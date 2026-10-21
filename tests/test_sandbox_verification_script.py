"""The fixed saved-repair workflow must stop before unconfirmed provider use."""

import json
import hashlib
from contextlib import closing
from pathlib import Path
import runpy
import socket
import sqlite3
import subprocess
import sys

import httpx
import pytest

from docdrift.nebius import RemoteAdapterError
from docdrift.sandbox_plan import F6_RUN_ID, prepare_f6_plan, validate_f6_plan
from docdrift.snapshot import file_hashes


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(ROOT / 'scripts/verify_saved_f6_sandbox.py'))


def deny_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No provider request, guest execution, or subprocess is authorized here')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(httpx.Client, '__init__', forbidden)


def command(monkeypatch, tmp_path, name, *extra):
    monkeypatch.setattr(sys, 'argv', [
        'verify_saved_f6_sandbox.py', name,
        '--plan-root', str(tmp_path / 'plan'),
        '--state-root', str(tmp_path / 'state'),
        '--coverage', str(tmp_path / 'coverage.json'),
        *map(str, extra),
    ])
    return SCRIPT['main']()


def test_prepare_works_outside_checkout_with_network_and_processes_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'prepared_offline'
    assert result['provider_requests'] == result['current_inference_calls'] == 0
    assert result['verifier_operation_limit'] == 12
    assert result['runtime_probe_limit'] == 3
    assert result['private_image_import_limit'] == 1
    assert '@sha256:' in result['registry_image']
    assert len(validate_f6_plan(tmp_path / 'plan')['phases']) == 12
    assert not (tmp_path / 'state').exists()


def test_run_without_coverage_stops_before_key_lookup_client_or_state(tmp_path, monkeypatch, capsys):
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'run') == 2
    message = capsys.readouterr().err
    assert 'credit coverage is unconfirmed' in message
    assert 'no provider request was made' in message
    assert not (tmp_path / 'state').exists()


def test_unconfirmed_coverage_cannot_become_a_live_switch(tmp_path, monkeypatch, capsys):
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    (tmp_path / 'coverage.json').write_text(json.dumps({
        'kind': 'docdrift_sandbox_credit_coverage',
        'project_id': SCRIPT['PROJECT'], 'personal_spend_limit': 0,
        'execution': 'unknown', 'image_import': 'unknown', 'storage': 'unknown',
        'confirmation': 'Access works; coverage has not been established.',
        'confirmed_at_utc': '2026-10-16T00:00:00+00:00',
    }))
    (tmp_path / 'coverage.json').chmod(0o600)
    monkeypatch.setenv('NEBIUS_API_KEY', 'synthetic-not-a-real-provider-key')
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'run') == 2
    message = capsys.readouterr().err.lower()
    assert 'coverage' in message or 'covered' in message
    assert not (tmp_path / 'state').exists()


def test_changed_source_is_rejected_before_missing_coverage_or_provider(tmp_path, monkeypatch, capsys):
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    source = tmp_path / 'plan/original/drift_demo/__init__.py'
    source.chmod(0o600)
    source.write_bytes(source.read_bytes() + b'\n# changed after approval\n')
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'run') == 2
    assert 'pinned published bytes' in capsys.readouterr().err
    assert not (tmp_path / 'state').exists()


@pytest.mark.parametrize('code,identities', [
    ('import_acceptance_persistence_failed', {
        'operation_id': '11111111-1111-4111-8111-111111111111',
        'attempt_id': '22222222-2222-4222-8222-222222222222',
    }),
    ('acceptance_persistence_failed', {
        'operation_id': '33333333-3333-4333-8333-333333333333',
        'attempt_id': '44444444-4444-4444-8444-444444444444',
    }),
    ('synthetic_invalid_error_ids', {
        'operation_id': 'synthetic-private-value\nAuthorization: synthetic-secret',
        'attempt_id': '00000000-0000-0000-0000-000000000000',
    }),
])
@pytest.mark.parametrize('report_write_fails', [False, True])
@pytest.mark.parametrize('billing_mode', ['confirmed', 'scoped'])
def test_known_acceptance_ids_survive_runner_errors_without_exposing_other_data(
        tmp_path, monkeypatch, capsys, code, identities, report_write_fails, billing_mode):
    """Inject a local adapter failure; no acceptance or provider call occurs."""
    import docdrift.sandbox_live as live

    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    authorization = {
        'kind': 'docdrift_sandbox_credit_coverage', 'project_id': SCRIPT['PROJECT'],
        'personal_spend_limit': 0, 'execution': 'free_or_grant_covered',
        'image_import': 'free_or_grant_covered', 'storage': 'free_or_grant_covered',
        'confirmation': 'Synthetic test only; no actual coverage assertion.',
        'confirmed_at_utc': '2026-10-21T00:00:00+00:00',
    }
    billing_facts = {'credit_coverage_confirmed': True, 'personal_spend_limit': 0}
    if billing_mode == 'scoped':
        authorization = {
            'kind': 'docdrift_sandbox_scoped_authorization', 'project_id': SCRIPT['PROJECT'],
            'billing_coverage': 'unverified', 'source_run_id': '4fd82cb8be7a449e8815d5366665f4ac',
            'limits': {'image_imports': 1, 'runtime_probes': 3, 'verifier_operations': 12, 'inference_calls': 0},
            'authorization': 'Synthetic test only; user permission is not credit coverage.',
            'authorized_at_utc': '2026-10-21T00:00:00+00:00',
        }
        billing_facts = {'credit_coverage_confirmed': False, 'personal_spend_limit': None,
                         'billing_coverage': 'unverified', 'user_authorized_scoped_run': True}
    (tmp_path / 'coverage.json').write_text(json.dumps(authorization))
    (tmp_path / 'coverage.json').chmod(0o600)
    monkeypatch.setenv('NEBIUS_API_KEY', 'synthetic-not-a-real-provider-key')
    deny_side_effects(monkeypatch)
    if report_write_fails:
        original_write = SCRIPT['verification'].__globals__['write_json']
        def failed_error_report(path, value):
            if 'error' in value:
                raise OSError('Synthetic error-report storage failure')
            original_write(path, value)
        monkeypatch.setitem(SCRIPT['verification'].__globals__, 'write_json', failed_error_report)

    class FailingRemote:
        billing_authorization = billing_facts

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def import_image(self):
            raise RemoteAdapterError(code, **identities)

        @property
        def operation_counts(self):
            return {'image_imports': 0, 'runtime_probes': 0, 'verifier_operations': 0}

    monkeypatch.setattr(live, 'F6SandboxRemote', FailingRemote)
    assert command(monkeypatch, tmp_path, 'run') == 2
    output = capsys.readouterr()
    report_text = (tmp_path / 'state/runtime-report.json').read_text()
    report = json.loads(report_text)
    expected_ids = identities if code != 'synthetic_invalid_error_ids' else {}
    assert report['status'] == 'incomplete'
    assert report['billing_authorization'] == billing_facts
    assert report['billed_amount'] is None and report['billed_amount_status'] == 'unverified'
    if report_write_fails:
        assert 'error' not in report and 'error_context' not in report
    else:
        assert report['error'] == code and report['error_context'] == expected_ids
    assert output.out == ''
    assert output.err.strip() == code + ''.join(f' {name}={value}' for name, value in expected_ids.items())
    assert 'synthetic-not-a-real-provider-key' not in output.err + report_text
    assert 'synthetic-private-value' not in output.err + report_text
    assert 'Authorization' not in output.err + report_text


def synthetic_image_listing(monkeypatch, values):
    requests = []
    def handle(transport, request):
        assert request.method == 'GET'
        assert request.url.path == '/sandboxes/v1/images'
        assert dict(request.url.params) == {'tag': 'python', 'limit': '1000', 'offset': '0'}
        requests.append(request)
        return httpx.Response(200, json={'images': values})
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', handle)
    def no_side_effects(*args, **kwargs):
        raise AssertionError('Image discovery tests must not use sockets or subprocesses')
    monkeypatch.setattr(socket, 'socket', no_side_effects)
    monkeypatch.setattr(subprocess, 'Popen', no_side_effects)
    monkeypatch.setenv('NEBIUS_API_KEY', 'synthetic-image-discovery-key')
    return requests


@pytest.mark.parametrize('values', [[], [
    {'uuid': '22222222-2222-4222-8222-222222222222', 'tag': 'python:3.12-slim',
     'unknown_provider_field': 'synthetic-private-provider-data'},
    {'uuid': '11111111-1111-4111-8111-111111111111', 'tag': 'python:3.11'},
]])
def test_image_discovery_is_one_read_and_preserves_failed_import_state(
        tmp_path, monkeypatch, capsys, values):
    requests = synthetic_image_listing(monkeypatch, values)
    state = tmp_path / 'state'
    state.mkdir()
    receipt = state / 'session.json'
    receipt.write_bytes(b'Synthetic existing failed-import receipt; must remain unchanged.\n')
    before = {path.name: path.read_bytes() for path in state.iterdir()}
    assert command(monkeypatch, tmp_path, 'images') == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert output.err == '' and len(requests) == result['provider_requests'] == 1
    assert result['images'] == sorted(
        [{'uuid': row['uuid'], 'tag': row['tag']} for row in values],
        key=lambda row: (row['tag'], row['uuid']))
    assert result['image_imports'] == result['guest_executions'] == result['inference_calls'] == 0
    assert result['billing_coverage'] == 'unverified' and result['may_have_more'] is False
    record = Path(result['record_path'])
    assert json.loads(record.read_text()) == result
    assert record.stat().st_mode & 0o777 == 0o600
    assert 'synthetic-image-discovery-key' not in output.out
    assert 'synthetic-private-provider-data' not in output.out
    assert {path.name: path.read_bytes() for path in state.iterdir()} == before
    assert not (tmp_path / 'plan').exists()


@pytest.mark.parametrize('values', [None, {}, [{'uuid': 'bad-id', 'tag': 'python:3.12'}],
    [{'uuid': '11111111-1111-4111-8111-111111111111', 'tag': 'python:3.12\nprivate-data'}],
    [{'uuid': '11111111-1111-4111-8111-111111111111', 'tag': 'unrelated:latest'}],
])
def test_invalid_image_discovery_response_is_not_saved_or_echoed(tmp_path, monkeypatch, capsys, values):
    requests = synthetic_image_listing(monkeypatch, values)
    assert command(monkeypatch, tmp_path, 'images') == 2
    output = capsys.readouterr()
    assert len(requests) == 1 and output.out == ''
    assert output.err.strip() == 'invalid_image_list_response'
    assert not (tmp_path / 'access').exists() and not (tmp_path / 'state').exists()


def test_image_discovery_without_key_stops_before_client_or_state(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'images') == 2
    assert 'NEBIUS_API_KEY is required' in capsys.readouterr().err
    assert not (tmp_path / 'access').exists() and not (tmp_path / 'state').exists()


@pytest.fixture
def reuse_inputs(tmp_path):
    """Manufacture local records; the pinned IDs are synthetic values here."""
    from docdrift.remote_journal import SubmissionJournal
    from docdrift.sandbox_live import RECOVERY_FAILED_IMPORT_ID, RECOVERY_IMAGE_ID, _encoded

    plan = prepare_f6_plan(tmp_path / 'plan', ROOT / 'docs/demo/f6/agent/evidence.zip',
                           ROOT / 'docs/demo/f6/proposals/agent.json')
    authorization = {
        'kind': 'docdrift_sandbox_scoped_authorization', 'project_id': SCRIPT['PROJECT'],
        'billing_coverage': 'unverified', 'source_run_id': F6_RUN_ID,
        'limits': {'image_imports': 1, 'runtime_probes': 3, 'verifier_operations': 12, 'inference_calls': 0},
        'authorization': 'Synthetic test only; not a live user authorization.',
        'authorized_at_utc': '2026-10-21T00:00:00+00:00',
    }
    coverage = tmp_path / 'coverage.json'
    coverage.write_text(json.dumps(authorization))
    coverage.chmod(0o600)
    plan_digest = hashlib.sha256(_encoded(plan)).hexdigest()
    session = {
        'identity': {'kind': 'fixed_f6_sandbox_session', 'project_id': SCRIPT['PROJECT'],
                     'plan_sha256': plan_digest, 'registry_image': SCRIPT['REGISTRY_IMAGE'],
                     'coverage_sha256': hashlib.sha256(coverage.read_bytes()).hexdigest()},
        'image_id': None, 'imported_image_id': None, 'run_id': None, 'probes': {}, 'uploads': {},
    }
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'session.json').write_text(json.dumps(session))
    journal = SubmissionJournal(state)
    payload = {'registry': {'url': SCRIPT['REGISTRY_IMAGE']}, 'timeout': 120}
    receipt = journal.begin('f6_control_' + plan_digest[:16], 'image_import',
                            hashlib.sha256(_encoded(payload)).hexdigest())
    journal.accepted(receipt['attempt_id'], RECOVERY_FAILED_IMPORT_ID)
    journal.completed(receipt['attempt_id'], {'operation_id': RECOVERY_FAILED_IMPORT_ID,
                      'service_state': 'FAILED', 'state': 'failed'})
    operations = state / 'operations'
    operations.mkdir()
    (operations / (RECOVERY_FAILED_IMPORT_ID + '.json')).write_text(json.dumps({
        'uuid': RECOVERY_FAILED_IMPORT_ID, 'kind': 'image_import', 'status': 'FAILED',
        'result_image_uuid': None, 'result': {'image': None},
        'metadata': payload, 'error': 'Synthetic import failure; no provider call occurred.',
    }))
    inventory = tmp_path / 'inventory.json'
    inventory.write_text(json.dumps({
        'kind': 'sandbox_public_python_image_inventory', 'status': 'read_only_images_listed',
        'project_id': SCRIPT['PROJECT'], 'query': {'tag': 'python', 'limit': 1000, 'offset': 0},
        'images': [{'uuid': RECOVERY_IMAGE_ID, 'tag': 'python:3.12-slim'}],
        'provider_requests': 1, 'image_imports': 0, 'guest_executions': 0, 'inference_calls': 0,
        'note': 'Synthetic listing fixture only.',
    }))
    inventory.chmod(0o600)
    return {'state': state, 'inventory': inventory, 'image_id': RECOVERY_IMAGE_ID,
            'failed_id': RECOVERY_FAILED_IMPORT_ID, 'output': tmp_path / 'reuse.json'}


def reuse_command(monkeypatch, tmp_path, fixture, *extra):
    return command(monkeypatch, tmp_path, 'prepare-reuse',
                   '--inventory', fixture['inventory'], '--image-id', fixture['image_id'],
                   '--reuse-record', fixture['output'], *extra)


def durable_state_hashes(state):
    # A read-only SQLite connection may create/update transient WAL coordination
    # files. Compare the durable database, session, and operation records.
    return {name: digest for name, digest in file_hashes(state).items()
            if name not in {'state.sqlite3-shm', 'state.sqlite3-wal'}}


def test_prepare_reuse_freezes_inputs_offline_without_changing_live_state(
        tmp_path, monkeypatch, capsys, reuse_inputs):
    deny_side_effects(monkeypatch)
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    before = durable_state_hashes(reuse_inputs['state'])
    assert reuse_command(monkeypatch, tmp_path, reuse_inputs) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'prepared_image_reuse_offline'
    assert result['provider_requests'] == result['additional_imports'] == result['guest_executions'] == 0
    record_bytes = reuse_inputs['output'].read_bytes()
    record = json.loads(record_bytes)
    assert record['image_id'] == reuse_inputs['image_id']
    assert record['failed_import_operation_id'] == reuse_inputs['failed_id']
    assert record['inventory_sha256'] == hashlib.sha256(reuse_inputs['inventory'].read_bytes()).hexdigest()
    assert reuse_inputs['output'].stat().st_mode & 0o777 == 0o600
    assert reuse_command(monkeypatch, tmp_path, reuse_inputs) == 0
    assert reuse_inputs['output'].read_bytes() == record_bytes
    assert durable_state_hashes(reuse_inputs['state']) == before


@pytest.mark.parametrize('change', [
    'inventory', 'duplicate_image', 'bound_image', 'uncertain', 'result_image', 'authorization', 'orphan_run',
])
def test_prepare_reuse_rejects_changed_or_nonterminal_inputs_without_side_effects(
        tmp_path, monkeypatch, capsys, reuse_inputs, change):
    state = reuse_inputs['state']
    if change in {'inventory', 'duplicate_image'}:
        value = json.loads(reuse_inputs['inventory'].read_text())
        if change == 'inventory':
            value['images'] = []
        else:
            value['images'].append({'uuid': reuse_inputs['image_id'], 'tag': 'python:3.11'})
        reuse_inputs['inventory'].write_text(json.dumps(value))
    elif change == 'bound_image':
        path = state / 'session.json'
        value = json.loads(path.read_text())
        value['image_id'] = reuse_inputs['image_id']
        path.write_text(json.dumps(value))
    elif change == 'uncertain':
        with closing(sqlite3.connect(state / 'state.sqlite3')) as connection:
            connection.execute("UPDATE remote_submissions SET state='uncertain'")
            connection.commit()
    elif change == 'result_image':
        path = state / 'operations' / (reuse_inputs['failed_id'] + '.json')
        value = json.loads(path.read_text())
        value['result_image_uuid'] = reuse_inputs['image_id']
        path.write_text(json.dumps(value))
    elif change == 'authorization':
        with (tmp_path / 'coverage.json').open('a') as stream:
            stream.write('\n')
    else:
        from docdrift.store import StateStore
        StateStore(state).create_run('a' * 32, {})
    before = durable_state_hashes(state)
    deny_side_effects(monkeypatch)
    assert reuse_command(monkeypatch, tmp_path, reuse_inputs) == 2
    assert capsys.readouterr().err
    assert not reuse_inputs['output'].exists() and durable_state_hashes(state) == before


def test_prepare_reuse_does_not_accept_a_publicly_readable_existing_record(
        tmp_path, monkeypatch, capsys, reuse_inputs):
    deny_side_effects(monkeypatch)
    assert reuse_command(monkeypatch, tmp_path, reuse_inputs) == 0
    capsys.readouterr()
    content = reuse_inputs['output'].read_bytes()
    reuse_inputs['output'].chmod(0o644)
    assert reuse_command(monkeypatch, tmp_path, reuse_inputs) == 2
    assert capsys.readouterr().err
    assert reuse_inputs['output'].read_bytes() == content


def test_run_with_reuse_record_never_calls_the_import_path(tmp_path, monkeypatch, capsys, reuse_inputs):
    import docdrift.sandbox_live as live

    assert reuse_command(monkeypatch, tmp_path, reuse_inputs) == 0
    capsys.readouterr()
    calls = []
    class StoppedInspection:
        billing_authorization = {'billing_coverage': 'unverified', 'credit_coverage_confirmed': False,
                                 'personal_spend_limit': None}

        def __init__(self, **kwargs):
            assert kwargs['reuse_record_path'] == reuse_inputs['output']

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def select_existing_image(self):
            calls.append('inspect_existing')
            raise RemoteAdapterError('synthetic_inspection_stopped')

        def import_image(self):
            raise AssertionError('Existing-image recovery must never invoke an import')

        @property
        def operation_counts(self):
            return {'image_imports': 1, 'runtime_probes': 0, 'verifier_operations': 0}

    deny_side_effects(monkeypatch)
    monkeypatch.setenv('NEBIUS_API_KEY', 'synthetic-not-a-real-key')
    monkeypatch.setattr(live, 'F6SandboxRemote', StoppedInspection)
    assert command(monkeypatch, tmp_path, 'run', '--reuse-record', reuse_inputs['output']) == 2
    assert calls == ['inspect_existing']
    assert capsys.readouterr().err.strip() == 'synthetic_inspection_stopped'
    report = json.loads((reuse_inputs['state'] / 'runtime-report.json').read_text())
    assert report['failed_registry_image'] == SCRIPT['REGISTRY_IMAGE']
    assert 'registry_image' not in report and 'image_id' not in report
    assert report['operation_attempts']['image_imports'] == 1
