"""Explicit, fixed-F6 Sandbox activation; no general live-execution switch.

Only the pinned saved repair, twelve approved verifier phases, one private OCI
import, and three capability probes can reach a provider transport. Merely
constructing this adapter never makes a request. Billing coverage is either a
separately recorded factual confirmation or explicitly unverified under the
user's bounded authorization; API access never establishes coverage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import fcntl
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

import httpx

from .adapters import ExecutionRequest
from .nebius import (
    BASE_URL, MAX_LOG_BYTES, NebiusSandboxAdapter, RemoteAdapterError,
    RemoteExecutionRequest, RemoteMutationsDisabled, RemoteResult, UncertainSubmission, UploadedFile,
)
from .profile import strict_json
from .remote_journal import SubmissionConflict, SubmissionJournal
from .sandbox_execution import (
    GUEST_EXAMPLE, GUEST_RUNNER, PYTHON_EXECUTABLE, SandboxExecutionAdapter,
    _image_uuid,
)
from .sandbox_plan import F6_RUN_ID, _read_regular, validate_f6_plan


PROJECT_ID = 'aiproject-e00a0rb50jb0emajfv'
ARTIFACT_PATH = '/work/docdrift/artifact.txt'
ARTIFACT_BYTES = b'DocDrift fixed F6 Sandbox artifact probe\n'
_EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
_IMPORT_PHASE = 'image_import'
_IMPORT_TIMEOUT = 120
_SCOPED_LIMITS = MappingProxyType({
    'image_imports': 1, 'runtime_probes': 3, 'verifier_operations': 12, 'inference_calls': 0,
})
PROBES = MappingProxyType({
    'capability': MappingProxyType({
        'code': (
            'import json, os, socket, sys\n'
            'interfaces = sorted(name for _, name in socket.if_nameindex())\n'
            'assert sys.version_info[:2] == (3, 12)\n'
            'assert os.geteuid() == 65534\n'
            'assert set(interfaces) <= {"lo"}\n'
            'print(json.dumps({"python": [3, 12], "euid": os.geteuid(), '
            '"interfaces": interfaces}, sort_keys=True))\n'
        ),
        'disposable': True,
    }),
    'artifact': MappingProxyType({
        'code': f'from pathlib import Path\nPath({ARTIFACT_PATH!r}).write_bytes({ARTIFACT_BYTES!r})\n',
        'disposable': False,
    }),
    'cancellation': MappingProxyType({
        'code': 'import time\ntime.sleep(20)\n',
        'disposable': True,
    }),
})


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _coverage(path: Path, project_id: str) -> bytes:
    try:
        content = _read_regular(path, 16_384)
        value = strict_json(content)
    except (OSError, ValueError):
        raise ValueError('Sandbox coverage confirmation or scoped authorization is required before any provider request') from None
    if isinstance(value, dict) and value.get('kind') == 'docdrift_sandbox_scoped_authorization':
        required = {
            'kind': 'docdrift_sandbox_scoped_authorization', 'project_id': PROJECT_ID,
            'billing_coverage': 'unverified', 'source_run_id': F6_RUN_ID,
        }
        limits = value.get('limits')
        if (project_id != PROJECT_ID
                or set(value) != {*required, 'limits', 'authorization', 'authorized_at_utc'}
                or any(value.get(key) != expected for key, expected in required.items())
                or not isinstance(limits, dict) or set(limits) != set(_SCOPED_LIMITS)
                or any(type(limits[key]) is not int or limits[key] != expected
                       for key, expected in _SCOPED_LIMITS.items())
                or not isinstance(value.get('authorization'), str) or not value['authorization'].strip()
                or not isinstance(value.get('authorized_at_utc'), str)):
            raise ValueError('Sandbox scoped authorization must match the fixed F6 project and limits')
        timestamp_key, timestamp_label = 'authorized_at_utc', 'scoped authorization'
    else:
        required = {
            'kind': 'docdrift_sandbox_credit_coverage', 'project_id': project_id,
            'execution': 'free_or_grant_covered', 'image_import': 'free_or_grant_covered',
            'storage': 'free_or_grant_covered',
        }
        if (not isinstance(value, dict) or any(value.get(key) != expected for key, expected in required.items())
                or type(value.get('personal_spend_limit')) is not int or value['personal_spend_limit'] != 0
                or not isinstance(value.get('confirmation'), str) or not value['confirmation'].strip()
                or not isinstance(value.get('confirmed_at_utc'), str)):
            raise ValueError('Sandbox execution, import and storage coverage must all be explicitly confirmed')
        timestamp_key, timestamp_label = 'confirmed_at_utc', 'coverage confirmation'
    try:
        confirmed = datetime.fromisoformat(value[timestamp_key].replace('Z', '+00:00'))
        if (confirmed.tzinfo is None or confirmed.utcoffset() != timezone.utc.utcoffset(confirmed)
                or confirmed > datetime.now(timezone.utc) + timedelta(minutes=5)):
            raise ValueError
    except ValueError:
        raise ValueError(f'Sandbox {timestamp_label} must have a UTC timestamp') from None
    return content


def _billing_facts(content: bytes) -> dict:
    """Publish validated billing facts without copying the authorization prose."""
    value = strict_json(content)
    facts = {'kind': value['kind'], 'project_id': value['project_id']}
    if value['kind'] == 'docdrift_sandbox_scoped_authorization':
        return {**facts, 'personal_spend_limit': None, 'credit_coverage_confirmed': False,
                'billing_coverage': 'unverified', 'user_authorized_scoped_run': True,
                'source_run_id': value['source_run_id'], 'limits': value['limits'],
                'authorized_at_utc': value['authorized_at_utc']}
    return {**facts, 'personal_spend_limit': 0, 'credit_coverage_confirmed': True,
            'billing_coverage': 'free_or_grant_covered', 'user_authorized_scoped_run': False,
            'confirmed_at_utc': value['confirmed_at_utc']}


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        parent = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temporary.unlink(missing_ok=True)


class F6SandboxRemote(NebiusSandboxAdapter):
    """One durable, explicitly authorized activation of the saved F6 plan."""

    def __init__(self, api_key: str, project_id: str, plan_root: Path, state_root: Path,
                 registry_image: str, coverage_path: Path):
        if project_id != PROJECT_ID:
            raise ValueError('Fixed F6 verification is scoped to the approved project')
        if not isinstance(registry_image, str) or re.fullmatch(
                r'docker://docker\.io/library/python@sha256:[0-9a-f]{64}', registry_image) is None:
            raise ValueError('F6 requires a digest-pinned official Python OCI image')
        self.plan_root = Path(plan_root).resolve()
        self.coverage_path = Path(coverage_path).absolute()
        coverage = _coverage(self.coverage_path, project_id)
        self._billing_authorization = _encoded(_billing_facts(coverage))
        self.plan = validate_f6_plan(self.plan_root)
        self.state_root = Path(state_root).resolve()
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = (self.state_root / 'session.lock').open('a+b')
        try:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            self._lock = None
            raise SubmissionConflict('Another fixed F6 session already holds this state directory') from None
        self._session_path = self.state_root / 'session.json'
        self._identity = {
            'kind': 'fixed_f6_sandbox_session', 'project_id': project_id,
            'plan_sha256': _digest(_encoded(self.plan)), 'registry_image': registry_image,
            'coverage_sha256': _digest(coverage),
        }
        self._control_run = 'f6_control_' + self._identity['plan_sha256'][:16]
        self._authorization = None
        try:
            if self._session_path.exists():
                session = strict_json(_read_regular(self._session_path, 256 * 1024))
                if not isinstance(session, dict) or session.get('identity') != self._identity:
                    raise SubmissionConflict('Saved F6 session project, plan, image or coverage changed')
            else:
                session = {'identity': self._identity, 'image_id': None, 'imported_image_id': None,
                           'run_id': None, 'uploads': {}, 'probes': {}}
                _write(self._session_path, _encoded(session))
            super().__init__(api_key, project_id, journal=SubmissionJournal(self.state_root))
            self._authorization_digest = _digest(self._client.headers['Authorization'].encode())
        except BaseException:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
            self._lock.close()
            self._lock = None
            raise

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._lock is not None:
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
                self._lock.close()
                self._lock = None

    def _session(self) -> dict:
        value = strict_json(_read_regular(self._session_path, 256 * 1024))
        if (not isinstance(value, dict) or value.get('identity') != self._identity
                or not isinstance(value.get('uploads'), dict) or not isinstance(value.get('probes'), dict)
                or not {'image_id', 'imported_image_id', 'run_id'} <= value.keys()):
            raise SubmissionConflict('Saved F6 session identity changed')
        return value

    def _save(self, session: dict) -> None:
        if session.get('identity') != self._identity:
            raise SubmissionConflict('F6 identity cannot be replaced')
        _write(self._session_path, _encoded(session))

    def _scope(self) -> dict:
        if self._lock is None:
            raise RemoteAdapterError('fixed_f6_session_closed')
        if (_digest(_coverage(self.coverage_path, PROJECT_ID)) != self._identity['coverage_sha256']
                or _digest(_encoded(validate_f6_plan(self.plan_root))) != self._identity['plan_sha256']
                or _digest(_encoded(self.plan)) != self._identity['plan_sha256']):
            raise SubmissionConflict('Approved F6 plan or coverage changed')
        if (self.offline_simulation is not False
                or self._client.base_url != httpx.URL(BASE_URL)
                or self._client.headers.get('Project') != PROJECT_ID
                or _digest(self._client.headers.get('Authorization', '').encode()) != self._authorization_digest
                or type(self._client._transport) is not httpx.HTTPTransport
                or any(transport is not None and transport is not self._client._transport
                       for transport in self._client._mounts.values())):
            raise RemoteAdapterError('fixed_f6_transport_changed')
        session = self._session()
        imported = session['imported_image_id']
        if imported is not None:
            receipt = self.journal.lookup(self._control_run, _IMPORT_PHASE)
            if (not receipt or receipt['state'] != 'completed'
                    or (receipt.get('result_metadata') or {}).get('result_image_id') != imported
                    or receipt['result_metadata'].get('service_state') != 'SUCCESS'):
                raise SubmissionConflict('Selected imported image differs from its durable receipt')
        if session['image_id'] is not None and session['image_id'] != imported:
            raise SubmissionConflict('Selected F6 image differs from the single import')
        for name, result in session['probes'].items():
            receipt = self.journal.lookup(self._control_run, 'probe_' + name) if name in PROBES else None
            recorded = (receipt or {}).get('result_metadata') or {}
            # Cancellation can finish before an instance has an assigned image.
            # Accept that outcome only for our requested cancellation probe and
            # its matching terminal receipt; it is never execution evidence.
            cancelled_before_assignment = (
                name == 'cancellation' and session.get('cancellation_requested') is True
                and isinstance(result, dict) and result.get('image_id') is None
                and result.get('service_state') == 'CANCELLED'
                and receipt is not None and receipt['state'] == 'completed'
                and recorded.get('operation_id') == result.get('operation_id')
                and recorded.get('service_state') == 'CANCELLED'
                and 'image_id' in recorded and recorded['image_id'] is None
            )
            image_matches = isinstance(result, dict) and (
                result.get('image_id') == session['image_id']
                or result.get('image_id') is None and result.get('service_state') in {'PENDING', 'ASSIGNED', 'EXECUTING'}
                or cancelled_before_assignment)
            if (not isinstance(result, dict) or not receipt or receipt['operation_id'] != result.get('operation_id')
                    or not image_matches):
                raise SubmissionConflict('Saved capability probe differs from its durable receipt')
        if session['run_id'] is not None:
            self._validate_run(session['run_id'], session['image_id'])
        return session

    def _validate_run(self, run_id: str, image_id: str) -> None:
        try:
            with sqlite3.connect(self.journal.path) as connection:
                row = connection.execute('SELECT metadata_json FROM runs WHERE run_id=?', (run_id,)).fetchone()
            metadata = strict_json(row[0]) if row else {}
        except (sqlite3.Error, ValueError):
            metadata = {}
        if (not isinstance(metadata, dict) or metadata.get('sandbox_plan_sha256') != self._identity['plan_sha256']
                or metadata.get('image') != image_id or metadata.get('adapter') != 'nebius_sandbox'
                or metadata.get('synthetic_execution') is not False):
            raise SubmissionConflict('Verifier ledger does not match the bound F6 plan and image')

    def _require_mutations(self) -> None:
        self._scope()
        if self._authorization is None:
            # The ordinary simulation bridge invokes this guard at entry.
            # Explicit F6 scope must not enable that unchanged bridge.
            raise RemoteMutationsDisabled()

    @property
    def run_id(self) -> str | None:
        return self._session()['run_id']

    @property
    def image_id(self) -> str | None:
        return self._session()['image_id']

    @property
    def operation_counts(self) -> dict[str, int]:
        """Count durable attempts, including uncertainty, without provider reads."""
        control = self.journal.for_run(self._control_run)
        run_id = self._session()['run_id']
        verifier = self.journal.for_run(run_id) if run_id is not None else []
        phases = {item['phase'] for item in self.plan['phases']}
        return {
            'image_imports': sum(item['phase'] == _IMPORT_PHASE for item in control),
            'runtime_probes': sum(item['phase'] in {'probe_' + name for name in PROBES} for item in control),
            'verifier_operations': sum(item['phase'] in phases for item in verifier),
        }

    def bind_image(self, image_uuid: str) -> None:
        session = self._scope()
        image_uuid = _image_uuid(image_uuid)
        if session['imported_image_id'] != image_uuid or session['image_id'] not in {None, image_uuid}:
            raise SubmissionConflict('F6 image must be the single successfully imported immutable image')
        session['image_id'] = image_uuid
        self._save(session)

    def bind_run(self, run_id: str) -> None:
        session = self._scope()
        if not isinstance(run_id, str) or re.fullmatch(r'[0-9a-f]{32}', run_id) is None:
            raise ValueError('F6 verifier run must have a canonical run ID')
        if session['image_id'] is None or session['run_id'] not in {None, run_id}:
            raise SubmissionConflict('F6 verifier run or selected image cannot change')
        self._validate_run(run_id, session['image_id'])
        session['run_id'] = run_id
        self._save(session)

    @contextmanager
    def _authorize(self, method: str, path: str, identity: object):
        if self._authorization is not None:
            raise RemoteAdapterError('fixed_f6_nested_mutation')
        self._authorization = (method, path, identity)
        try:
            yield
        finally:
            self._authorization = None

    def _owned(self) -> dict[str, dict]:
        session = self._session()
        receipts = self.journal.for_run(self._control_run)
        if session['run_id'] is not None:
            receipts += self.journal.for_run(session['run_id'])
        return {item['operation_id']: item for item in receipts if item['operation_id']}

    def _request(self, method: str, path: str, *, payload=None, content=None, params=None, limit=2 * 1024 * 1024):
        session = self._scope()
        if method == 'GET':
            allowed = path.startswith('operations/') and path.removeprefix('operations/') in self._owned() and not params
            if path == f"inspect/{session['image_id']}/" and session['image_id']:
                allowed = not params
            artifact = session['probes'].get('artifact', {})
            if artifact.get('result_image_id') and path == f"inspect/{artifact['result_image_id']}/download":
                allowed = params == {'path': ARTIFACT_PATH}
            if not allowed:
                raise RemoteAdapterError('fixed_f6_read_out_of_scope')
        else:
            authorization = self._authorization
            if authorization is None or authorization[:2] != (method, path):
                raise RemoteAdapterError('fixed_f6_mutation_out_of_scope')
            expected = authorization[2]
            if path == 'files':
                valid = isinstance(content, bytes) and _digest(content) == expected and payload is None
            elif path == 'instances':
                actual = dict(payload) if isinstance(payload, dict) else {}
                cwd = actual.pop('cwd', None)
                valid = (actual == expected and isinstance(cwd, str)
                         and re.fullmatch(r'/work/docdrift/operations/[0-9a-f-]{36}', cwd) is not None)
            elif path == 'images/import':
                valid = payload == expected
            else:
                valid = path.startswith('operations/') and path.removeprefix('operations/') == expected
            if not valid:
                raise RemoteAdapterError('fixed_f6_mutation_out_of_scope')
        status, data = super()._request(method, path, payload=payload, content=content, params=params, limit=limit)
        if method == 'GET' and path.startswith('operations/'):
            _write(self.state_root / 'operations' / (path.removeprefix('operations/') + '.json'), data)
        return status, data

    def import_image(self) -> str:
        """Submit once, then only observe the same private import across restarts."""
        self._scope()
        receipt = self.journal.lookup(self._control_run, _IMPORT_PHASE)
        if receipt is None:
            payload = {'registry': {'url': self._identity['registry_image']}, 'timeout': _IMPORT_TIMEOUT}
            receipt = self.journal.begin(self._control_run, _IMPORT_PHASE, _digest(_encoded(payload)))
            try:
                with self._authorize('POST', 'images/import', payload):
                    status, data = self._request('POST', 'images/import', payload=payload)
                returned = self._object(data)
                operation_id = _image_uuid(returned.get('uuid'))
            except (RemoteAdapterError, ValueError) as error:
                code = error.code if isinstance(error, RemoteAdapterError) else 'invalid_import_response'
                rejected = re.fullmatch(r'http_4\d\d', code) is not None and code not in {'http_408', 'http_429'}
                if rejected:
                    self.journal.rejected(receipt['attempt_id'], code)
                    raise RemoteAdapterError(code, attempt_id=receipt['attempt_id']) from None
                self.journal.uncertain(receipt['attempt_id'], code)
                raise UncertainSubmission(code, attempt_id=receipt['attempt_id']) from None
            try:
                self.journal.accepted(receipt['attempt_id'], operation_id)
            except Exception:
                raise RemoteAdapterError('import_acceptance_persistence_failed',
                    operation_id=operation_id, attempt_id=receipt['attempt_id']) from None
            if status != 201:
                raise RemoteAdapterError('invalid_import_response', operation_id=operation_id)
            receipt = self.journal.lookup(self._control_run, _IMPORT_PHASE)
        if not receipt['operation_id']:
            raise UncertainSubmission('saved_import_cannot_retry', attempt_id=receipt['attempt_id'])
        operation_id = receipt['operation_id']
        if (receipt['state'] == 'completed'
                and (receipt.get('result_metadata') or {}).get('service_state') in {'FAILED', 'CANCELLED'}):
            raise RemoteAdapterError('import_not_successful', operation_id=operation_id,
                                     attempt_id=receipt['attempt_id'])
        deadline = time.monotonic() + _IMPORT_TIMEOUT
        for _ in range(61):
            _, data = self._request('GET', f'operations/{operation_id}')
            value = self._object(data)
            if (value.get('uuid') != operation_id or value.get('kind') != 'image_import'
                    or value.get('status') not in {'PENDING', 'ASSIGNED', 'EXECUTING', 'SUCCESS', 'FAILED', 'CANCELLED'}):
                raise RemoteAdapterError('invalid_import_operation', operation_id=operation_id)
            if value['status'] in {'FAILED', 'CANCELLED'}:
                self.journal.completed(receipt['attempt_id'], {'operation_id': operation_id,
                    'state': 'failed' if value['status'] == 'FAILED' else 'cancelled', 'service_state': value['status']})
                raise RemoteAdapterError('import_not_successful', operation_id=operation_id,
                                         attempt_id=receipt['attempt_id'])
            if value['status'] == 'SUCCESS':
                result = value.get('result')
                result = result if isinstance(result, dict) else {}
                image = _image_uuid(value.get('result_image_uuid') or result.get('image'))
                if (value.get('image_uuid') is not None
                        or result.get('image') not in {None, image}
                        or value.get('result_image_uuid') not in {None, image}):
                    raise RemoteAdapterError('invalid_import_image', operation_id=operation_id)
                self.journal.completed(receipt['attempt_id'], {'operation_id': operation_id,
                    'result_image_id': image, 'state': 'completed', 'service_state': 'SUCCESS'})
                session = self._session()
                if session['imported_image_id'] not in {None, image}:
                    raise SubmissionConflict('Saved imported image changed')
                session['imported_image_id'] = image
                self._save(session)
                self.bind_image(image)
                session = self._session()
                if session.get('image_inspected_id') != image:
                    _, inspected = self._request('GET', f'inspect/{image}/')
                    if self._object(inspected).get('uuid') != image:
                        raise RemoteAdapterError('invalid_image_response')
                    session['image_inspected_id'] = image
                    self._save(session)
                return image
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(2, remaining))
        raise RemoteAdapterError('import_observation_timeout', operation_id=operation_id)

    def prepare(self, files: dict[str, bytes]) -> dict[str, UploadedFile]:
        session = self._scope()
        allowed = {(path, digest) for phase in self.plan['phases'] for path, digest in phase['files'].items()}
        allowed.add((ARTIFACT_PATH, _EMPTY_SHA256))
        if any(not isinstance(value, bytes) or (path, _digest(value)) not in allowed for path, value in files.items()):
            raise RemoteAdapterError('fixed_f6_upload_out_of_scope')
        uploaded = {}
        for path, content in sorted(files.items()):
            digest = _digest(content)
            saved = session['uploads'].get(digest)
            if saved:
                if saved['state'] != 'accepted':
                    raise UncertainSubmission('upload_uncertain_no_retry')
                uploaded[path] = UploadedFile(saved['uuid'], digest, saved['size'])
                continue
            session['uploads'][digest] = {'state': 'submitting', 'size': len(content)}
            self._save(session)
            try:
                with self._authorize('POST', 'files', digest):
                    value = super().prepare({path: content})[path]
            except BaseException:
                session['uploads'][digest]['state'] = 'uncertain'
                self._save(session)
                raise
            session['uploads'][digest] = {'state': 'accepted', 'uuid': value.uuid, 'size': value.size}
            self._save(session)
            uploaded[path] = value
        return uploaded

    def _file_hashes(self, files) -> dict[str, str]:
        uploads = self._session()['uploads']
        hashes = {}
        for path, value in files.items():
            file_id = value.uuid if isinstance(value, UploadedFile) else value
            matches = [digest for digest, record in uploads.items()
                       if record['state'] == 'accepted' and record['uuid'] == file_id]
            if len(matches) != 1:
                raise RemoteAdapterError('fixed_f6_unknown_uploaded_file')
            if isinstance(value, UploadedFile) and (
                    value.sha256 != matches[0] or value.size != uploads[matches[0]]['size']):
                raise RemoteAdapterError('fixed_f6_uploaded_identity_changed')
            hashes[path] = matches[0]
        return hashes

    def _phase(self, run_id: str, phase: str) -> dict:
        session = self._scope()
        if run_id != session['run_id'] or session['run_id'] is None:
            raise RemoteAdapterError('fixed_f6_run_out_of_scope')
        matches = [item for item in self.plan['phases'] if item['phase'] == phase]
        if len(matches) != 1:
            raise RemoteAdapterError('fixed_f6_phase_out_of_scope')
        return matches[0]

    def submit(self, request: RemoteExecutionRequest, on_accepted, *, run_id: str, phase: str) -> str:
        session = self._scope()
        if (request.image_id != session['image_id'] or session['image_id'] is None
                or session.get('image_inspected_id') != session['image_id']):
            raise RemoteAdapterError('fixed_f6_image_out_of_scope')
        hashes = self._file_hashes(request.files)
        if run_id == self._control_run and phase.startswith('probe_') and phase[6:] in PROBES:
            name = phase[6:]
            probe = PROBES[name]
            expected_files = {ARTIFACT_PATH: _EMPTY_SHA256} if name == 'artifact' else {}
            valid = (request.args == ('-B', '-c', probe['code']) and not request.environment
                     and hashes == expected_files and request.disposable is probe['disposable'])
        else:
            spec = self._phase(run_id, phase)
            valid = (request.args == ('-B', GUEST_RUNNER) and dict(request.environment) == spec['environment']
                     and hashes == spec['files'] and request.disposable is True)
            if not self._capability_success(session):
                raise RemoteAdapterError('fixed_f6_capability_not_confirmed')
        if (not valid or request.executable != PYTHON_EXECUTABLE or request.timeout_seconds != 30
                or request.log_limit_bytes != MAX_LOG_BYTES):
            raise RemoteAdapterError('fixed_f6_execution_out_of_scope')
        expected = self._payload(request)
        expected.pop('cwd')
        with self._authorize('POST', 'instances', expected):
            return super().submit(request, on_accepted, run_id=run_id, phase=phase)

    def recover(self, run_id: str, phase: str, *, expected_image_id=None, expected_disposable=None):
        session = self._scope()
        if run_id == self._control_run and phase.startswith('probe_') and phase[6:] in PROBES:
            expected_retention = PROBES[phase[6:]]['disposable']
        else:
            self._phase(run_id, phase)
            expected_retention = True
        if expected_image_id != session['image_id'] or expected_disposable is not expected_retention:
            raise SubmissionConflict('F6 recovery image or retention changed')
        return super().recover(run_id, phase, expected_image_id=expected_image_id,
                               expected_disposable=expected_disposable)

    @staticmethod
    def _capability_success(session: dict) -> bool:
        saved = session['probes'].get('capability')
        if not isinstance(saved, dict):
            return False
        try:
            result = RemoteResult(**saved)
            output = strict_json(result.stdout)
        except (TypeError, ValueError):
            return False
        return (result.execution_passed and not result.synthetic and isinstance(output, dict)
                and output.get('python') == [3, 12] and output.get('euid') == 65534
                and isinstance(output.get('interfaces'), list)
                and all(item == 'lo' for item in output['interfaces']))

    @property
    def billing_authorization(self) -> dict:
        self._scope()
        return strict_json(self._billing_authorization)

    @property
    def runtime_capabilities(self) -> dict:
        session = self._scope()
        return {'python_capability_tested': self._capability_success(session),
                'network_isolation_tested': self._capability_success(session),
                'capability_operation_id': session['probes'].get('capability', {}).get('operation_id')}

    def preflight(self, image_id=None) -> dict:
        session = self._scope()
        if image_id != session['image_id'] or image_id is None or not self._capability_success(session):
            raise RemoteAdapterError('fixed_f6_capability_not_confirmed')
        return {'image_id': image_id, 'synthetic': False, **self.billing_authorization,
                'live_mutations_enabled': True,
                'python_version': '3.12', 'network': 'disabled', **self.runtime_capabilities}

    def run_probe(self, name: str) -> RemoteResult:
        session = self._scope()
        if name not in PROBES or session['image_id'] is None:
            raise RemoteAdapterError('fixed_f6_probe_out_of_scope')
        spec = PROBES[name]
        phase = 'probe_' + name
        receipt = self.recover(self._control_run, phase, expected_image_id=session['image_id'],
                               expected_disposable=spec['disposable'])
        if receipt is None:
            files = self.prepare({ARTIFACT_PATH: b''}) if name == 'artifact' else {}
            request = RemoteExecutionRequest(session['image_id'], PYTHON_EXECUTABLE,
                ('-B', '-c', spec['code']), files=files, disposable=spec['disposable'])
            operation_id = self.submit(request, lambda _: None, run_id=self._control_run, phase=phase)
        elif receipt['operation_id']:
            operation_id = receipt['operation_id']
        else:
            raise UncertainSubmission('saved_probe_cannot_retry', attempt_id=receipt['attempt_id'])
        result = self.observe(operation_id, timeout_seconds=0 if name == 'cancellation' else 30)
        session = self._session()
        session['probes'][name] = asdict(result)
        self._save(session)
        if name == 'capability' and not self._capability_success(session):
            raise RemoteAdapterError('fixed_f6_capability_not_confirmed', operation_id=operation_id)
        return result

    def cancel(self, operation_id: str) -> None:
        self._scope()
        receipt = self.journal.lookup(self._control_run, 'probe_cancellation')
        if not receipt or receipt['operation_id'] != operation_id:
            raise RemoteAdapterError('fixed_f6_cancel_out_of_scope')
        session = self._session()
        if session.get('cancellation_requested'):
            raise UncertainSubmission('cancellation_already_requested', operation_id=operation_id)
        session['cancellation_requested'] = True
        self._save(session)
        with self._authorize('DELETE', f'operations/{operation_id}', operation_id):
            super().cancel(operation_id)

    def cancel_probe(self) -> RemoteResult:
        session = self._scope()
        receipt = self.recover(self._control_run, 'probe_cancellation', expected_image_id=session['image_id'],
                               expected_disposable=True)
        if not receipt or not receipt['operation_id']:
            raise RemoteAdapterError('fixed_f6_cancellation_probe_missing')
        result = self.observe(receipt['operation_id'], timeout_seconds=0)
        if result.service_state not in {'SUCCESS', 'FAILED', 'CANCELLED'} and not session.get('cancellation_requested'):
            self.cancel(result.operation_id)
            result = self.observe(result.operation_id, timeout_seconds=30)
        elif session.get('cancellation_requested') and result.service_state not in {'SUCCESS', 'FAILED', 'CANCELLED'}:
            result = self.observe(result.operation_id, timeout_seconds=30)
        session = self._session()
        session['probes']['cancellation'] = asdict(result)
        self._save(session)
        return result

    def download_probe_artifact(self) -> bytes:
        session = self._scope()
        receipt = self.recover(self._control_run, 'probe_artifact', expected_image_id=session['image_id'],
                               expected_disposable=False)
        if not receipt or not receipt['operation_id']:
            raise RemoteAdapterError('fixed_f6_artifact_probe_missing')
        content = super().download(receipt['operation_id'], (ARTIFACT_PATH,))[ARTIFACT_PATH]
        if content != ARTIFACT_BYTES:
            raise RemoteAdapterError('fixed_f6_artifact_bytes_mismatch')
        return content


class F6ExecutionAdapter(SandboxExecutionAdapter):
    """Reuse durable bridge recovery, with the fixed live plan checked first."""

    backend_name = 'nebius_sandbox'
    synthetic = False

    def _require_simulation(self) -> None:
        if type(self.remote) is not F6SandboxRemote:
            raise TypeError('F6ExecutionAdapter requires its fixed-scope live remote')
        self.remote._scope()

    @property
    def execution_contract(self) -> dict:
        contract = super().execution_contract
        contract.pop('code_executions', None)
        return {**contract, 'synthetic': False, 'network': 'disabled_and_capability_probed',
                'scope': 'saved_f6_only', 'billing_authorization': self.remote.billing_authorization}

    def preflight(self, image: str) -> dict:
        self._require_simulation()
        return {**self.remote.preflight(image), 'image': image, 'adapter': self.backend_name,
                'python_executable_contract': PYTHON_EXECUTABLE}

    def _freeze(self, request: ExecutionRequest):
        files, digest = super()._freeze(request)
        hashes = {path: _digest(content) for path, content in files.items()}
        if (request.image != self.remote.image_id or request.timeout_seconds != 30
                or request.log_limit_bytes != MAX_LOG_BYTES
                or not any(hashes == phase['files'] and dict(request.environment) == phase['environment']
                           and _digest(request.code.encode()) == phase['code_sha256']
                           for phase in self.remote.plan['phases'])):
            raise RemoteAdapterError('fixed_f6_execution_out_of_scope')
        return files, digest

    def execute(self, request: ExecutionRequest, on_accepted, *, run_id: str, phase: str):
        spec = self.remote._phase(run_id, phase)
        files, _ = self._freeze(request)
        if ({path: _digest(content) for path, content in files.items()} != spec['files']
                or dict(request.environment) != spec['environment']
                or _digest(request.code.encode()) != spec['code_sha256']):
            raise RemoteAdapterError('fixed_f6_phase_inputs_changed')
        self.remote.preflight(request.image)
        return super().execute(request, on_accepted, run_id=run_id, phase=phase)

    def recover(self, run_id: str, phase: str, *, expected_image_id: str):
        self.remote._phase(run_id, phase)
        return super().recover(run_id, phase, expected_image_id=expected_image_id)

    @staticmethod
    def _result(result: RemoteResult):
        if result.synthetic:
            raise RemoteAdapterError('fixed_f6_synthetic_result_forbidden')
        return replace(SandboxExecutionAdapter._result(result), synthetic=False)
