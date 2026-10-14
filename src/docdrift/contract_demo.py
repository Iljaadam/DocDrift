"""Offline Sandbox contract exercise. Synthetic responses; no code execution."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path

import httpx

from .engine import write_json
from .nebius import NebiusSandboxAdapter, RemoteAdapterError, RemoteExecutionRequest, UncertainSubmission
from .remote_journal import SubmissionConflict, SubmissionJournal
from .store import StateStore


IMAGE_ID = '11111111-1111-4111-8111-111111111111'
RESULT_IMAGE_ID = '22222222-2222-4222-8222-222222222222'
PROJECT_ID = '33333333-3333-4333-8333-333333333333'


def run_contract_demo(state_root: Path) -> dict:
    """Exercise persistence, result parsing, cancellation, and artifacts offline."""
    journal = SubmissionJournal(state_root)
    store = StateStore(state_root)
    run_id = uuid.uuid4().hex
    store.create_run(run_id, {'kind': 'offline_sandbox_contract', 'live_requests': 0, 'paid_calls': 0})
    requests: list[dict] = []
    operations: dict[str, dict] = {}
    instance_posts = 0
    artifact_content = b'{"synthetic":true,"artifact":"contract-only"}\n'

    def response_for(operation_id: str) -> dict:
        operation = operations[operation_id]
        result = None
        if operation['status'] == 'SUCCESS':
            failed = operation['exit_code'] != 0
            result = {
                'state': {'exit_code': operation['exit_code'], 'signal': None, 'timed_out': False},
                'stdout': {'value': base64.b64encode(b'' if failed else b'{}\n').decode(), 'encoding': 'base64', 'truncated': False},
                'stderr': {'value': base64.b64encode(b"AttributeError: 'WordCounter' object has no attribute 'tally'\n" if failed else b'').decode(), 'encoding': 'base64', 'truncated': False},
                'resources': {'cost': 123, 'cpu_time_ms': 10},
            }
        return {'uuid': operation_id, 'kind': 'instance', 'status': operation['status'], 'image_uuid': IMAGE_ID,
                'result_image_uuid': RESULT_IMAGE_ID if operation['retained'] and operation['status'] == 'SUCCESS' else None,
                'duration': 0.01, 'metadata': {'shell': False, 'preserve_env': False, 'disposable': not operation['retained'],
                'networking': {'enabled': False}, 'truncate_output_at': 262144, 'result': result}}

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal instance_posts
        path = request.url.path.removeprefix('/sandboxes/v1/')
        requests.append({'method': request.method, 'path': path})
        if request.method == 'GET' and path == 'whoami':
            return httpx.Response(200, json={'permissions': {'execute': True}, 'limits': {'max_concurrent_operations': 1}})
        if request.method == 'GET' and path == f'inspect/{IMAGE_ID}/':
            return httpx.Response(200, json={'uuid': IMAGE_ID})
        if request.method == 'POST' and path == 'files':
            return httpx.Response(201, json={'uuid': str(uuid.uuid4()), 'size': len(request.content), 'sha256': hashlib.sha256(request.content).hexdigest()})
        if request.method == 'POST' and path == 'instances':
            instance_posts += 1
            if instance_posts == 3:
                raise httpx.ReadTimeout('Synthetic ambiguous submission; no network request', request=request)
            payload = json.loads(request.content)
            assert payload['networking'] == {'enabled': False}
            assert payload['shell'] is False and payload['preserve_env'] is False
            operation_id = str(uuid.uuid4())
            operations[operation_id] = {'status': 'PENDING' if instance_posts == 1 else 'SUCCESS',
                'exit_code': 1 if instance_posts == 2 else 0, 'retained': not payload['disposable'], 'observations': 0}
            return httpx.Response(201, json={**payload, 'uuid': operation_id})
        if path.startswith('operations/'):
            operation_id = path.split('/')[1]
            operation = operations[operation_id]
            if request.method == 'DELETE':
                operation['status'] = 'CANCELLED'
                return httpx.Response(202)
            if request.method == 'GET':
                operation['observations'] += 1
                if operation['status'] == 'PENDING' and operation['observations'] > 1:
                    operation['status'] = 'SUCCESS'
                return httpx.Response(200, json=response_for(operation_id))
        if request.method == 'GET' and path == f'inspect/{RESULT_IMAGE_ID}/download':
            assert request.url.params['path'] == '/work/docdrift/artifact.json'
            return httpx.Response(200, content=artifact_content)
        raise AssertionError(f'Unexpected offline contract request: {request.method} {path}')

    transport = httpx.MockTransport(handle)

    def adapter():
        return NebiusSandboxAdapter('offline-placeholder-not-a-provider-key', PROJECT_ID,
            transport=transport, offline_simulation=True, journal=journal)

    with adapter() as first:
        preflight = first.preflight(IMAGE_ID)
        files = first.prepare({'/work/docdrift/example.py': b'print({})\n'})
        request = RemoteExecutionRequest(image_id=IMAGE_ID, executable='/usr/local/bin/python',
            args=('-B', '/work/docdrift/example.py'), files=files, environment={'DOCDRIFT_INPUT': '[]'}, disposable=True)

        def interrupted_callback(operation_id: str):
            assert journal.lookup(run_id, 'callback_recovery')['operation_id'] == operation_id
            raise RuntimeError('Synthetic controller interruption after durable acceptance')

        try:
            first.submit(request, interrupted_callback, run_id=run_id, phase='callback_recovery')
        except RemoteAdapterError as error:
            assert error.code == 'acceptance_callback_failed'
            accepted_id = error.operation_id
        else:
            raise AssertionError('The recovery exercise must interrupt after acceptance')

    with adapter() as recovered:
        receipt = recovered.recover(run_id, 'callback_recovery', expected_image_id=IMAGE_ID, expected_disposable=True)
        assert receipt['operation_id'] == accepted_id
        recovered_result = recovered.observe(accepted_id, poll_interval_seconds=0)
        failed_id = recovered.submit(RemoteExecutionRequest(image_id=IMAGE_ID, executable='/usr/local/bin/python',
            args=('-B', '/work/docdrift/example.py'), files=files, disposable=False), lambda _: None,
            run_id=run_id, phase='nonzero_process_exit')
        failed_result = recovered.observe(failed_id)
        artifacts = recovered.download(failed_id, ('/work/docdrift/artifact.json',))
        before_uncertain = instance_posts
        try:
            recovered.submit(request, lambda _: None, run_id=run_id, phase='ambiguous_submit')
        except UncertainSubmission:
            pass
        else:
            raise AssertionError('The timeout exercise must remain uncertain')
        try:
            recovered.submit(request, lambda _: None, run_id=run_id, phase='ambiguous_submit')
        except SubmissionConflict:
            pass
        else:
            raise AssertionError('Retrying an ambiguous POST must be refused')
        assert instance_posts == before_uncertain + 1
        cancel_id = recovered.submit(request, lambda _: None, run_id=run_id, phase='cancellation')
        recovered.cancel(cancel_id)
        cancellation = recovered.observe(cancel_id)

    assert recovered_result.execution_passed and not failed_result.execution_passed
    assert cancellation.state == 'cancelled' and not cancellation.execution_passed
    assert journal.lookup(run_id, 'ambiguous_submit')['state'] == 'uncertain'
    assert artifacts['/work/docdrift/artifact.json'] == artifact_content
    report = {
        'run_id': run_id, 'mode': 'offline_synthetic_contract', 'status': 'contract_checks_passed',
        'live_requests': 0, 'code_executions': 0, 'inference_calls': 0, 'paid_calls': 0,
        'provider_qualification': 'unconfirmed', 'behavior_verified': False,
        'note': 'All API responses, process streams, and resource values are synthetic contract examples. No repository code was executed.',
        'preflight': preflight,
        'checks': {'accepted_id_survived_callback_interruption': receipt['operation_id'] == accepted_id,
            'service_success_does_not_imply_exit_zero': failed_result.service_state == 'SUCCESS' and failed_result.exit_code == 1,
            'uncertain_submission_not_retried': instance_posts == 4,
            'cancellation_observed_terminal': cancellation.state == 'cancelled',
            'artifact_bytes_match': artifacts['/work/docdrift/artifact.json'] == artifact_content},
        'results': {'recovered': asdict(recovered_result), 'nonzero_exit': asdict(failed_result), 'cancelled': asdict(cancellation)},
        'resource_units': 'Raw provider fields; cost is not interpreted as dollars. Values in this demo are synthetic.',
        'artifacts': {'/work/docdrift/artifact.json': {'size': len(artifact_content), 'sha256': hashlib.sha256(artifact_content).hexdigest()}},
        'requests': requests, 'submission_receipts': journal.for_run(run_id),
    }
    directory = store.root / 'contracts' / run_id
    directory.mkdir(parents=True)
    write_json(directory / 'report.json', report)
    store.event(run_id, 'offline_contract_finished', {'status': report['status'], 'report': str(directory / 'report.json'), 'live_requests': 0})
    return {**report, 'report_path': str(directory / 'report.json')}
