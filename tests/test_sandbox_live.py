"""Isolated wire fixtures for fixed activation; no guest code or network runs.

HTTPTransport.handle_request is replaced inside each test. Its fixture returns
manufactured process results from frozen contracts; these temporary test runs
are never live execution evidence or coverage confirmations.
"""

import base64
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import httpx
import pytest

from docdrift.adapters import ExecutionRequest
from docdrift.engine import resume_run
from docdrift.evidence import verify_evidence
from docdrift.markdown import extract_examples
from docdrift.nebius import RemoteAdapterError, RemoteMutationsDisabled, UncertainSubmission
from docdrift.remote_journal import SubmissionConflict, SubmissionJournal
from docdrift.sandbox_execution import GUEST_EXAMPLE, GUEST_REPOSITORY, SandboxExecutionAdapter
from docdrift.sandbox_live import (
    ARTIFACT_BYTES, ARTIFACT_PATH, F6ExecutionAdapter, F6SandboxRemote, PROJECT_ID, PROBES,
    _coverage,
)
from docdrift.sandbox_plan import F6_RUN_ID, initialize_f6_run, prepare_f6_plan
from docdrift.snapshot import file_hashes


ROOT = Path(__file__).resolve().parents[1]
IMAGE = '11111111-1111-4111-8111-111111111111'
RETAINED = '22222222-2222-4222-8222-222222222222'
REGISTRY = 'docker://docker.io/library/python@sha256:' + 'a' * 64
SCOPED_LIMITS = {'image_imports': 1, 'runtime_probes': 3, 'verifier_operations': 12, 'inference_calls': 0}


def scoped_authorization(prepared):
    value = {
        'kind': 'docdrift_sandbox_scoped_authorization', 'project_id': PROJECT_ID,
        'billing_coverage': 'unverified', 'source_run_id': F6_RUN_ID,
        'limits': dict(SCOPED_LIMITS),
        'authorization': 'Synthetic scoped permission fixture only; no actual authorization or billing assertion.',
        'authorized_at_utc': '2026-10-16T12:00:00Z',
    }
    prepared.coverage.write_text(json.dumps(value))
    return value


class SyntheticWire:
    """Manufacture API bytes; never execute the imported image or uploads."""

    def __init__(self, plan_root, plan, state):
        self.plan = plan
        self.state = state
        self.requests = []
        self.files = {}
        self.operations = {}
        self.fail_once = None
        self.reject_once = None
        self.before_request = None
        self.profile = json.loads((plan_root / 'profile/profile.json').read_text())

    def counts(self):
        return Counter((method, path) for method, path, _ in self.requests)

    @staticmethod
    def stream(value):
        return {'value': base64.b64encode(value.encode()).decode(), 'encoding': 'base64', 'truncated': False}

    def handle(self, request):
        path = request.url.path.removeprefix('/sandboxes/v1/')
        payload = json.loads(request.content) if request.content and path != 'files' else None
        self.requests.append((request.method, path, payload))
        if self.before_request:
            self.before_request(request.method, path, payload)
        if self.reject_once == (request.method, path):
            self.reject_once = None
            return httpx.Response(403, json={'error': 'synthetic rejection'})
        response = self.response(request, path, payload)
        if self.fail_once == (request.method, path):
            self.fail_once = None
            raise httpx.ReadTimeout('Synthetic response lost after acceptance', request=request)
        return response

    def response(self, request, path, payload):
        if (request.method, path) == ('POST', 'images/import'):
            operation = str(uuid4())
            self.operations[operation] = {
                'uuid': operation, 'kind': 'image_import', 'status': 'SUCCESS',
                'image_uuid': None, 'result_image_uuid': IMAGE, 'result': {'image': IMAGE},
            }
            return httpx.Response(201, json={'uuid': operation})
        if (request.method, path) == ('GET', f'inspect/{IMAGE}/'):
            return httpx.Response(200, json={'uuid': IMAGE})
        if (request.method, path) == ('POST', 'files'):
            file_id = str(uuid4())
            self.files[file_id] = request.content
            return httpx.Response(201, json={'uuid': file_id, 'size': len(request.content),
                                            'sha256': hashlib.sha256(request.content).hexdigest()})
        if (request.method, path) == ('POST', 'instances'):
            operation = str(uuid4())
            code = payload['args'][-1] if '-c' in payload['args'] else self.files[payload['files'][GUEST_EXAMPLE]['uuid']].decode()
            status, result_image, exit_code, stdout, stderr = 'SUCCESS', None, 0, '', ''
            if code == PROBES['capability']['code']:
                stdout = json.dumps({'python': [3, 12], 'euid': 65534, 'interfaces': ['lo']}) + '\n'
            elif code == PROBES['artifact']['code']:
                result_image = RETAINED
            elif code == PROBES['cancellation']['code']:
                status, exit_code = 'EXECUTING', None
            else:
                hashes = {name: hashlib.sha256(self.files[value['uuid']]).hexdigest()
                          for name, value in payload['files'].items()}
                matches = [phase for phase in self.plan['phases']
                           if phase['files'] == hashes and phase['environment'] == {'DOCDRIFT_INPUT': payload['env']['DOCDRIFT_INPUT']}]
                assert matches, 'Unexpected verifier bytes must not be accepted by the synthetic fixture'
                phase = matches[0]
                if phase['phase'].split('/')[0] in {'baseline_target', 'confirm_original', 'final_original'}:
                    exit_code, stderr = 1, 'Synthetic frozen original AttributeError; no code executed.\n'
                else:
                    spec = self.profile['examples'][0 if phase['phase'].startswith('final_repaired/') else 1]
                    case = next(case for case in spec['cases'] if case['id'] == phase['case_id'])
                    stdout = json.dumps(case['expected_json'], ensure_ascii=False) + '\n'
            self.operations[operation] = {
                'uuid': operation, 'kind': 'instance', 'status': status,
                'image_uuid': IMAGE, 'result_image_uuid': result_image, 'duration': 0.1,
                'metadata': {**payload, 'result': {
                    'state': {'exit_code': exit_code, 'signal': -1, 'timed_out': False},
                    'stdout': self.stream(stdout), 'stderr': self.stream(stderr), 'resources': {},
                }},
            }
            return httpx.Response(201, json={'uuid': operation})
        if path.startswith('operations/'):
            operation = path.removeprefix('operations/')
            assert operation in self.operations
            if request.method == 'DELETE':
                self.operations[operation]['status'] = 'CANCELLED'
                self.operations[operation]['metadata']['result']['state']['signal'] = 15
                return httpx.Response(202)
            assert request.method == 'GET'
            return httpx.Response(200, json=self.operations[operation])
        if (request.method, path) == ('GET', f'inspect/{RETAINED}/download'):
            assert dict(request.url.params) == {'path': ARTIFACT_PATH}
            return httpx.Response(200, content=ARTIFACT_BYTES)
        raise AssertionError(f'Out-of-scope synthetic wire request: {request.method} {path}')


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    plan_root = tmp_path / 'plan'
    plan = prepare_f6_plan(plan_root, ROOT / 'docs/demo/f6/agent/evidence.zip',
                           ROOT / 'docs/demo/f6/proposals/agent.json')
    coverage = tmp_path / 'synthetic-coverage.json'
    coverage.write_text(json.dumps({
        'kind': 'docdrift_sandbox_credit_coverage', 'project_id': PROJECT_ID, 'personal_spend_limit': 0,
        'execution': 'free_or_grant_covered', 'image_import': 'free_or_grant_covered', 'storage': 'free_or_grant_covered',
        'confirmation': 'Synthetic test fixture only; no assertion about actual billing coverage.',
        'confirmed_at_utc': '2026-10-16T12:00:00+00:00',
    }))
    coverage.chmod(0o600)
    state = tmp_path / 'state'
    wire = SyntheticWire(plan_root, plan, state)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda _, request: wire.handle(request))
    def no_socket(*args, **kwargs):
        raise AssertionError('Synthetic wire tests must never open sockets')
    monkeypatch.setattr(socket, 'socket', no_socket)
    kwargs = {'api_key': 'synthetic-fixed-f6-test-key', 'project_id': PROJECT_ID,
              'plan_root': plan_root, 'state_root': state, 'registry_image': REGISTRY,
              'coverage_path': coverage}
    return SimpleNamespace(plan_root=plan_root, plan=plan, state=state, coverage=coverage,
                           wire=wire, kwargs=kwargs)


def bound_run(prepared, remote):
    remote.import_image()
    remote.run_probe('capability')
    adapter = F6ExecutionAdapter(remote)
    run_id = initialize_f6_run(prepared.plan_root, prepared.state, IMAGE, adapter.execution_contract)
    remote.bind_run(run_id)
    example = extract_examples('README.md', (prepared.plan_root / 'original/README.md').read_bytes())[0]
    phase = prepared.plan['phases'][0]
    request = ExecutionRequest(prepared.plan_root / 'original', example.code, phase['environment'], IMAGE)
    return adapter, run_id, request, phase['phase']


@pytest.mark.parametrize('billing_mode', ['confirmed', 'scoped'])
def test_full_isolated_lifecycle_and_completed_resume_do_not_repeat_mutations(prepared, billing_mode):
    if billing_mode == 'scoped':
        scoped_authorization(prepared)
    original_hashes = file_hashes(prepared.plan_root)
    with F6SandboxRemote(**prepared.kwargs) as remote:
        assert prepared.wire.requests == []
        billing = remote.billing_authorization
        assert billing['credit_coverage_confirmed'] is (billing_mode == 'confirmed')
        assert billing['personal_spend_limit'] == (0 if billing_mode == 'confirmed' else None)
        assert billing['user_authorized_scoped_run'] is (billing_mode == 'scoped')
        assert billing['billing_coverage'] == ('free_or_grant_covered' if billing_mode == 'confirmed' else 'unverified')
        assert 'confirmation' not in billing and 'authorization' not in billing
        if billing_mode == 'scoped':
            assert billing['source_run_id'] == F6_RUN_ID and billing['limits'] == SCOPED_LIMITS
            changed_facts = remote.billing_authorization
            changed_facts['limits']['inference_calls'] = 99
            assert remote.billing_authorization == billing
        assert remote.import_image() == IMAGE
        assert remote.run_probe('capability').execution_passed
        assert remote.run_probe('artifact').execution_passed
        assert remote.download_probe_artifact() == ARTIFACT_BYTES
        assert remote.run_probe('cancellation').service_state == 'EXECUTING'
        assert remote.cancel_probe().service_state == 'CANCELLED'
        adapter = F6ExecutionAdapter(remote)
        assert adapter.execution_contract['synthetic'] is False
        assert 'code_executions' not in adapter.execution_contract
        assert adapter.execution_contract['billing_authorization'] == billing
        run_id = initialize_f6_run(prepared.plan_root, prepared.state, IMAGE, adapter.execution_contract)
        remote.bind_run(run_id)
        result = resume_run(run_id, prepared.state, adapter=adapter)
        assert result['status'] == 'completed' and result['repair_verdict'] == 'behavior_verified'
        assert result['usage']['compute_operations'] == 12
        assert result['usage']['inference_calls'] == result['usage']['paid_calls'] == 0
        assert result['protected_hashes_preserved'] is True
        assert {key: result['environment'][key] for key in billing} == billing
        assert remote.operation_counts == {'image_imports': 1, 'runtime_probes': 3, 'verifier_operations': 12}
        assert verify_evidence(prepared.state / 'runs' / run_id / 'evidence.zip')['status'] == 'integrity_verified'
        with zipfile.ZipFile(prepared.state / 'runs' / run_id / 'evidence.zip') as archive:
            saved_report = json.loads(archive.read('report.json'))
            ledger = json.loads(archive.read('ledger.json'))
            commands = json.loads(archive.read('commands.json'))['operations']
        assert {key: saved_report['environment'][key] for key in billing} == billing
        assert ledger['metadata']['execution_contract']['billing_authorization'] == billing
        assert all(command['billing_authorization'] == billing for command in commands)
    counts = prepared.wire.counts()
    assert counts['POST', 'images/import'] == 1
    assert counts['POST', 'instances'] == 15
    assert counts['POST', 'files'] == 10
    assert sum(count for (method, _), count in counts.items() if method == 'DELETE') == 1
    with F6SandboxRemote(**prepared.kwargs) as remote:
        assert remote.import_image() == IMAGE
        for name in ('capability', 'artifact', 'cancellation'):
            remote.run_probe(name)
        assert remote.download_probe_artifact() == ARTIFACT_BYTES
        assert remote.cancel_probe().service_state == 'CANCELLED'
        assert resume_run(remote.run_id, prepared.state, adapter=F6ExecutionAdapter(remote)) == result
    after = prepared.wire.counts()
    assert {key: value for key, value in after.items() if key[0] != 'GET'} == {
        key: value for key, value in counts.items() if key[0] != 'GET'}
    assert file_hashes(prepared.plan_root) == original_hashes


def test_scoped_authorization_preserves_exact_record_bytes_and_coverage_hash_binding(prepared):
    scoped_authorization(prepared)
    content = prepared.coverage.read_bytes()
    assert _coverage(prepared.coverage, PROJECT_ID) == content
    with F6SandboxRemote(**prepared.kwargs) as remote:
        identity = json.loads((prepared.state / 'session.json').read_text())['identity']
        assert identity['coverage_sha256'] == hashlib.sha256(content).hexdigest()
        assert set(identity) == {'kind', 'project_id', 'plan_sha256', 'registry_image', 'coverage_sha256'}
        prepared.coverage.write_bytes(content + b'\n')
        with pytest.raises(SubmissionConflict, match='coverage changed'):
            remote.import_image()
        assert prepared.wire.requests == []
    with pytest.raises(SubmissionConflict, match='coverage changed'):
        F6SandboxRemote(**prepared.kwargs)
    assert prepared.wire.requests == []


@pytest.mark.parametrize('field,replacement', [
    ('kind', 'docdrift_sandbox_general_authorization'),
    ('project_id', 'different-project'),
    ('billing_coverage', 'free_or_grant_covered'),
    ('source_run_id', 'different-run'),
    ('authorization', ''),
    ('authorization', '  '),
    ('authorization', True),
    ('authorized_at_utc', None),
    ('authorized_at_utc', 'not-a-timestamp'),
    ('authorized_at_utc', '2026-10-16T12:00:00'),
    ('authorized_at_utc', '2026-10-16T12:00:00+01:00'),
    ('limits', None),
    ('limits', []),
    ('limits', {key: value for key, value in SCOPED_LIMITS.items() if key != 'inference_calls'}),
    ('limits', {**SCOPED_LIMITS, 'additional_operations': 1}),
    ('personal_spend_limit', 0),
    *[('limits', {**SCOPED_LIMITS, key: value + 1}) for key, value in SCOPED_LIMITS.items()],
    ('limits', {**SCOPED_LIMITS, 'image_imports': True}),
    ('limits', {**SCOPED_LIMITS, 'runtime_probes': 3.0}),
    ('limits', {**SCOPED_LIMITS, 'inference_calls': False}),
])
def test_malformed_or_expanded_scoped_authorization_refuses_before_client_or_state(
        prepared, monkeypatch, field, replacement):
    value = scoped_authorization(prepared)
    value[field] = replacement
    prepared.coverage.write_text(json.dumps(value))
    def no_client(*args, **kwargs):
        raise AssertionError('Invalid scoped authorization must be checked before client construction')
    monkeypatch.setattr(httpx.Client, '__init__', no_client)
    with pytest.raises(ValueError):
        F6SandboxRemote(**prepared.kwargs)
    assert prepared.wire.requests == [] and not prepared.state.exists()


def test_future_scoped_authorization_refuses_before_client_or_state(prepared, monkeypatch):
    value = scoped_authorization(prepared)
    value['authorized_at_utc'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    prepared.coverage.write_text(json.dumps(value))
    def no_client(*args, **kwargs):
        raise AssertionError('Future authorization must be checked before client construction')
    monkeypatch.setattr(httpx.Client, '__init__', no_client)
    with pytest.raises(ValueError, match='UTC timestamp'):
        F6SandboxRemote(**prepared.kwargs)
    assert prepared.wire.requests == [] and not prepared.state.exists()


@pytest.mark.parametrize('field', ['coverage_path', 'project_id'])
def test_unconfirmed_scope_refuses_before_client_construction_or_state(prepared, monkeypatch, field):
    kwargs = dict(prepared.kwargs)
    kwargs[field] = prepared.coverage.with_name('missing.json') if field == 'coverage_path' else 'different-project'
    def no_client(*args, **kwargs):
        raise AssertionError('Unconfirmed scope must be checked before constructing a client')
    monkeypatch.setattr(httpx.Client, '__init__', no_client)
    with pytest.raises(ValueError):
        F6SandboxRemote(**kwargs)
    assert prepared.wire.requests == [] and not prepared.state.exists()


def test_session_lock_prevents_concurrent_activation_and_releases_after_close(prepared):
    with F6SandboxRemote(**prepared.kwargs):
        with pytest.raises(SubmissionConflict, match='holds this state directory'):
            F6SandboxRemote(**prepared.kwargs)
        assert prepared.wire.requests == []
    with F6SandboxRemote(**prepared.kwargs):
        assert prepared.wire.requests == []


def test_fixed_activation_does_not_enable_the_ordinary_simulation_bridge(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(RemoteMutationsDisabled):
            SandboxExecutionAdapter(remote)
    assert prepared.wire.requests == []


@pytest.mark.parametrize('change', ['code', 'environment', 'phase', 'image'])
def test_changed_verifier_inputs_are_refused_before_upload_or_submission(prepared, change):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        adapter, run_id, request, phase = bound_run(prepared, remote)
        before = list(prepared.wire.requests)
        if change == 'code':
            request = replace(request, code=request.code + '\nprint("extra")\n')
        elif change == 'environment':
            request = replace(request, environment={'DOCDRIFT_INPUT': '["unapproved"]'})
        elif change == 'phase':
            phase = 'unapproved/operation'
        else:
            request = replace(request, image=RETAINED)
        with pytest.raises((RemoteAdapterError, ValueError)):
            adapter.execute(request, lambda _: None, run_id=run_id, phase=phase)
        assert prepared.wire.requests == before


@pytest.mark.parametrize('change', ['mount', 'transport', 'authorization', 'project', 'base_url'])
def test_changed_client_cannot_route_requests_outside_the_fixed_scope(prepared, change):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        original_transport = remote._client._transport
        original_mounts = dict(remote._client._mounts)
        original_headers = dict(remote._client.headers)
        original_url = remote._client.base_url
        try:
            if change == 'mount':
                remote._client._mounts[object()] = httpx.MockTransport(lambda _: pytest.fail('foreign request'))
            elif change == 'transport':
                remote._client._transport = httpx.MockTransport(lambda _: pytest.fail('foreign request'))
            elif change == 'authorization':
                remote._client.headers['Authorization'] = 'Bearer changed-test-key'
            elif change == 'project':
                remote._client.headers['Project'] = 'different-project'
            else:
                remote._client.base_url = 'https://example.invalid/'
            with pytest.raises(RemoteAdapterError, match='transport_changed'):
                remote.import_image()
            assert prepared.wire.requests == []
        finally:
            remote._client._transport = original_transport
            remote._client._mounts = original_mounts
            remote._client.headers.clear()
            remote._client.headers.update(original_headers)
            remote._client.base_url = original_url


@pytest.mark.parametrize('change', ['source', 'coverage'])
def test_changed_approved_bytes_block_even_after_client_is_constructed(prepared, change):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        path = prepared.plan_root / 'original/drift_demo/__init__.py' if change == 'source' else prepared.coverage
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b'\n')
        with pytest.raises(ValueError):
            remote.import_image()
        assert prepared.wire.requests == []


@pytest.mark.parametrize('path', ['images/import', 'instances', 'files'])
def test_ambiguous_mutation_is_never_repeated_after_restart(prepared, path):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        if path != 'images/import':
            remote.import_image()
        prepared.wire.fail_once = ('POST', path)
        with pytest.raises(RemoteAdapterError):
            if path == 'images/import':
                remote.import_image()
            else:
                remote.run_probe('capability' if path == 'instances' else 'artifact')
    before = prepared.wire.counts()['POST', path]
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(UncertainSubmission):
            if path == 'images/import':
                remote.import_image()
            else:
                remote.run_probe('capability' if path == 'instances' else 'artifact')
    assert prepared.wire.counts()['POST', path] == before == 1


def test_uncertain_cancellation_reconciles_known_id_without_second_delete(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        result = remote.run_probe('cancellation')
        prepared.wire.fail_once = ('DELETE', f'operations/{result.operation_id}')
        with pytest.raises(RemoteAdapterError):
            remote.cancel_probe()
    with F6SandboxRemote(**prepared.kwargs) as remote:
        assert remote.cancel_probe().service_state == 'CANCELLED'
    assert prepared.wire.counts()['DELETE', f'operations/{result.operation_id}'] == 1


def unassigned_probe_response(prepared, monkeypatch, name, status):
    """Use the documented nullable image shape; no live result is replayed."""
    original = prepared.wire.response
    def response(request, path, payload):
        returned = original(request, path, payload)
        if (request.method == 'POST' and path == 'instances'
                and payload['args'] == ['-B', '-c', PROBES[name]['code']]):
            operation = prepared.wire.operations[returned.json()['uuid']]
            operation.update(status=status, image_uuid=None, result_image_uuid=None)
        return returned
    monkeypatch.setattr(prepared.wire, 'response', response)


@pytest.mark.parametrize('lost_cancellation_response', [False, True])
def test_cancellation_before_image_assignment_recovers_without_repeat_mutations(
        prepared, monkeypatch, lost_cancellation_response):
    unassigned_probe_response(prepared, monkeypatch, 'cancellation', 'PENDING')
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        remote.run_probe('capability')
        queued = remote.run_probe('cancellation')
        assert queued.service_state == 'PENDING' and queued.image_id is None
        if lost_cancellation_response:
            prepared.wire.fail_once = ('DELETE', f'operations/{queued.operation_id}')
            with pytest.raises(RemoteAdapterError):
                remote.cancel_probe()
        else:
            cancelled = remote.cancel_probe()
            assert cancelled.service_state == 'CANCELLED' and cancelled.image_id is None
            assert F6ExecutionAdapter(remote).preflight(IMAGE)['python_capability_tested']
    before = prepared.wire.counts()
    with F6SandboxRemote(**prepared.kwargs) as remote:
        assert remote.import_image() == IMAGE
        cancelled = remote.cancel_probe()
        assert cancelled.service_state == 'CANCELLED' and cancelled.image_id is None
        assert remote.run_probe('cancellation').service_state == 'CANCELLED'
        assert F6ExecutionAdapter(remote).preflight(IMAGE)['python_capability_tested']
    after = prepared.wire.counts()
    assert after['DELETE', f'operations/{queued.operation_id}'] == 1
    assert {key: count for key, count in after.items() if key[0] != 'GET'} == {
        key: count for key, count in before.items() if key[0] != 'GET'}


@pytest.mark.parametrize('name,status', [
    ('capability', 'CANCELLED'), ('artifact', 'CANCELLED'),
    ('cancellation', 'SUCCESS'), ('cancellation', 'FAILED'), ('cancellation', 'CANCELLED'),
])
def test_unrelated_terminal_probes_without_images_remain_rejected(prepared, monkeypatch, name, status):
    unassigned_probe_response(prepared, monkeypatch, name, status)
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        if name == 'capability':
            with pytest.raises(RemoteAdapterError, match='capability_not_confirmed'):
                remote.run_probe(name)
        else:
            remote.run_probe(name)
        before = list(prepared.wire.requests)
        with pytest.raises(SubmissionConflict, match='differs from its durable receipt'):
            remote.import_image()
        assert prepared.wire.requests == before
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(SubmissionConflict, match='differs from its durable receipt'):
            remote.import_image()
    assert prepared.wire.requests == before


def test_cancelled_probe_cannot_drop_an_image_recorded_in_its_terminal_receipt(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        remote.run_probe('cancellation')
        assert remote.cancel_probe().image_id == IMAGE
        session_path = prepared.state / 'session.json'
        session = json.loads(session_path.read_text())
        session['probes']['cancellation']['image_id'] = None
        session_path.write_text(json.dumps(session))
        before = list(prepared.wire.requests)
        with pytest.raises(SubmissionConflict, match='differs from its durable receipt'):
            remote.import_image()
        assert prepared.wire.requests == before


def test_accepted_verifier_callback_interruption_resumes_same_operation(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        adapter, run_id, request, phase = bound_run(prepared, remote)
        def interrupted(operation_id):
            assert SubmissionJournal(prepared.state).get(remote.journal.for_run(run_id)[0]['attempt_id'])['operation_id'] == operation_id
            raise RuntimeError('Synthetic local callback interruption')
        with pytest.raises(RemoteAdapterError, match='acceptance_callback_failed'):
            adapter.execute(request, interrupted, run_id=run_id, phase=phase)
    before = prepared.wire.counts()
    with F6SandboxRemote(**prepared.kwargs) as remote:
        adapter = F6ExecutionAdapter(remote)
        result = adapter.execute(request, lambda _: None, run_id=run_id, phase=phase)
        assert result.exit_code == 1
    after = prepared.wire.counts()
    assert after['POST', 'instances'] == before['POST', 'instances']
    assert after['POST', 'files'] == before['POST', 'files']


def test_journal_receipts_exist_before_import_and_instance_post(prepared):
    observed = []
    def before_request(method, path, payload):
        if method == 'POST' and path in {'images/import', 'instances'}:
            journal = SubmissionJournal(prepared.state)
            import sqlite3
            with sqlite3.connect(journal.path) as connection:
                assert connection.execute("SELECT count(*) FROM remote_submissions WHERE state='submitting'").fetchone()[0] == 1
            observed.append(path)
        elif method == 'POST' and path == 'files':
            session = json.loads((prepared.state / 'session.json').read_text())
            assert any(upload['state'] == 'submitting' for upload in session['uploads'].values())
            observed.append(path)
        elif method == 'DELETE':
            session = json.loads((prepared.state / 'session.json').read_text())
            assert session['cancellation_requested'] is True
            observed.append('cancel')
    prepared.wire.before_request = before_request
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        remote.run_probe('capability')
        remote.run_probe('artifact')
        remote.run_probe('cancellation')
        remote.cancel_probe()
    assert observed == ['images/import', 'instances', 'files', 'instances', 'instances', 'cancel']


def test_rejected_import_attempt_remains_consumed_on_restart(prepared):
    prepared.wire.reject_once = ('POST', 'images/import')
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(RemoteAdapterError, match='http_403'):
            remote.import_image()
        assert remote.operation_counts['image_imports'] == 1
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(UncertainSubmission, match='saved_import_cannot_retry'):
            remote.import_image()
        assert remote.operation_counts['image_imports'] == 1
    assert prepared.wire.counts()['POST', 'images/import'] == 1


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED'])
def test_terminal_unsuccessful_import_resumes_without_requests_or_receipt_changes(prepared, status):
    original_response = prepared.wire.response

    def terminal_import(request, path, payload):
        response = original_response(request, path, payload)
        if (request.method, path) == ('POST', 'images/import'):
            operation = prepared.wire.operations[response.json()['uuid']]
            operation.update(status=status, result_image_uuid=None, result={'image': None},
                             error='Synthetic private importer detail; never report this text.')
        return response

    prepared.wire.response = terminal_import
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(RemoteAdapterError, match='import_not_successful') as first:
            remote.import_image()
        assert first.value.operation_id is not None
        assert first.value.attempt_id is not None
        receipt = remote.journal.get(first.value.attempt_id)
        assert receipt['state'] == 'completed'
        assert receipt['result_metadata']['service_state'] == status
        assert remote.operation_counts == {'image_imports': 1, 'runtime_probes': 0, 'verifier_operations': 0}

    operation_path = prepared.state / 'operations' / (first.value.operation_id + '.json')
    operation_bytes = operation_path.read_bytes()
    requests = list(prepared.wire.requests)
    prepared.wire.operations.clear()  # Even an expired provider operation must not be polled again.
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(RemoteAdapterError, match='import_not_successful') as resumed:
            remote.import_image()
        assert resumed.value.operation_id == first.value.operation_id
        assert resumed.value.attempt_id == first.value.attempt_id
        assert remote.journal.get(first.value.attempt_id) == receipt
        assert remote.operation_counts == {'image_imports': 1, 'runtime_probes': 0, 'verifier_operations': 0}
        assert remote.image_id is None
        assert remote.run_id is None
    assert prepared.wire.requests == requests
    assert operation_path.read_bytes() == operation_bytes


def test_foreign_operation_cannot_be_observed_or_cancelled(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        with pytest.raises(RemoteAdapterError, match='read_out_of_scope'):
            remote.observe(str(uuid4()), timeout_seconds=0)
        with pytest.raises(RemoteAdapterError, match='cancel_out_of_scope'):
            remote.cancel(str(uuid4()))
        assert prepared.wire.requests == []


def test_synthetic_result_cannot_be_relabelled_as_live_execution(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        result = remote.run_probe('capability')
        with pytest.raises(RemoteAdapterError, match='synthetic_result_forbidden'):
            F6ExecutionAdapter._result(replace(result, synthetic=True))


def test_cached_plan_cannot_expand_live_scope(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.plan['phases'].append(dict(remote.plan['phases'][0], phase='unapproved/operation'))
        with pytest.raises(ValueError):
            remote.import_image()
        assert prepared.wire.requests == []


def test_session_image_must_match_completed_import_receipt(prepared):
    with F6SandboxRemote(**prepared.kwargs) as remote:
        remote.import_image()
        before = list(prepared.wire.requests)
        session_path = prepared.state / 'session.json'
        session = json.loads(session_path.read_text())
        session.update(image_id=RETAINED, imported_image_id=RETAINED)
        session_path.write_text(json.dumps(session))
        with pytest.raises(SubmissionConflict, match='durable receipt'):
            remote.import_image()
        assert prepared.wire.requests == before
