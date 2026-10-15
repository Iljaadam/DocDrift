import copy
import json
import shutil
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

import httpx
import pytest

from docdrift.adapters import ExecutionRequest
from docdrift.nebius import NebiusSandboxAdapter, RemoteAdapterError, RemoteMutationsDisabled, UncertainSubmission
from docdrift.remote_journal import SubmissionConflict, SubmissionJournal
from docdrift.sandbox_execution import (
    GUEST_EXAMPLE, GUEST_REPOSITORY, GUEST_RUNNER, PYTHON_EXECUTABLE,
    RUNNER_BYTES, SandboxExecutionAdapter,
)
from docdrift.sandbox_simulation import IMAGE_ID, FixtureSandboxSimulation, create_fixture_simulation


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'renamed_method'
OTHER_IMAGE = '22222222-2222-4222-8222-222222222222'


def execution(tmp_path):
    snapshot = tmp_path / 'snapshot'
    shutil.copytree(FIXTURE / 'repository', snapshot)
    return ExecutionRequest(snapshot, (FIXTURE / 'repair.py').read_text(), {'DOCDRIFT_INPUT': '["red", "blue", "red"]'}, IMAGE_ID)


def bridge(state, handler=None):
    service = FixtureSandboxSimulation(state)
    service.register_profile(FIXTURE / 'repository', FIXTURE / 'profile.json', (FIXTURE / 'repair.py').read_text())
    transport = service.transport if handler is None else httpx.MockTransport(lambda request: handler(service, request))
    remote = NebiusSandboxAdapter('synthetic-key', 'synthetic-project', transport=transport,
                                  offline_simulation=True, journal=SubmissionJournal(state))
    adapter = SandboxExecutionAdapter(remote)
    adapter.simulation = service
    return adapter


class RecordingTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests = []

    def handle_request(self, request):
        self.requests.append(request)
        raise AssertionError('Bridge must refuse a provider-capable transport')


def test_bridge_refuses_nonmock_client_before_even_read_only_preflight(tmp_path):
    transport = RecordingTransport()
    with NebiusSandboxAdapter('synthetic-key', 'synthetic-project', transport=transport,
                              journal=SubmissionJournal(tmp_path)) as remote:
        with pytest.raises(RemoteMutationsDisabled):
            SandboxExecutionAdapter(remote)
    assert transport.requests == []


@pytest.mark.parametrize('method', ['preflight', 'execute', 'observe', 'recover', 'cancel', 'release'])
def test_each_bridge_entrypoint_rechecks_transport_even_after_reconfiguration(tmp_path, method):
    request = execution(tmp_path)
    foreign = RecordingTransport()
    with bridge(tmp_path / 'state') as adapter:
        adapter.remote._client.close()
        adapter.remote._client = httpx.Client(transport=foreign, trust_env=False)
        with pytest.raises(RemoteMutationsDisabled):
            if method == 'preflight':
                adapter.preflight(IMAGE_ID)
            elif method == 'execute':
                adapter.execute(request, lambda _: None, run_id='run', phase='phase')
            elif method == 'observe':
                adapter.observe(OTHER_IMAGE)
            elif method == 'recover':
                adapter.recover('run', 'phase', expected_image_id=IMAGE_ID)
            elif method == 'cancel':
                adapter.cancel(OTHER_IMAGE)
            else:
                adapter.release({})
        assert adapter.simulation.requests == []
    assert foreign.requests == []


def test_preflight_and_result_are_explicitly_synthetic_and_do_not_invent_timing(tmp_path):
    request = execution(tmp_path)
    with create_fixture_simulation(tmp_path / 'state', [FIXTURE]) as adapter:
        information = adapter.preflight(IMAGE_ID)
        accepted = []
        result = adapter.execute(request, accepted.append, run_id='run', phase='phase')
        assert information['synthetic'] and information['live_requests'] == information['code_executions'] == 0
        assert information['image_id'] == IMAGE_ID and not information['python_capability_tested']
        assert not information['network_isolation_tested'] and not information['live_mutations_enabled']
        assert result.synthetic and result.evidence_complete and result.service_state == 'SUCCESS'
        assert result.exit_code == 0 and json.loads(result.stdout) == {'red': 2, 'blue': 1}
        assert result.elapsed_seconds is None
        assert accepted == [result.operation_id]
        assert adapter.backend_name == 'nebius_sandbox_simulation' and adapter.scoped_execution
        assert adapter.execution_contract['arguments'] == ['-B', GUEST_RUNNER]
        before = adapter.simulation.requests.copy()
        adapter.release(asdict(result))
        assert adapter.simulation.requests == before
        assert all(method != 'DELETE' for method, _ in before)


def test_acceptance_callback_sees_durable_remote_identity(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    def accepted(operation_id):
        assert SubmissionJournal(state).lookup('run', 'phase')['operation_id'] == operation_id
    with bridge(state) as adapter:
        adapter.execute(request, accepted, run_id='run', phase='phase')


def test_snapshot_bytes_are_frozen_before_any_upload_and_guest_paths_are_separate(tmp_path):
    request = execution(tmp_path)
    source = request.snapshot / 'drift_demo' / '__init__.py'
    original = source.read_bytes()
    changed = False
    def handler(service, http_request):
        nonlocal changed
        if http_request.method == 'POST' and http_request.url.path.endswith('/files') and not changed:
            source.write_text('raise RuntimeError("changed after freezing")\n')
            changed = True
        return service.handle(http_request)
    with bridge(tmp_path / 'state', handler) as adapter:
        result = adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        assert result.exit_code == 0
        with sqlite3.connect(adapter.simulation.database) as connection:
            payload = json.loads(connection.execute('SELECT response_json FROM sandbox_mock_operations').fetchone()[0])['metadata']
            files = {path: connection.execute('SELECT content FROM sandbox_mock_files WHERE uuid=?', (record['uuid'],)).fetchone()[0]
                     for path, record in payload['files'].items()}
        assert files[f'{GUEST_REPOSITORY}/drift_demo/__init__.py'] == original
        assert files[GUEST_EXAMPLE] == request.code.encode()
        assert files[GUEST_RUNNER] == RUNNER_BYTES
        assert payload['command'] == PYTHON_EXECUTABLE and payload['args'] == ['-B', GUEST_RUNNER]
        assert payload['networking'] == {'enabled': False}
        assert payload['env']['PYTHONPATH'] == '/work/docdrift'
        assert payload['preserve_env'] is False and payload['shell'] is False
        assert payload['disposable'] is True


@pytest.mark.parametrize('bad_entry', ['symlink', 'directory_symlink', '.env', '.git', 'fifo'])
def test_unsafe_snapshot_entries_are_rejected_before_transport(tmp_path, bad_entry):
    request = execution(tmp_path)
    if bad_entry == 'symlink':
        (request.snapshot / 'outside').symlink_to(FIXTURE / 'repair.py')
    elif bad_entry == 'directory_symlink':
        (request.snapshot / 'outside').symlink_to(FIXTURE / 'repository', target_is_directory=True)
    elif bad_entry == 'fifo':
        import os
        os.mkfifo(request.snapshot / 'pipe')
    else:
        (request.snapshot / bad_entry).mkdir()
    with bridge(tmp_path / 'state') as adapter:
        with pytest.raises(ValueError):
            adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        assert adapter.simulation.requests == []
        assert SubmissionJournal(tmp_path / 'state').for_run('run') == []


def test_snapshot_ancestor_symlink_cannot_hide_a_prohibited_resolved_directory(tmp_path):
    request = execution(tmp_path)
    hidden = tmp_path / '.aws'
    hidden.mkdir()
    shutil.copytree(request.snapshot, hidden / 'repository')
    alias = tmp_path / 'alias'
    alias.symlink_to(hidden, target_is_directory=True)
    request = replace(request, snapshot=alias / 'repository')
    with bridge(tmp_path / 'state') as adapter:
        with pytest.raises(ValueError, match='resolves through'):
            adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        assert adapter.simulation.requests == []


@pytest.mark.parametrize('changes', [
    {'image': 'python:3.12'}, {'timeout_seconds': 31}, {'timeout_seconds': True},
    {'log_limit_bytes': 262145}, {'environment': {'NEBIUS_API_KEY': 'do-not-upload'}},
    {'environment': {'PYTHONPATH': '/other'}}, {'code': 'x' * 262145},
])
def test_invalid_request_contract_never_uploads_or_submits(tmp_path, changes):
    request = replace(execution(tmp_path), **changes)
    with bridge(tmp_path / 'state') as adapter:
        with pytest.raises(ValueError):
            adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        assert adapter.simulation.requests == []


def test_accepted_interruption_recovers_after_restart_without_upload_or_resubmit(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    def interrupt(_):
        raise RuntimeError('Interrupted controller callback')
    with bridge(state) as first:
        with pytest.raises(RemoteAdapterError, match='acceptance_callback_failed'):
            first.execute(request, interrupt, run_id='run', phase='phase')
    receipt = SubmissionJournal(state).lookup('run', 'phase')
    assert receipt['operation_id'] and receipt['state'] == 'accepted'
    with bridge(state) as resumed:
        accepted = []
        result = resumed.execute(request, accepted.append, run_id='run', phase='phase')
        assert result.operation_id == receipt['operation_id'] and result.exit_code == 0
        assert accepted == [result.operation_id]
        assert resumed.simulation.requests == [('GET', f'operations/{result.operation_id}')]


def test_ambiguous_instance_receipt_survives_restart_and_forbids_all_retries(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    def handler(service, http_request):
        response = service.handle(http_request)
        if http_request.method == 'POST' and http_request.url.path.endswith('/instances'):
            raise httpx.ReadTimeout('Synthetic missing acceptance response', request=http_request)
        return response
    with bridge(state, handler) as first:
        with pytest.raises(UncertainSubmission):
            first.execute(request, lambda _: None, run_id='run', phase='phase')
    receipt = SubmissionJournal(state).lookup('run', 'phase')
    assert receipt['state'] == 'uncertain' and receipt['operation_id'] is None
    with bridge(state) as resumed:
        with pytest.raises(UncertainSubmission, match='saved_submission_cannot_retry'):
            resumed.execute(request, lambda _: None, run_id='run', phase='phase')
        assert resumed.simulation.requests == []
        with sqlite3.connect(resumed.simulation.database) as connection:
            assert connection.execute('SELECT COUNT(*) FROM sandbox_mock_operations').fetchone()[0] == 1


def test_ambiguous_upload_receipt_survives_restart_without_reupload(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    def handler(service, http_request):
        response = service.handle(http_request)
        if http_request.method == 'POST' and http_request.url.path.endswith('/files'):
            raise httpx.ReadTimeout('Synthetic uncertain upload', request=http_request)
        return response
    with bridge(state, handler) as first:
        with pytest.raises(RemoteAdapterError, match='transport_timeout'):
            first.execute(request, lambda _: None, run_id='run', phase='phase')
    with bridge(state) as resumed:
        with pytest.raises(RemoteAdapterError, match='upload_uncertain_no_retry'):
            resumed.execute(request, lambda _: None, run_id='run', phase='phase')
        assert resumed.simulation.requests == []
        assert SubmissionJournal(state).for_run('run') == []


def test_definitive_submission_rejection_stays_rejected_and_never_retries(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    def handler(service, http_request):
        if http_request.method == 'POST' and http_request.url.path.endswith('/instances'):
            return httpx.Response(403, json={})
        return service.handle(http_request)
    with bridge(state, handler) as first:
        with pytest.raises(RemoteAdapterError, match='http_403'):
            first.execute(request, lambda _: None, run_id='run', phase='phase')
    assert SubmissionJournal(state).lookup('run', 'phase')['state'] == 'rejected'
    with bridge(state) as resumed:
        with pytest.raises(RemoteAdapterError, match='saved_submission_rejected_no_retry'):
            resumed.execute(request, lambda _: None, run_id='run', phase='phase')
        assert resumed.simulation.requests == []


def test_wrong_recovery_image_does_not_replace_the_owned_operation_expectation(tmp_path):
    request = execution(tmp_path)
    with bridge(tmp_path / 'state') as adapter:
        result = adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        with pytest.raises(SubmissionConflict):
            adapter.recover('run', 'phase', expected_image_id=OTHER_IMAGE)
        assert adapter.observe(result.operation_id).evidence_complete


def test_recovered_callback_failure_has_safe_error_and_retains_accepted_identity(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    with bridge(state) as first:
        result = first.execute(request, lambda _: None, run_id='run', phase='phase')
    def failed_callback(_):
        raise RuntimeError('untrusted callback contents')
    with bridge(state) as resumed:
        with pytest.raises(RemoteAdapterError, match='acceptance_callback_failed') as raised:
            resumed.execute(request, failed_callback, run_id='run', phase='phase')
        assert raised.value.operation_id == result.operation_id
        assert raised.value.__context__ is None
        assert resumed.simulation.requests == []


@pytest.mark.parametrize('change', ['code', 'environment', 'snapshot', 'image', 'timeout', 'log_limit'])
def test_reusing_a_phase_with_changed_frozen_inputs_cannot_reuse_success(tmp_path, change):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    with bridge(state) as first:
        first.execute(request, lambda _: None, run_id='run', phase='phase')
    if change == 'code':
        request = replace(request, code=request.code + '# changed\n')
    elif change == 'environment':
        request = replace(request, environment={'DOCDRIFT_INPUT': '[]'})
    elif change == 'snapshot':
        (request.snapshot / 'drift_demo' / '__init__.py').write_text('# changed source\n')
    elif change == 'image':
        request = replace(request, image=OTHER_IMAGE)
    elif change == 'timeout':
        request = replace(request, timeout_seconds=29)
    else:
        request = replace(request, log_limit_bytes=1000)
    with bridge(state) as resumed:
        with pytest.raises(SubmissionConflict, match='inputs changed'):
            resumed.execute(request, lambda _: None, run_id='run', phase='phase')
        assert resumed.simulation.requests == []


@pytest.mark.parametrize('fault', ['signal', 'missing_result', 'network', 'stdout_truncated', 'wrong_image'])
def test_remote_status_signal_isolation_and_evidence_loss_survive_shared_result_conversion(tmp_path, fault):
    request = execution(tmp_path)
    def handler(service, http_request):
        response = service.handle(http_request)
        if http_request.method != 'GET' or '/operations/' not in http_request.url.path:
            return response
        data = copy.deepcopy(response.json())
        if fault == 'signal':
            data['metadata']['result']['state']['signal'] = 9
        elif fault == 'missing_result':
            data['metadata']['result'] = None
        elif fault == 'network':
            data['metadata']['networking'] = {'enabled': True}
        elif fault == 'stdout_truncated':
            data['metadata']['result']['stdout']['truncated'] = True
        else:
            data['image_uuid'] = OTHER_IMAGE
        return httpx.Response(200, json=data)
    with bridge(tmp_path / 'state', handler) as adapter:
        result = adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        assert result.synthetic and result.service_state == 'SUCCESS'
        if fault == 'signal':
            assert result.signal == 9
        elif fault == 'stdout_truncated':
            assert result.stdout_truncated
        else:
            assert not result.evidence_complete and result.state == 'incomplete'


def test_observation_timeout_is_not_guest_timeout_and_does_not_cancel_or_complete_receipt(tmp_path, monkeypatch):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    def handler(service, http_request):
        response = service.handle(http_request)
        if http_request.method == 'GET' and '/operations/' in http_request.url.path:
            data = response.json()
            data['status'] = 'EXECUTING'
            return httpx.Response(200, json=data)
        return response
    with bridge(state, handler) as adapter:
        observe = adapter.remote.observe
        monkeypatch.setattr(adapter.remote, 'observe', lambda operation_id, *args, **kwargs: observe(operation_id, timeout_seconds=0))
        result = adapter.execute(request, lambda _: None, run_id='run', phase='phase')
        assert result.observation_timed_out and not result.timed_out and result.state == 'pending'
        assert SubmissionJournal(state).lookup('run', 'phase')['state'] == 'accepted'
        adapter.release(asdict(result))
        assert not any(method == 'DELETE' for method, _ in adapter.simulation.requests)


def test_cancel_is_explicit_and_recovery_restores_ownership(tmp_path):
    request = execution(tmp_path)
    state = tmp_path / 'state'
    with bridge(state) as first:
        result = first.execute(request, lambda _: None, run_id='run', phase='phase')
    with bridge(state) as resumed:
        with pytest.raises(RemoteAdapterError, match='operation_not_owned'):
            resumed.cancel(result.operation_id)
        resumed.recover('run', 'phase', expected_image_id=IMAGE_ID)
        resumed.cancel(result.operation_id)
        assert resumed.simulation.requests == [('DELETE', f'operations/{result.operation_id}')]
