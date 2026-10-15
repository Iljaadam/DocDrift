"""Persistent HTTP mocks for explicitly supplied owned fixture contracts.

No Python from uploads, examples, checks or packages is imported or executed.
Responses are manufactured from profile examples and expected JSON, and are
never evidence of remote execution or model behavior.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from .markdown import extract_examples
from .nebius import NebiusSandboxAdapter
from .profile import load_profile, operation_present
from .remote_journal import SubmissionJournal
from .sandbox_execution import (
    GUEST_EXAMPLE, GUEST_REPOSITORY, GUEST_RUNNER, PYTHON_EXECUTABLE,
    RUNNER_BYTES, SandboxExecutionAdapter, freeze_snapshot,
)


IMAGE_ID = '11111111-1111-4111-8111-111111111111'


class FixtureSandboxSimulation:
    """Synthetic service state survives restarts; only frozen fixtures match."""

    def __init__(self, state_root: Path):
        journal = SubmissionJournal(state_root)
        self.database = journal.path
        self.requests: list[tuple[str, str]] = []
        self._contracts: list[dict] = []
        with self._connection() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS sandbox_mock_files (
                    uuid TEXT PRIMARY KEY, content BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sandbox_mock_operations (
                    uuid TEXT PRIMARY KEY, response_json TEXT NOT NULL
                );
            ''')
        self.transport = httpx.MockTransport(self.handle)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.execute('PRAGMA synchronous = FULL')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def register_profile(self, repository: Path, profile: Path, repair_code: str) -> None:
        """Register exact curated code/input pairs without running that code."""
        specification, _ = load_profile(profile)
        if not str(specification.get('name', '')).startswith('owned-'):
            raise ValueError('Sandbox simulation accepts only explicitly labelled owned fixtures')
        frozen = freeze_snapshot(repository)
        documentation = {f'{GUEST_REPOSITORY}/{path}' for path in specification['documentation']}
        source_files = {path: hashlib.sha256(content).hexdigest() for path, content in frozen.items() if path not in documentation}
        responses = {}
        for example in specification['examples']:
            path = example['path']
            original = extract_examples(path, frozen[f'{GUEST_REPOSITORY}/{path}'])[example['ordinal']].code
            known_code = repair_code if example['role'] == 'target' else original
            for case in example['cases']:
                value = case['env']['DOCDRIFT_INPUT']
                responses[(known_code, value)] = (0, json.dumps(case['expected_json'], ensure_ascii=False) + '\n', '')
                if example['role'] == 'target' and original != known_code:
                    # This is an explicitly invented baseline response, not an
                    # observed exception. Preserve the exit-zero drift shape.
                    responses[(original, value)] = (
                        (0, json.dumps('synthetic_original_mismatch') + '\n', '')
                        if operation_present(original, example['required_call']) else
                        (1, '', 'Synthetic fixture original failure; no code was executed.\n')
                    )
        self._contracts.append({'source_files': source_files, 'documentation': documentation, 'responses': responses})

    def register_run(self, run_root: Path) -> None:
        self.register_profile(run_root / 'original', run_root / 'profile' / 'profile.json', (run_root / 'replacement.py').read_text())

    def _observation(self, payload: dict) -> tuple[int, str, str]:
        if (payload.get('image') != IMAGE_ID or payload.get('command') != PYTHON_EXECUTABLE
                or payload.get('args') != ['-B', GUEST_RUNNER]
                or payload.get('shell') is not False or payload.get('preserve_env') is not False
                or payload.get('networking') != {'enabled': False}):
            return 1, '', 'Synthetic request contract mismatch; no code was executed.\n'
        files = {}
        with self._connection() as connection:
            for path, record in payload.get('files', {}).items():
                uploaded = connection.execute('SELECT content FROM sandbox_mock_files WHERE uuid=?', (record.get('uuid'),)).fetchone()
                if uploaded is None:
                    return 1, '', 'Synthetic upload identity unavailable; no code was executed.\n'
                files[path] = bytes(uploaded[0])
        if files.get(GUEST_RUNNER) != RUNNER_BYTES:
            return 1, '', 'Synthetic runner mismatch; no code was executed.\n'
        try:
            code = files.get(GUEST_EXAMPLE, b'').decode('utf-8')
        except UnicodeError:
            return 1, '', 'Synthetic code encoding mismatch; no code was executed.\n'
        value = payload.get('env', {}).get('DOCDRIFT_INPUT')
        for contract in self._contracts:
            source_files = {path: hashlib.sha256(content).hexdigest() for path, content in files.items()
                            if path.startswith(GUEST_REPOSITORY + '/') and path not in contract['documentation']}
            if source_files == contract['source_files'] and (code, value) in contract['responses']:
                return contract['responses'][(code, value)]
        return 1, '', 'No frozen synthetic fixture response matches these bytes and input; no code was executed.\n'

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix('/sandboxes/v1/')
        self.requests.append((request.method, path))
        if request.method == 'GET' and path == 'whoami':
            return httpx.Response(200, json={'permissions': {'spawn_disposable': True, 'cancel': True}, 'limits': {'instance_max_concurrency': 1}})
        if request.method == 'GET' and path == f'inspect/{IMAGE_ID}/':
            return httpx.Response(200, json={'uuid': IMAGE_ID})
        if request.method == 'POST' and path == 'files':
            file_id = str(uuid4())
            with self._connection() as connection:
                connection.execute('INSERT INTO sandbox_mock_files VALUES (?, ?)', (file_id, request.content))
            return httpx.Response(201, json={'uuid': file_id, 'sha256': hashlib.sha256(request.content).hexdigest(), 'size': len(request.content)})
        if request.method == 'POST' and path == 'instances':
            payload = json.loads(request.content)
            exit_code, stdout, stderr = self._observation(payload)
            limit = payload.get('truncate_output_at', 262_144)
            def stream(value):
                raw = value.encode('utf-8')
                return {'value': base64.b64encode(raw[:limit]).decode(), 'encoding': 'base64', 'truncated': len(raw) > limit}
            operation_id = str(uuid4())
            response = {
                'uuid': operation_id, 'kind': 'instance', 'status': 'SUCCESS', 'image_uuid': payload['image'],
                'result_image_uuid': None, 'duration': None,
                'metadata': {**payload, 'result': {
                    'state': {'exit_code': exit_code, 'signal': None, 'timed_out': False},
                    'stdout': stream(stdout), 'stderr': stream(stderr), 'resources': {},
                }},
            }
            with self._connection() as connection:
                connection.execute('INSERT INTO sandbox_mock_operations VALUES (?, ?)', (operation_id, json.dumps(response)))
            return httpx.Response(201, json={'uuid': operation_id})
        if path.startswith('operations/') and request.method in {'GET', 'DELETE'}:
            operation_id = path.removeprefix('operations/')
            with self._connection() as connection:
                row = connection.execute('SELECT response_json FROM sandbox_mock_operations WHERE uuid=?', (operation_id,)).fetchone()
                if row is None:
                    return httpx.Response(404, json={})
                response = json.loads(row[0])
                if request.method == 'DELETE':
                    response['status'] = 'CANCELLED'
                    connection.execute('UPDATE sandbox_mock_operations SET response_json=? WHERE uuid=?', (json.dumps(response), operation_id))
                    return httpx.Response(202)
            return httpx.Response(200, json=response)
        return httpx.Response(404, json={})


def create_fixture_simulation(state_root: Path, fixtures: list[Path]) -> SandboxExecutionAdapter:
    """Build an explicit zero-network mock; supplied fixtures are curator input."""
    service = FixtureSandboxSimulation(state_root)
    for fixture in fixtures:
        specification, _ = load_profile(fixture / 'profile.json')
        service.register_profile(fixture / 'repository', fixture / 'profile.json', (fixture / specification.get('known_repair', 'repair.py')).read_text())
    remote = NebiusSandboxAdapter(
        'synthetic-no-provider-key', 'synthetic-no-provider-project',
        transport=service.transport, offline_simulation=True, journal=SubmissionJournal(state_root),
    )
    bridge = SandboxExecutionAdapter(remote)
    bridge.simulation = service
    return bridge
