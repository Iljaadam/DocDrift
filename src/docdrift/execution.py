"""Shared durable execution routing for verification and model exploration."""

from __future__ import annotations

from dataclasses import asdict
import json

from .adapters import ExecutionRequest, LocalDockerAdapter
from .snapshot import file_hashes, sha256
from .store import StateStore


def backend_name(adapter) -> str:
    return getattr(adapter, 'backend_name', None) or ('local_docker' if adapter is None or isinstance(adapter, LocalDockerAdapter) else type(adapter).__name__)


def is_simulated(adapter) -> bool:
    return getattr(adapter, 'synthetic', False) is True


def _validate_observation(adapter, result: dict, image: str) -> None:
    if result.get('image_id') != image:
        raise RuntimeError('Execution result came from a different environment image')
    if (result.get('synthetic', False) is True) != is_simulated(adapter):
        raise RuntimeError('Execution evidence type does not match its adapter')


def perform_execution(adapter, store: StateStore, run_id: str, phase: str, request: ExecutionRequest) -> dict:
    """Keep accepted identities before observation; never cache a client wait timeout."""
    digest = sha256(json.dumps({'files': file_hashes(request.snapshot), 'code': request.code,
                               'environment': dict(request.environment), 'image': request.image,
                               'timeout_seconds': request.timeout_seconds, 'log_limit_bytes': request.log_limit_bytes}, sort_keys=True).encode())
    identity_phase = 'execution_request/' + sha256(phase.encode())
    previous = store.run(run_id)['phases'].get(identity_phase)
    if previous and previous.get('sha256') != digest:
        raise RuntimeError('Saved execution phase inputs changed; automatic resubmission is forbidden')
    if previous is None:
        store.event(run_id, identity_phase, {'sha256': digest, 'phase': phase})
    existing = next((item for item in store.operations(run_id) if item['phase'] == phase), None)
    if existing and existing['result'] is not None:
        _validate_observation(adapter, existing['result'], request.image)
        return existing['result']
    scoped = getattr(adapter, 'scoped_execution', False) is True
    accepted = lambda operation_id: store.save_operation(run_id, phase, operation_id)
    if existing:
        if scoped:
            receipt = adapter.recover(run_id, phase, expected_image_id=request.image)
            if not receipt or receipt.get('operation_id') != existing['operation_id']:
                raise RuntimeError('Saved operation identity does not match its submission receipt')
        raw = adapter.observe(existing['operation_id'], timeout_seconds=request.timeout_seconds)
    elif scoped:
        raw = adapter.execute(request, accepted, run_id=run_id, phase=phase)
    else:
        raw = adapter.execute(request, accepted)
    result = asdict(raw)
    operation_id = result.get('operation_id')
    if not operation_id:
        raise RuntimeError('Missing operation identity; do not retry an uncertain submission')
    if not result.get('observation_timed_out') and result.get('state') != 'pending':
        store.complete_operation(run_id, operation_id, result)
    else:
        store.event(run_id, 'observation_incomplete', {'operation_id': operation_id, 'phase': phase})
    if hasattr(adapter, 'release'):
        adapter.release(result)
    else:
        adapter.cancel(operation_id)
        if hasattr(adapter, 'cleanup'):
            adapter.cleanup(operation_id)
    _validate_observation(adapter, result, request.image)
    return result
