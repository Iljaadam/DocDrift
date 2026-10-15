"""Exercise the shared controller against synthetic Sandbox responses only."""

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from docdrift.cli import demo_repository, main
from docdrift.adapters import ExecutionRequest, ExecutionResult
from docdrift.execution import perform_execution
from docdrift.engine import failure_signature, resume_run, start_run
from docdrift.evaluation import evaluate_fixture
from docdrift.evidence import verify_evidence
from docdrift.profile import check_result, load_profile
from docdrift.repair import ScriptedModel
from docdrift.sandbox_simulation import IMAGE_ID, create_fixture_simulation
from docdrift.store import StateStore


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/development/source_only'


def scripted_agent():
    code = (FIXTURE / 'repair.py').read_text()
    def response(name, arguments):
        return {'choices': [{'message': {'role': 'assistant', 'tool_calls': [{
            'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)},
        }]}}]}
    return ScriptedModel([response('read_file', {'path': 'drift_demo/__init__.py'}),
                          response('run_python', {'code': code}), response('submit_replacement', {'code': code})])


def owned_repository(tmp_path):
    repository = tmp_path / 'repository'
    demo_repository(FIXTURE / 'repository', repository)
    return repository


def test_model_probe_and_verifier_path_is_durable_synthetic_and_integrity_checkable(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Synthetic execution must not contact a socket or Docker')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr('docdrift.adapters.LocalDockerAdapter.preflight', forbidden)
    state = tmp_path / 'state'
    with create_fixture_simulation(state, [FIXTURE]) as adapter:
        row = evaluate_fixture(FIXTURE, 'agent', scripted_agent(), state, IMAGE_ID, adapter=adapter)
        assert row['outcome'] == 'synthetic_contract_passed'
        assert row['evidence'] == 'synthetic_not_execution'
        assert row['scored'] is False and not row['verified']
        assert row['compute_operations'] == 0 and row['simulated_operations'] == 14
        assert len(StateStore(state).operations(row['probe_run_id'])) == 2
        assert all(method != 'DELETE' for method, _ in adapter.simulation.requests)
    root = state / 'runs' / row['run_id']
    report = json.loads((root / 'report.json').read_text())
    assert report['adapter'] == 'nebius_sandbox_simulation'
    assert report['behavior_verified'] is False
    assert not any(example['verified'] for example in report['examples'])
    assert report['usage']['compute_operations'] == 0
    assert report['usage']['simulated_operations'] == 12
    assert all(item['result']['synthetic'] for item in report['results'])
    html = (root / 'review.html').read_text()
    assert '<h1>Synthetic contract passed</h1>' in html
    assert '<h1>Behavior verified</h1>' not in html
    assert 'No guest code executed' in html
    commands = json.loads((root / 'commands.json').read_text())['operations']
    assert all(item['synthetic'] and item['arguments'] == ['-B', '/work/docdrift/runner.py'] for item in commands)
    assert verify_evidence(root / 'evidence.zip')['execution_attested'] is False


def test_resume_after_accepted_callback_interruption_reuses_id_and_cli_selects_backend(tmp_path, monkeypatch, capsys):
    state = tmp_path / 'state'
    repository = owned_repository(tmp_path)
    original_save = StateStore.save_operation
    failed = False
    def fail_once(store, run_id, phase, operation_id):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError('Simulated callback interruption')
        return original_save(store, run_id, phase, operation_id)
    with create_fixture_simulation(state, [FIXTURE]) as adapter:
        with monkeypatch.context() as changes:
            changes.setattr(StateStore, 'save_operation', fail_once)
            report = start_run(repository, 'HEAD', FIXTURE / 'profile.json', FIXTURE / 'repair.py', state, IMAGE_ID, adapter)
        assert report['status'] == 'incomplete'
        receipts = adapter.remote.journal.for_run(report['run_id'])
        assert len(receipts) == 1 and receipts[0]['operation_id']
        first_id = receipts[0]['operation_id']
    monkeypatch.setattr('sys.argv', ['docdrift', '--state-dir', str(state), 'resume', report['run_id']])
    main()
    output = json.loads(capsys.readouterr().out)
    assert output['status'] == 'completed' and output['repair_verdict'] == 'synthetic_contract_passed'
    operations = StateStore(state).operations(report['run_id'])
    assert len(operations) == 12 and operations[0]['operation_id'] == first_id
    with create_fixture_simulation(state, []) as adapter:
        assert len(adapter.remote.journal.for_run(report['run_id'])) == 12


@pytest.mark.parametrize('timeout_at', [1, 7, 10])
def test_observation_timeout_remains_accepted_and_can_resume_without_resubmission(tmp_path, monkeypatch, timeout_at):
    state = tmp_path / 'state'
    repository = owned_repository(tmp_path)
    with create_fixture_simulation(state, [FIXTURE]) as adapter:
        observe = adapter.observe
        observations = 0
        def timed_out(operation_id, *args, **kwargs):
            nonlocal observations
            observations += 1
            result = observe(operation_id, *args, **kwargs)
            return replace(result, state='pending', observation_timed_out=True) if observations == timeout_at else result
        with monkeypatch.context() as changes:
            changes.setattr(adapter, 'observe', timed_out)
            report = start_run(repository, 'HEAD', FIXTURE / 'profile.json', FIXTURE / 'repair.py', state, IMAGE_ID, adapter)
        assert report['status'] == 'incomplete'
        operations = StateStore(state).operations(report['run_id'])
        assert len(operations) == timeout_at
        operation = operations[-1]
        assert operation['result'] is None
        before = sum(method == 'POST' and path == 'instances' for method, path in adapter.simulation.requests)
        resumed = resume_run(report['run_id'], state, adapter)
        assert resumed['repair_verdict'] == 'synthetic_contract_passed'
        assert sum(method == 'POST' and path == 'instances' for method, path in adapter.simulation.requests) == before + 12 - timeout_at
        assert all(method != 'DELETE' for method, _ in adapter.simulation.requests)


def test_cached_wrong_image_never_bypasses_probe_identity_check(tmp_path):
    class WrongImage:
        calls = 0
        def execute(self, request, on_accepted):
            self.calls += 1
            on_accepted('wrong-image-operation')
            return ExecutionResult('completed', 0, '{}', '', 'wrong-image-operation', 'wrong-image', 0)
        def cancel(self, operation_id):
            pass
    adapter = WrongImage()
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    store = StateStore(tmp_path / 'state')
    store.create_run('probe-scope', {})
    request = ExecutionRequest(snapshot, 'print({})', {}, IMAGE_ID)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='different environment image'):
            perform_execution(adapter, store, 'probe-scope', 'probe/0', request)
    assert adapter.calls == 1


@pytest.mark.parametrize('change', [
    {'signal': 9}, {'observation_timed_out': True}, {'evidence_complete': False},
    {'service_state': 'FAILED'}, {'timed_out': True}, {'stdout_truncated': True},
])
def test_remote_failure_details_cannot_verify_or_reproduce_drift(change):
    profile, _ = load_profile(FIXTURE / 'profile.json')
    spec = profile['examples'][0]
    result = {'state': 'completed', 'exit_code': 0, 'stdout': '{}', 'stderr': '', **change}
    checked = check_result(result, spec['cases'][0], (FIXTURE / 'repair.py').read_text(), spec['required_call'], spec['operation_ast_sha256'])
    assert checked['behavior_passed'] is False
    result['exit_code'] = 1
    assert failure_signature({'result': result, 'checks': checked}) is None


def test_cli_simulation_refuses_live_inference_before_model_client_or_network(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('Live inference must be rejected before constructing a client')
    monkeypatch.setattr('docdrift.repair.TokenFactoryClient', forbidden)
    monkeypatch.setattr('sys.argv', ['docdrift', '--state-dir', str(tmp_path), 'repair', '--execution-backend', 'sandbox-simulation', '--live', '--model', 'unused'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert '--live is disabled' in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
