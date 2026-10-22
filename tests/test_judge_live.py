"""Synthetic HTTP fixtures only: none of these tests execute guest code."""

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from docdrift.adapters import ExecutionRequest
from docdrift.judge_live import (
    IMAGE_ID, PROJECT_ID, JudgeExecutionAdapter, run_capability,
)
from docdrift.markdown import extract_examples
from docdrift.nebius import (
    NebiusSandboxAdapter, RemoteAdapterError, RemoteExecutionRequest,
    RemoteMutationsDisabled, UncertainSubmission,
)
from docdrift.policy import apply_replacement
from docdrift.remote_journal import SubmissionConflict, SubmissionJournal
from docdrift.sandbox_execution import GUEST_RUNNER, PYTHON_EXECUTABLE


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'fixtures/development/source_only'
OTHER = '22222222-2222-4222-8222-222222222222'


def capability():
    # Explicitly manufactured startup result; not a live capability claim.
    return {'kind': 'docdrift_judge_sandbox_capability', 'status': 'verified',
            'project_id': PROJECT_ID, 'image_id': IMAGE_ID, 'operation_id': OTHER,
            'python': [3, 12], 'euid': 65534, 'interfaces': ['lo'], 'synthetic': False}


class Service:
    """Return owned manufactured responses without importing uploaded Python."""

    def __init__(self):
        self.requests = []
        self.operations = {}
        self.payloads = []
        self.capability_facts = {'python': [3, 12], 'euid': 65534, 'interfaces': ['lo']}
        self.failure = None
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request):
        path = request.url.path.removeprefix('/sandboxes/v1/')
        self.requests.append((request.method, path))
        assert request.headers['Project'] == PROJECT_ID
        assert request.headers['Authorization'] == 'Bearer synthetic-key'
        if self.failure == (request.method, path):
            raise httpx.ConnectError('synthetic ambiguous transport failure', request=request)
        if request.method == 'POST' and path == 'files':
            return httpx.Response(201, json={'uuid': str(uuid4()), 'size': len(request.content),
                                             'sha256': hashlib.sha256(request.content).hexdigest()})
        if request.method == 'POST' and path == 'instances':
            payload = json.loads(request.content)
            self.payloads.append(payload)
            assert payload['image'] == IMAGE_ID
            assert payload['networking'] == {'enabled': False}
            assert payload['shell'] is False and payload['preserve_env'] is False
            assert payload['disposable'] is True and payload['uid'] == payload['gid'] == 65534
            assert payload['command'] == PYTHON_EXECUTABLE
            assert payload['timeout'] == 30
            operation_id = str(uuid4())
            stdout = json.dumps(self.capability_facts) if payload['args'][0] == '-I' else '{}\n'
            stream = lambda value: {'value': value, 'encoding': 'utf-8', 'truncated': False}
            self.operations[operation_id] = {
                'uuid': operation_id, 'kind': 'instance', 'status': 'SUCCESS', 'image_uuid': IMAGE_ID,
                'result_image_uuid': None, 'duration': 0.5,
                'metadata': {**payload, 'result': {
                    'state': {'exit_code': 0, 'signal': -1, 'timed_out': False},
                    'stdout': stream(stdout), 'stderr': stream(''), 'resources': {},
                }},
            }
            return httpx.Response(201, json={'uuid': operation_id})
        if request.method == 'GET' and path.startswith('operations/'):
            return httpx.Response(200, json=self.operations[path.removeprefix('operations/')])
        raise AssertionError('Unexpected request outside synthetic service contract')


def request(tmp_path, fixture=FIXTURE):
    snapshot = tmp_path / 'snapshot'
    shutil.copytree(fixture / 'repository', snapshot)
    original = (snapshot / 'README.md').read_bytes()
    return ExecutionRequest(snapshot, extract_examples('README.md', original)[0].code,
                            {'DOCDRIFT_INPUT': '[]'}, IMAGE_ID)


def bridge(tmp_path, service, reserve=lambda: None, fixture=FIXTURE):
    return JudgeExecutionAdapter('synthetic-key', tmp_path / 'state', fixture, reserve,
                                 capability=capability(), transport=service.transport)


def test_constructor_and_preflight_make_no_requests(tmp_path):
    service = Service()
    with bridge(tmp_path, service) as adapter:
        info = adapter.preflight(IMAGE_ID)
        assert info['python_capability_tested'] and info['network_isolation_tested']
        assert not info['synthetic'] and info['billing_coverage'] == 'unverified'
        assert adapter.execution_contract['fixture'] == 'source_only'
        assert adapter.execution_contract['arguments'] == ['-B', GUEST_RUNNER]
    assert not service.requests


@pytest.mark.parametrize('name', ['source_only', 'renamed_import', 'changed_return_shape'])
def test_only_approved_fixture_contents_can_spawn(tmp_path, name):
    fixture = ROOT / 'fixtures' / ('development' if name == 'source_only' else 'evaluation') / name
    service, reserved = Service(), []
    with bridge(tmp_path, service, lambda: reserved.append(True), fixture) as adapter:
        accepted = []
        result = adapter.execute(request(tmp_path, fixture), accepted.append, run_id='run', phase='probe/0')
        assert result.state == 'completed' and not result.synthetic and result.evidence_complete
        assert reserved == [True] and accepted == [result.operation_id]
        adapter.release({})
        assert all(method != 'DELETE' for method, _ in service.requests)
        assert service.payloads[0]['args'] == ['-B', GUEST_RUNNER]
        assert set(service.payloads[0]['env']) == {
            'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE', 'DOCDRIFT_INPUT'}


def test_resume_observes_receipt_without_reserving_uploading_or_spawning(tmp_path):
    service, reserved = Service(), []
    req = request(tmp_path)
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        result = adapter.execute(req, lambda _: None, run_id='run', phase='probe/0')
    before = service.requests.copy()
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        saved = adapter.execute(req, lambda _: None, run_id='run', phase='probe/0')
    assert saved == result and reserved == [True]
    assert service.requests[len(before):] == [('GET', 'operations/' + result.operation_id)]


def test_second_phase_uses_durable_cached_uploads_but_reserves_new_spawn(tmp_path):
    service, reserved = Service(), []
    req = request(tmp_path)
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        adapter.execute(req, lambda _: None, run_id='run', phase='probe/0')
    uploads = service.requests.count(('POST', 'files'))
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        adapter.execute(req, lambda _: None, run_id='run', phase='probe/1')
    assert reserved == [True, True]
    assert service.requests.count(('POST', 'files')) == uploads


@pytest.mark.parametrize('mutation', ['image', 'network_env', 'input', 'timeout', 'log_limit', 'source', 'added', 'readme_prose', 'healthy'])
def test_invalid_request_is_rejected_before_any_provider_request(tmp_path, mutation):
    service, req = Service(), request(tmp_path)
    if mutation == 'image':
        req = replace(req, image=OTHER)
    elif mutation == 'network_env':
        req = replace(req, environment={'NEBIUS_API_KEY': 'must-never-upload'})
    elif mutation == 'input':
        req = replace(req, environment={'DOCDRIFT_INPUT': 'unapproved'})
    elif mutation == 'timeout':
        req = replace(req, timeout_seconds=29)
    elif mutation == 'log_limit':
        req = replace(req, log_limit_bytes=99)
    elif mutation == 'source':
        (req.snapshot / 'drift_demo/__init__.py').write_text('print("modified")')
    elif mutation == 'added':
        (req.snapshot / 'credentials.txt').write_text('never upload')
    elif mutation == 'readme_prose':
        with (req.snapshot / 'README.md').open('a') as stream:
            stream.write('\nmodified prose\n')
    else:
        path = req.snapshot / 'README.md'
        path.write_bytes(path.read_bytes().replace(b'measure(', b'wrong('))
    with bridge(tmp_path, service) as adapter, pytest.raises((ValueError, RemoteAdapterError)):
        adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    assert service.requests == []


def test_policy_checked_target_replacement_can_enter_snapshot(tmp_path):
    service, req = Service(), request(tmp_path)
    path = req.snapshot / 'README.md'
    original = path.read_bytes()
    target = extract_examples('README.md', original)[0]
    # A test-only curated proposal; no model receives this file.
    proposal = (FIXTURE / 'repair.py').read_text()
    path.write_bytes(apply_replacement('README.md', original, target.id, target.source_hash, proposal))
    with bridge(tmp_path, service) as adapter:
        adapter.execute(replace(req, code=proposal), lambda _: None, run_id='run', phase='phase')
    assert service.payloads


def test_arbitrary_probe_code_stays_in_isolated_guest(tmp_path):
    service, req = Service(), request(tmp_path)
    code = 'raise RuntimeError("This must never execute on the controller")\n'
    with bridge(tmp_path, service) as adapter:
        result = adapter.execute(replace(req, code=code), lambda _: None, run_id='run', phase='probe/0')
    assert result.state == 'completed'  # Manufactured response, not code execution.


def test_ambiguous_spawn_is_consumed_and_never_retried(tmp_path):
    service, req, reserved = Service(), request(tmp_path), []
    service.failure = ('POST', 'instances')
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        with pytest.raises(UncertainSubmission):
            adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    service.failure = None
    before = service.requests.copy()
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        with pytest.raises(UncertainSubmission):
            adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    assert service.requests == before and reserved == [True]


def test_ambiguous_upload_is_never_retried_and_never_reserves_spawn(tmp_path):
    service, req, reserved = Service(), request(tmp_path), []
    service.failure = ('POST', 'files')
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter, pytest.raises(RemoteAdapterError):
        adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    before = service.requests.copy()
    service.failure = None
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter, pytest.raises(RemoteAdapterError):
        adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    assert service.requests == before and reserved == []


def test_budget_refusal_happens_before_post_and_cannot_be_retried(tmp_path):
    service, req, reserved = Service(), request(tmp_path), []
    def refuse():
        reserved.append(True)
        raise ValueError('synthetic_budget_exhausted')
    with bridge(tmp_path, service, refuse) as adapter, pytest.raises(UncertainSubmission):
        adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    assert not service.payloads and reserved == [True]
    with bridge(tmp_path, service) as adapter, pytest.raises(UncertainSubmission):
        adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    assert not service.payloads


def test_local_operation_cap_is_durable_across_adapter_restarts(tmp_path):
    service, req, reserved = Service(), request(tmp_path), []
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter:
        for index in range(17):
            adapter.execute(req, lambda _: None, run_id='run', phase='probe/' + str(index))
    with bridge(tmp_path, service, lambda: reserved.append(True)) as adapter, pytest.raises(RemoteAdapterError, match='judge_operation_limit'):
        adapter.execute(req, lambda _: None, run_id='run', phase='probe/17')
    assert len(reserved) == len(service.payloads) == 17


@pytest.mark.parametrize('method,path', [('GET', 'whoami'), ('GET', 'inspect/' + IMAGE_ID + '/'),
    ('GET', 'operations/' + OTHER), ('POST', 'files'), ('POST', 'instances'),
    ('POST', 'images/import'), ('DELETE', 'operations/' + OTHER)])
def test_direct_requests_never_bypass_scoped_entrypoints(tmp_path, method, path):
    service = Service()
    with bridge(tmp_path, service) as adapter, pytest.raises(RemoteAdapterError):
        adapter.remote._request(method, path)
    assert service.requests == []


def test_direct_submit_and_upload_are_blocked(tmp_path):
    service = Service()
    with bridge(tmp_path, service) as adapter:
        with pytest.raises(RemoteAdapterError):
            adapter.remote.prepare({'/work/docdrift/secret': b'never upload'})
        with pytest.raises(RemoteAdapterError):
            adapter.remote.submit(RemoteExecutionRequest(IMAGE_ID, '/bin/sh'), lambda _: None, run_id='run', phase='phase')
    assert service.requests == []


@pytest.mark.parametrize('key,value', [('image_id', OTHER), ('project_id', 'other'), ('python', [3, 11]),
    ('euid', 0), ('interfaces', ['eth0', 'lo']), ('synthetic', True), ('operation_id', 'invalid')])
def test_wrong_startup_capability_blocks_constructor(tmp_path, key, value):
    record = capability()
    record[key] = value
    service = Service()
    with pytest.raises(ValueError):
        JudgeExecutionAdapter('synthetic-key', tmp_path / 'state', FIXTURE, lambda: None,
                              capability=record, transport=service.transport)
    assert service.requests == []


def test_startup_uses_one_probe_then_reuses_durable_record(tmp_path):
    service, reserved = Service(), []
    record = run_capability('synthetic-key', tmp_path / 'startup', lambda: reserved.append(True), transport=service.transport)
    assert record['status'] == 'verified' and record['image_id'] == IMAGE_ID
    assert reserved == [True] and len(service.payloads) == 1
    assert service.payloads[0]['files'] == {} and service.payloads[0]['args'][0] == '-I'
    before = service.requests.copy()
    saved = run_capability('synthetic-key', tmp_path / 'startup', lambda: reserved.append(True), transport=service.transport)
    assert saved == record and service.requests == before and reserved == [True]


@pytest.mark.parametrize('facts', [{'python': [3, 11], 'euid': 65534, 'interfaces': ['lo']},
    {'python': [3, 12], 'euid': 0, 'interfaces': ['lo']},
    {'python': [3, 12], 'euid': 65534, 'interfaces': ['eth0']},
    {'python': [3, 12], 'euid': 65534, 'interfaces': ['lo'], 'operation_id': OTHER}])
def test_startup_rejects_invalid_facts_without_second_spawn(tmp_path, facts):
    service, reserved = Service(), []
    service.capability_facts = facts
    for _ in range(2):
        with pytest.raises(RemoteAdapterError, match='judge_startup_capability_failed'):
            run_capability('synthetic-key', tmp_path / 'startup', lambda: reserved.append(True), transport=service.transport)
    assert reserved == [True] and len(service.payloads) == 1


def test_startup_recovers_accepted_operation_after_callback_failure(tmp_path, monkeypatch):
    from docdrift import judge_live
    service, reserved = Service(), []
    original = judge_live._write
    def fail_record(path, content):
        if path.name == 'capability.json':
            raise OSError('synthetic write failure')
        original(path, content)
    monkeypatch.setattr(judge_live, '_write', fail_record)
    with pytest.raises(OSError):
        run_capability('synthetic-key', tmp_path / 'startup', lambda: reserved.append(True), transport=service.transport)
    monkeypatch.setattr(judge_live, '_write', original)
    assert run_capability('synthetic-key', tmp_path / 'startup', lambda: reserved.append(True), transport=service.transport)['status'] == 'verified'
    assert reserved == [True] and len(service.payloads) == 1


def test_startup_ambiguous_submission_never_reposts(tmp_path):
    service, reserved = Service(), []
    service.failure = ('POST', 'instances')
    for _ in range(2):
        with pytest.raises(UncertainSubmission):
            run_capability('synthetic-key', tmp_path / 'startup', lambda: reserved.append(True), transport=service.transport)
    assert reserved == [True] and service.requests == [('POST', 'instances')]


def test_consumed_f6_state_is_refused(tmp_path):
    service = Service()
    with pytest.raises(ValueError, match='consumed F6'):
        JudgeExecutionAdapter('synthetic-key', tmp_path / 'sandbox-f6', FIXTURE, lambda: None,
                              capability=capability(), transport=service.transport)
    assert service.requests == []


def test_wrong_fixture_profile_or_source_cannot_be_selected(tmp_path):
    service = Service()
    fixture = tmp_path / 'development/source_only'
    shutil.copytree(FIXTURE.parent, fixture.parent)
    (fixture / 'checks.py').write_text('raise RuntimeError("must never run")')
    with pytest.raises(ValueError, match='profile or checks'):
        bridge(tmp_path, service, fixture=fixture)
    assert service.requests == []


def test_frozen_run_profile_cannot_change(tmp_path):
    service, req = Service(), request(tmp_path)
    profile = tmp_path / 'state/runs/run/profile'
    profile.mkdir(parents=True)
    (profile / 'profile.json').write_bytes((FIXTURE / 'profile.json').read_bytes())
    (profile / 'checks.py').write_text('malicious changed check')
    with bridge(tmp_path, service) as adapter, pytest.raises(RemoteAdapterError, match='judge_frozen_profile_changed'):
        adapter.execute(req, lambda _: None, run_id='run', phase='phase')
    assert service.requests == []


def test_fixture_binding_prevents_state_reuse_for_a_different_case(tmp_path):
    service = Service()
    with bridge(tmp_path, service):
        pass
    with pytest.raises(SubmissionConflict):
        bridge(tmp_path, service, fixture=ROOT / 'fixtures/evaluation/renamed_import')
    assert service.requests == []


def test_default_remote_still_blocks_live_mutations(tmp_path):
    service = Service()
    with NebiusSandboxAdapter('synthetic-key', PROJECT_ID, transport=service.transport,
                              journal=SubmissionJournal(tmp_path)) as remote:
        with pytest.raises(RemoteMutationsDisabled):
            remote.prepare({'/work/docdrift/example.py': b'print(1)'})
    assert service.requests == []


def test_full_engine_verifier_round_trip_with_manufactured_http_evidence(tmp_path):
    """A contract rehearsal, never evidence that the twelve snippets ran."""
    from docdrift.cli import demo_repository
    from docdrift.engine import resume_run, start_run
    from docdrift.sandbox_simulation import FixtureSandboxSimulation, IMAGE_ID as SIMULATED_IMAGE

    class PinnedFixtureService(FixtureSandboxSimulation):
        def _observation(self, payload):
            return super()._observation({**payload, 'image': SIMULATED_IMAGE})

    state = tmp_path / 'state'
    service = PinnedFixtureService(tmp_path / 'manufactured-service')
    service.register_profile(FIXTURE / 'repository', FIXTURE / 'profile.json', (FIXTURE / 'repair.py').read_text())
    repository = tmp_path / 'repository'
    demo_repository(FIXTURE / 'repository', repository)
    reserved = []
    with JudgeExecutionAdapter('synthetic-key', state, FIXTURE, lambda: reserved.append(True),
                               capability=capability(), transport=service.transport) as adapter:
        report = start_run(repository, 'HEAD', FIXTURE / 'profile.json', FIXTURE / 'repair.py', state, IMAGE_ID, adapter)
        assert report['status'] == 'completed' and report['repair_verdict'] == 'behavior_verified'
        assert report['protected_hashes_preserved'] and len(reserved) == 12
        assert report['environment']['capability']['operation_id'] == OTHER
        before = service.requests.copy()
        assert resume_run(report['run_id'], state, adapter)['run_id'] == report['run_id']
        assert service.requests == before
