"""Offline-only execution bridge for the synthetic Sandbox REST contract.

The bridge never accepts a live transport, including for preflight and polling.
It uploads frozen bytes but does not execute code itself. Live mutation guards
in the low-level adapter remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Callable
from uuid import UUID

from .adapters import ExecutionRequest, ExecutionResult
from .nebius import (
    MAX_LOG_BYTES, NebiusSandboxAdapter, RemoteAdapterError, RemoteExecutionRequest,
    RemoteResult, UncertainSubmission, UploadedFile,
)
from .remote_journal import SubmissionConflict


GUEST_REPOSITORY = '/work/docdrift/repository'
GUEST_EXAMPLE = '/work/docdrift/example.py'
GUEST_RUNNER = '/work/docdrift/runner.py'
PYTHON_EXECUTABLE = '/usr/local/bin/python3.12'
MAX_SNAPSHOT_BYTES = 50 * 1024 * 1024
_FORBIDDEN = {'.git', '.aws', '.ssh', '.env', '.codex', '.agents'}
_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\Z')
# PYTHONPATH in the low-level contract is fixed to /work/docdrift. Keep the
# repository under its own directory so it cannot replace the controller runner.
RUNNER_BYTES = (
    'import os, runpy, sys\n'
    f'os.chdir({GUEST_REPOSITORY!r})\n'
    f'sys.path.insert(0, {GUEST_REPOSITORY!r})\n'
    f'runpy.run_path({GUEST_EXAMPLE!r}, run_name="__main__")\n'
).encode('utf-8')


def _image_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Sandbox image must be a canonical immutable UUID') from None
    if str(parsed) != value or parsed.int == 0:
        raise ValueError('Sandbox image must be a canonical immutable UUID')
    return value


def freeze_snapshot(snapshot: Path) -> dict[str, bytes]:
    """Read bounded regular files once; refuse metadata, symlinks and devices."""
    source = Path(snapshot)
    if source.is_symlink() or any(part in _FORBIDDEN for part in source.parts):
        raise ValueError('Sandbox snapshot cannot contain credential/metadata paths or symlinks')
    source = source.resolve(strict=True)
    if any(part in _FORBIDDEN for part in source.parts):
        raise ValueError('Sandbox snapshot resolves through a credential/metadata directory')
    if not source.is_dir():
        raise ValueError('Sandbox snapshot must be a directory')
    files: dict[str, bytes] = {}
    total = 0
    for directory, folders, names in os.walk(source, followlinks=False):
        for name in sorted(folders + names):
            path = Path(directory) / name
            if name in _FORBIDDEN or path.is_symlink():
                raise ValueError('Sandbox snapshot contains credential/metadata entries or symlinks')
            if not path.resolve(strict=True).is_relative_to(source):
                raise ValueError('Sandbox snapshot path escaped its root')
            mode = path.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError('Sandbox snapshot contains a nonregular file')
            if len(files) >= 1998:
                raise ValueError('Sandbox snapshot exceeds the 2000-file upload limit')
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError('Sandbox snapshot file changed type')
                content = stream.read(MAX_SNAPSHOT_BYTES - total + 1)
            total += len(content)
            if total > MAX_SNAPSHOT_BYTES:
                raise ValueError('Sandbox snapshot exceeds the 50 MiB upload limit')
            files[f'{GUEST_REPOSITORY}/{path.relative_to(source).as_posix()}'] = content
    return files


class SandboxExecutionAdapter:
    """An execution-shaped adapter that permits only explicit HTTP mocks."""

    backend_name = 'nebius_sandbox_simulation'
    scoped_execution = True
    synthetic = True

    def __init__(self, remote: NebiusSandboxAdapter):
        if not isinstance(remote, NebiusSandboxAdapter):
            raise TypeError('SandboxExecutionAdapter requires a NebiusSandboxAdapter')
        self.remote = remote
        self._require_simulation()
        if remote.journal is None:
            raise ValueError('Sandbox execution requires a durable submission journal')
        self._database = remote.journal.path
        with self._connection() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS sandbox_bridge_phases (
                    run_id TEXT NOT NULL, phase TEXT NOT NULL, request_digest TEXT NOT NULL,
                    image_id TEXT NOT NULL, PRIMARY KEY (run_id, phase)
                );
                CREATE TABLE IF NOT EXISTS sandbox_bridge_uploads (
                    sha256 TEXT PRIMARY KEY, state TEXT NOT NULL,
                    file_id TEXT, size INTEGER NOT NULL
                );
            ''')

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self._database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA synchronous = FULL')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _require_simulation(self) -> None:
        # The low-level guard checks the actual transport and every mount, not
        # merely a flag. Use it for GETs too, before any provider-capable method.
        self.remote._require_mutations()

    @property
    def execution_contract(self) -> dict:
        return {
            'executable': PYTHON_EXECUTABLE, 'arguments': ['-B', GUEST_RUNNER],
            'network': 'disabled_in_synthetic_request', 'synthetic': True,
            'repository_path': GUEST_REPOSITORY, 'code_executions': 0,
        }

    def preflight(self, image: str) -> dict:
        self._require_simulation()
        _image_uuid(image)
        information = self.remote.preflight(image)
        if information['permissions'].get('spawn_disposable') is not True:
            raise RemoteAdapterError('synthetic_spawn_permission_missing')
        return {
            **information, 'image': image, 'adapter': self.backend_name,
            'python_executable_contract': PYTHON_EXECUTABLE,
            'python_capability_tested': False, 'network': 'disabled_in_synthetic_request',
            'synthetic': True, 'code_executions': 0, 'live_requests': 0,
        }

    def _freeze(self, request: ExecutionRequest) -> tuple[dict[str, bytes], str]:
        _image_uuid(request.image)
        if type(request.timeout_seconds) is not int or not 1 <= request.timeout_seconds <= 30:
            raise ValueError('Sandbox execution timeout must be between 1 and 30 seconds')
        if type(request.log_limit_bytes) is not int or not 1 <= request.log_limit_bytes <= MAX_LOG_BYTES:
            raise ValueError('Invalid Sandbox output limit')
        if not isinstance(request.code, str) or len(request.code.encode('utf-8')) > MAX_LOG_BYTES:
            raise ValueError('Sandbox example exceeds the 256 KiB code limit')
        if set(request.environment) - {'DOCDRIFT_INPUT'}:
            raise ValueError('Only DOCDRIFT_INPUT may enter the Sandbox guest')
        if any(not isinstance(value, str) or '\x00' in value or len(value.encode('utf-8')) > 65_536 for value in request.environment.values()):
            raise ValueError('Invalid Sandbox guest environment')
        files = freeze_snapshot(request.snapshot)
        files[GUEST_EXAMPLE] = request.code.encode('utf-8')
        files[GUEST_RUNNER] = RUNNER_BYTES
        if sum(len(content) for content in files.values()) > MAX_SNAPSHOT_BYTES:
            raise ValueError('Sandbox uploads exceed the 50 MiB limit')
        identity = {
            'image_id': request.image, 'executable': PYTHON_EXECUTABLE,
            'args': ['-B', GUEST_RUNNER], 'environment': dict(request.environment),
            'timeout_seconds': request.timeout_seconds, 'log_limit_bytes': request.log_limit_bytes,
            'files': {path: hashlib.sha256(content).hexdigest() for path, content in sorted(files.items())},
            'disposable': True,
        }
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return files, digest

    def _freeze_phase(self, run_id: str, phase: str, digest: str, image_id: str) -> None:
        if any(not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None for value in [run_id, phase]):
            raise ValueError('Sandbox run and phase must be bounded machine identifiers')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            previous = connection.execute('SELECT request_digest, image_id FROM sandbox_bridge_phases WHERE run_id=? AND phase=?', (run_id, phase)).fetchone()
            if previous is not None:
                if previous['request_digest'] != digest or previous['image_id'] != image_id:
                    raise SubmissionConflict('Saved Sandbox phase inputs changed; reusing its result is forbidden')
            else:
                connection.execute('INSERT INTO sandbox_bridge_phases VALUES (?, ?, ?, ?)', (run_id, phase, digest, image_id))

    def _upload(self, path: str, content: bytes) -> UploadedFile:
        digest = hashlib.sha256(content).hexdigest()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            saved = connection.execute('SELECT * FROM sandbox_bridge_uploads WHERE sha256=?', (digest,)).fetchone()
            if saved is None:
                connection.execute('INSERT INTO sandbox_bridge_uploads VALUES (?, ?, NULL, ?)', (digest, 'submitting', len(content)))
            elif saved['state'] == 'accepted':
                return UploadedFile(saved['file_id'], digest, saved['size'])
            else:
                raise RemoteAdapterError('upload_uncertain_no_retry')
        try:
            uploaded = self.remote.prepare({path: content})[path]
        except BaseException:
            with self._connection() as connection:
                connection.execute('UPDATE sandbox_bridge_uploads SET state=? WHERE sha256=?', ('uncertain', digest))
            raise
        with self._connection() as connection:
            connection.execute('UPDATE sandbox_bridge_uploads SET state=?, file_id=?, size=? WHERE sha256=?', ('accepted', uploaded.uuid, uploaded.size, digest))
        return uploaded

    def execute(self, request: ExecutionRequest, on_accepted: Callable[[str], None], *, run_id: str, phase: str) -> ExecutionResult:
        self._require_simulation()
        files, digest = self._freeze(request)
        self._freeze_phase(run_id, phase, digest, request.image)
        receipt = self.recover(run_id, phase, expected_image_id=request.image)
        if receipt is not None:
            if receipt['operation_id']:
                callback_failed = False
                try:
                    on_accepted(receipt['operation_id'])
                except Exception:
                    callback_failed = True
                if callback_failed:
                    raise RemoteAdapterError('acceptance_callback_failed', operation_id=receipt['operation_id'], attempt_id=receipt['attempt_id'])
                return self.observe(receipt['operation_id'], timeout_seconds=request.timeout_seconds)
            if receipt['state'] == 'rejected':
                raise RemoteAdapterError('saved_submission_rejected_no_retry', attempt_id=receipt['attempt_id'])
            raise UncertainSubmission('saved_submission_cannot_retry', attempt_id=receipt['attempt_id'])
        uploaded = {path: self._upload(path, content) for path, content in sorted(files.items())}
        remote_request = RemoteExecutionRequest(
            image_id=request.image, executable=PYTHON_EXECUTABLE, args=('-B', GUEST_RUNNER),
            environment=request.environment, files=uploaded, disposable=True,
            timeout_seconds=request.timeout_seconds, log_limit_bytes=request.log_limit_bytes,
        )
        operation_id = self.remote.submit(remote_request, on_accepted, run_id=run_id, phase=phase)
        return self.observe(operation_id, timeout_seconds=request.timeout_seconds)

    def recover(self, run_id: str, phase: str, *, expected_image_id: str) -> dict | None:
        self._require_simulation()
        _image_uuid(expected_image_id)
        with self._connection() as connection:
            saved = connection.execute('SELECT image_id FROM sandbox_bridge_phases WHERE run_id=? AND phase=?', (run_id, phase)).fetchone()
        receipt = self.remote.journal.lookup(run_id, phase)
        if receipt and (saved is None or saved['image_id'] != expected_image_id):
            raise SubmissionConflict('Sandbox recovery image or frozen phase identity is missing or changed')
        return self.remote.recover(run_id, phase, expected_image_id=expected_image_id, expected_disposable=True) if receipt else None

    @staticmethod
    def _result(result: RemoteResult) -> ExecutionResult:
        return ExecutionResult(
            state=result.state, exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr,
            operation_id=result.operation_id, image_id=result.image_id, elapsed_seconds=result.elapsed_seconds,
            timed_out=result.timed_out, stdout_truncated=result.stdout_truncated, stderr_truncated=result.stderr_truncated,
            service_state=result.service_state, signal=result.signal,
            observation_timed_out=result.observation_timed_out, evidence_complete=result.evidence_complete,
            synthetic=True, error_code=result.error_code,
        )

    def observe(self, operation_id: str, timeout_seconds: float = 30, **kwargs) -> ExecutionResult:
        self._require_simulation()
        if operation_id not in self.remote._accepted:
            raise RemoteAdapterError('operation_not_owned', operation_id=operation_id)
        return self._result(self.remote.observe(operation_id, timeout_seconds, **kwargs))

    def cancel(self, operation_id: str) -> None:
        self._require_simulation()
        self.remote.cancel(operation_id)

    def release(self, result: dict) -> None:
        """Disposable simulation needs no DELETE after completion or timeout."""
        self._require_simulation()

    def close(self) -> None:
        self.remote.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
