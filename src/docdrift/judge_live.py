"""Narrow live Sandbox bridge for the approved, fixture-bound judge service.

There is no CLI activation or arbitrary image/repository route here. The host
owns the durable allowance callback; every new spawn reserves it immediately
before its sole POST. Ambiguous uploads and submissions are never retried.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Callable
from uuid import UUID

import httpx

from .markdown import extract_examples
from .nebius import (
    BASE_URL, MAX_LOG_BYTES, NebiusSandboxAdapter, RemoteAdapterError,
    RemoteExecutionRequest, RemoteResult, UploadedFile, UncertainSubmission,
)
from .policy import apply_replacement
from .profile import load_profile, strict_json
from .remote_journal import SubmissionConflict, SubmissionJournal
from .sandbox_execution import (
    GUEST_REPOSITORY, GUEST_RUNNER, PYTHON_EXECUTABLE,
    SandboxExecutionAdapter, freeze_snapshot,
)
from .sandbox_plan import _read_regular
from .sandbox_live import _write


PROJECT_ID = 'aiproject-e00a0rb50jb0emajfv'
IMAGE_ID = '4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae'
MAX_OPERATIONS = 17
_MANIFESTS = {
    'source_only': ('development', 'bc26871f8640c5bdc3130308a0bdaabe85fa2597b40a4009bf518a745cd9ffd9'),
    'renamed_import': ('evaluation', '12d58e9ae1bcf4898813cce999c104403bb1637f644a396c4a24431532560d18'),
    'changed_return_shape': ('evaluation', '12d58e9ae1bcf4898813cce999c104403bb1637f644a396c4a24431532560d18'),
}
_CAPABILITY_CODE = (
    'import json, os, socket, sys\n'
    'interfaces = sorted(name for _, name in socket.if_nameindex())\n'
    'assert sys.version_info[:2] == (3, 12)\n'
    'assert os.geteuid() == 65534\n'
    'assert set(interfaces) <= {"lo"}\n'
    'print(json.dumps({"python": [3, 12], "euid": os.geteuid(), '
    '"interfaces": interfaces}, sort_keys=True))\n'
)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _capability(value: dict) -> dict:
    expected = {
        'kind': 'docdrift_judge_sandbox_capability', 'status': 'verified',
        'project_id': PROJECT_ID, 'image_id': IMAGE_ID, 'python': [3, 12],
        'euid': 65534, 'synthetic': False,
    }
    if (not isinstance(value, dict) or set(value) != {*expected, 'interfaces', 'operation_id'}
            or any(value.get(key) != item or type(value.get(key)) is not type(item)
                   for key, item in expected.items())
            or value.get('interfaces') not in ([], ['lo'])):
        raise ValueError('Judge execution requires the approved startup capability result')
    try:
        if str(UUID(value['operation_id'])) != value['operation_id'] or UUID(value['operation_id']).int == 0:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Startup capability operation identity is invalid') from None
    return strict_json(_encoded(value))


def _fixture(fixture: Path) -> tuple[str, dict[str, bytes], dict, dict[str, bytes]]:
    """Read only pinned source/profile/checks, never the known repair contents."""
    original = Path(fixture)
    if original.is_symlink():
        raise ValueError('Judge fixture must be a regular pinned fixture directory')
    path = original.resolve(strict=True)
    name = path.name
    if name not in _MANIFESTS or path.parent.name != _MANIFESTS[name][0]:
        raise ValueError('Judge fixture is outside the approved inventory')
    manifest_bytes = _read_regular(path.parent / 'manifest.json', 262_144)
    if _digest(manifest_bytes) != _MANIFESTS[name][1]:
        raise ValueError('Judge fixture inventory changed')
    manifest = strict_json(manifest_bytes)['files']
    repository = freeze_snapshot(path / 'repository')
    expected = {GUEST_REPOSITORY + '/' + relative.removeprefix(name + '/repository/'): digest
                for relative, digest in manifest.items() if relative.startswith(name + '/repository/')}
    if {relative: _digest(content) for relative, content in repository.items()} != expected:
        raise ValueError('Judge fixture repository differs from its frozen manifest')
    profile, profile_files = load_profile(path / 'profile.json')
    if any(_digest(content) != manifest.get(name + '/' + relative)
           for relative, content in profile_files.items()):
        raise ValueError('Judge fixture profile or checks changed')
    return name, repository, profile, profile_files


class _JudgeRemote(NebiusSandboxAdapter):
    """Only frozen bridge uploads, disposable spawns, and owned observations."""

    def __init__(self, api_key: str, state_root: Path, reserve: Callable[[], None], *,
                 transport: httpx.BaseTransport | None, operation_limit: int):
        self.state_root = Path(state_root).resolve()
        if self.state_root.name == 'sandbox-f6' or any(part == 'sandbox-f6' for part in self.state_root.parts):
            raise ValueError('Judge execution cannot use the consumed F6 state')
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._reserve = reserve
        self._limit = operation_limit
        self._authorization = None
        self._allowed_files: dict[str, bytes] = {}
        self._allowed_request = None
        super().__init__(api_key, PROJECT_ID, transport=transport,
                         journal=SubmissionJournal(self.state_root))
        self._client_identity = self._client
        self._transport_identity = self._client._transport
        self._authorization_digest = _digest(self._client.headers['Authorization'].encode())

    def _require_mutations(self) -> None:
        if (self._client is not self._client_identity
                or self._client._transport is not self._transport_identity
                or str(self._client.base_url) != BASE_URL
                or self._client.headers.get('Project') != PROJECT_ID
                or _digest(self._client.headers.get('Authorization', '').encode()) != self._authorization_digest
                or any(value is not None and value is not self._transport_identity
                       for value in self._client._mounts.values())):
            raise RemoteAdapterError('judge_transport_changed')

    @contextmanager
    def _authorize(self, method: str, path: str, identity):
        self._require_mutations()
        if self._authorization is not None:
            raise RemoteAdapterError('judge_nested_request')
        self._authorization = (method, path, identity)
        try:
            yield
        finally:
            self._authorization = None

    def _request(self, method, path, *, payload=None, content=None, params=None, limit=2 * 1024 * 1024):
        self._require_mutations()
        if method == 'GET':
            operation_id = path.removeprefix('operations/')
            valid = (path == 'operations/' + operation_id and operation_id in self._accepted
                     and payload is None and content is None and params is None)
        else:
            authorization = self._authorization
            valid = (authorization is not None and authorization[:2] == (method, path)
                     and params is None)
            if valid and method == 'POST' and path == 'files':
                valid = isinstance(content, bytes) and _digest(content) == authorization[2] and payload is None
            elif valid and method == 'POST' and path == 'instances':
                actual = dict(payload) if isinstance(payload, dict) else {}
                cwd = actual.pop('cwd', None)
                valid = (actual == authorization[2] and content is None and isinstance(cwd, str)
                         and re.fullmatch(r'/work/docdrift/operations/[0-9a-f-]{36}', cwd) is not None)
                if valid:
                    # Consume the authorization before calling a callback or
                    # transport: neither can cause a second POST through it.
                    self._authorization = None
                    self._reserve()
            else:
                valid = False
        if not valid:
            raise RemoteAdapterError('judge_request_out_of_scope')
        status, data = super()._request(method, path, payload=payload, content=content, params=params, limit=limit)
        if method == 'GET':
            _write(self.state_root / 'operations' / (operation_id + '.json'), data)
        return status, data

    def prepare(self, files):
        if any(not isinstance(content, bytes) or self._allowed_files.get(path) != content
               for path, content in files.items()):
            raise RemoteAdapterError('judge_upload_out_of_scope')
        uploaded = {}
        for path, content in files.items():
            with self._authorize('POST', 'files', _digest(content)):
                uploaded.update(super().prepare({path: content}))
        return uploaded

    def submit(self, request, on_accepted, *, run_id, phase):
        if (run_id, phase, request) != self._allowed_request:
            raise RemoteAdapterError('judge_spawn_out_of_scope')
        if self.journal.lookup(run_id, phase) is not None:
            raise UncertainSubmission('saved_submission_cannot_retry')
        with self.journal._connection() as connection:
            count = connection.execute('SELECT COUNT(*) FROM remote_submissions').fetchone()[0]
        if count >= self._limit:
            raise RemoteAdapterError('judge_operation_limit')
        payload = self._payload(request)
        payload.pop('cwd')
        with self._authorize('POST', 'instances', payload):
            return super().submit(request, on_accepted, run_id=run_id, phase=phase)

    def recover(self, run_id, phase, *, expected_image_id=None, expected_disposable=None):
        if expected_image_id != IMAGE_ID or expected_disposable is not True:
            raise RemoteAdapterError('judge_recovery_out_of_scope')
        return super().recover(run_id, phase, expected_image_id=IMAGE_ID, expected_disposable=True)

    def cancel(self, operation_id):
        raise RemoteAdapterError('judge_cancellation_disabled_disposable_timeout')


class JudgeExecutionAdapter(SandboxExecutionAdapter):
    """Live execution only for the three frozen, dependency-free judge cases."""

    backend_name = 'nebius_sandbox'
    synthetic = False

    def __init__(self, api_key: str, state_root: Path, fixture: Path,
                 reserve_operation: Callable[[], None], *, capability: dict,
                 transport: httpx.BaseTransport | None = None):
        self._capability = _capability(capability)
        self.fixture_name, self._repository, self._profile, self._profile_files = _fixture(fixture)
        binding = {'kind': 'docdrift_judge_fixture_binding', 'fixture': self.fixture_name,
                   'files': {path: _digest(content) for path, content in self._repository.items()},
                   'profile': {path: _digest(content) for path, content in self._profile_files.items()},
                   'capability': self._capability}
        root = Path(state_root).resolve()
        path = root / 'judge-binding.json'
        if path.exists() and _read_regular(path, 32_768) != _encoded(binding):
            raise SubmissionConflict('Judge fixture or startup capability changed for this attempt')
        remote = _JudgeRemote(api_key, root, reserve_operation, transport=transport, operation_limit=MAX_OPERATIONS)
        if not path.exists():
            _write(path, _encoded(binding))
        super().__init__(remote)

    def _require_simulation(self):
        if type(self.remote) is not _JudgeRemote:
            raise TypeError('Judge execution requires its private scoped remote')
        self.remote._require_mutations()

    @property
    def execution_contract(self):
        return {'executable': PYTHON_EXECUTABLE, 'arguments': ['-B', GUEST_RUNNER],
                'network': 'disabled_and_capability_probed', 'synthetic': False,
                'scope': 'fixed_judge_fixture', 'fixture': self.fixture_name,
                'repository_path': GUEST_REPOSITORY, 'disposable': True, 'uid': 65534,
                'capability_operation_id': self._capability['operation_id'],
                'image_id': IMAGE_ID}

    def preflight(self, image: str):
        self._require_simulation()
        if image != IMAGE_ID:
            raise RemoteAdapterError('judge_image_out_of_scope')
        return {'image': IMAGE_ID, 'image_id': IMAGE_ID, 'adapter': self.backend_name,
                'python_executable_contract': PYTHON_EXECUTABLE, 'python_capability_tested': True,
                'network_isolation_tested': True, 'network': 'disabled_and_capability_probed',
                'synthetic': False, 'capability': dict(self._capability),
                'credit_coverage_confirmed': False, 'billing_coverage': 'unverified'}

    def _freeze(self, request):
        if request.image != IMAGE_ID or request.timeout_seconds != 30 or request.log_limit_bytes != MAX_LOG_BYTES:
            raise RemoteAdapterError('judge_execution_out_of_scope')
        files, digest = super()._freeze(request)
        repository = {path: content for path, content in files.items() if path.startswith(GUEST_REPOSITORY + '/')}
        target_path = GUEST_REPOSITORY + '/' + self._profile['target']['path']
        if (set(repository) != set(self._repository)
                or any(repository[path] != content for path, content in self._repository.items() if path != target_path)):
            raise RemoteAdapterError('judge_protected_snapshot_changed')
        original, current = self._repository[target_path], repository[target_path]
        if current != original:
            ordinal = self._profile['target']['ordinal']
            source = extract_examples(self._profile['target']['path'], original)[ordinal]
            examples = extract_examples(self._profile['target']['path'], current)
            if ordinal >= len(examples):
                raise RemoteAdapterError('judge_target_span_changed')
            approved = apply_replacement(source.path, original, source.id, source.source_hash, examples[ordinal].code)
            if approved != current:
                raise RemoteAdapterError('judge_target_span_changed')
        allowed_envs = [case['env'] for spec in self._profile['examples'] for case in spec['cases']]
        if dict(request.environment) not in allowed_envs:
            raise RemoteAdapterError('judge_environment_out_of_scope')
        return files, digest

    def execute(self, request, on_accepted, *, run_id, phase):
        if (not isinstance(run_id, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,255}', run_id) is None
                or not isinstance(phase, str)
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}', phase) is None):
            raise ValueError('Judge execution requires bounded run and phase identifiers')
        files, _ = self._freeze(request)
        profile_path = self.remote.state_root / 'runs' / run_id / 'profile'
        if profile_path.exists():
            profile_files = {path.removeprefix(GUEST_REPOSITORY + '/'): content
                             for path, content in freeze_snapshot(profile_path).items()}
            if profile_files != self._profile_files:
                raise RemoteAdapterError('judge_frozen_profile_changed')
        self.remote._allowed_files = files
        # The existing bridge performs its own durable recovery before upload.
        # Build the same remote request lazily after its uploads have UUIDs.
        previous_submit = self.remote._allowed_request
        self.remote._bridge_request = (run_id, phase, request)
        try:
            return super().execute(request, on_accepted, run_id=run_id, phase=phase)
        finally:
            self.remote._allowed_request = previous_submit
            self.remote._allowed_files = {}
            self.remote._bridge_request = None

    def _upload(self, path, content):
        uploaded = super()._upload(path, content)
        context = self.remote._bridge_request
        run_id, phase, request = context
        # Cache entries accepted in this durable attempt supply the exact file
        # UUIDs. No caller-provided or cross-attempt upload reference is used.
        files = self.remote._allowed_files
        with self._connection() as connection:
            saved = {row['sha256']: row for row in connection.execute(
                "SELECT * FROM sandbox_bridge_uploads WHERE state='accepted'")}
        if all(_digest(value) in saved for value in files.values()):
            references = {name: UploadedFile(saved[_digest(value)]['file_id'], _digest(value), saved[_digest(value)]['size'])
                          for name, value in files.items()}
            remote_request = RemoteExecutionRequest(IMAGE_ID, PYTHON_EXECUTABLE, ('-B', GUEST_RUNNER),
                                                    request.environment, references, True, 30, MAX_LOG_BYTES)
            self.remote._allowed_request = (run_id, phase, remote_request)
        return uploaded

    @staticmethod
    def _result(result: RemoteResult):
        if result.synthetic:
            raise RemoteAdapterError('judge_synthetic_result_forbidden')
        return replace(SandboxExecutionAdapter._result(result), synthetic=False)


def run_capability(api_key: str, state_root: Path, reserve_operation: Callable[[], None], *,
                   transport: httpx.BaseTransport | None = None) -> dict:
    """One startup spawn, recoverable by its durable receipt without resubmit."""
    root = Path(state_root).resolve()
    remote = _JudgeRemote(api_key, root, reserve_operation, transport=transport, operation_limit=1)
    try:
        run_id, phase = 'judge_startup', 'capability'
        receipt = remote.recover(run_id, phase, expected_image_id=IMAGE_ID, expected_disposable=True)
        path = root / 'capability.json'
        if path.exists():
            value = _capability(strict_json(_read_regular(path, 16_384)))
            if (not receipt or receipt['operation_id'] != value['operation_id']
                    or receipt['state'] != 'completed'):
                raise SubmissionConflict('Startup capability receipt is missing or changed')
            return value
        if receipt:
            if not receipt['operation_id']:
                raise UncertainSubmission('saved_submission_cannot_retry', attempt_id=receipt['attempt_id'])
            operation_id = receipt['operation_id']
        else:
            request = RemoteExecutionRequest(IMAGE_ID, PYTHON_EXECUTABLE, ('-I', '-c', _CAPABILITY_CODE),
                                             disposable=True, timeout_seconds=30, log_limit_bytes=MAX_LOG_BYTES)
            remote._allowed_request = (run_id, phase, request)
            operation_id = remote.submit(request, lambda _: None, run_id=run_id, phase=phase)
        result = remote.observe(operation_id, timeout_seconds=30)
        if not result.execution_passed or result.synthetic:
            raise RemoteAdapterError('judge_startup_capability_failed', operation_id=operation_id)
        try:
            facts = strict_json(result.stdout)
            if not isinstance(facts, dict) or set(facts) != {'python', 'euid', 'interfaces'}:
                raise ValueError
            value = _capability({'kind': 'docdrift_judge_sandbox_capability', 'status': 'verified',
                                 'project_id': PROJECT_ID, 'image_id': IMAGE_ID, 'operation_id': operation_id,
                                 **facts, 'synthetic': False})
        except (ValueError, TypeError):
            raise RemoteAdapterError('judge_startup_capability_failed', operation_id=operation_id) from None
        _write(path, _encoded(value))
        return value
    finally:
        remote.close()
