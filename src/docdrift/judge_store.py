"""Durable admission and attempt accounting for the one fixed judge deployment."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .profile import strict_json
from .sandbox_plan import _read_regular

PROJECT_ID = 'aiproject-e00a0rb50jb0emajfv'
IMAGE_ID = '4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae'
MODEL = 'nvidia/nemotron-3-super-120b-a12b'
LIMITS = {'attempts': 20, 'held_out_reserved_attempts': 4,
          'model_calls_per_attempt': 8, 'sandbox_operations_per_attempt': 17,
          'capability_operations': 1}
FIXTURES = {'source_only', 'renamed_import', 'changed_return_shape'}
_JOB = re.compile(r'[0-9a-f]{32}\Z')


class AdmissionError(ValueError):
    pass


def utc(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def authorization(path: Path, root: Path) -> tuple[dict, str]:
    data = _read_regular(path, 16384)
    value = strict_json(data)
    if (path.stat().st_mode & 0o777 != 0o600 or not isinstance(value, dict)
            or value.get('kind') != 'docdrift_judge_authorization'
            or value.get('project_id') != PROJECT_ID or value.get('image_id') != IMAGE_ID
            or value.get('model') != MODEL or value.get('limits') != LIMITS
            or value.get('user_authorized_bounded_runs') is not True
            or value.get('funding_intent') != 'granted_credits_only'
            or value.get('billing_coverage') != 'unverified'
            or value.get('state_root') != str(root.resolve())
            or value.get('expires_at_utc') != '2026-12-16T00:00:00+00:00'
            or 'sandbox-f6' in root.resolve().parts):
        raise AdmissionError('invalid_judge_authorization')
    return value, hashlib.sha256(data).hexdigest()


class JudgeStore:
    def __init__(self, root: Path, authorization_path: Path, *, clock=time.time):
        self.root = Path(root).resolve()
        self.authorization_path = Path(authorization_path).resolve()
        self.clock = clock
        self.config, self.authorization_sha256 = authorization(self.authorization_path, self.root)
        self.expires = datetime.fromisoformat(self.config['expires_at_utc']).timestamp()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'judge.sqlite3'
        binding_path = self.authorization_path.with_suffix('.state.json')
        binding = strict_json(_read_regular(binding_path, 16384)) if binding_path.exists() else None
        if binding is not None and not self.path.is_file():
            raise AdmissionError('judge_state_missing_preserve_allowance')
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS judge_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS judge_jobs (
                  id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                  fixture TEXT NOT NULL, strategy TEXT NOT NULL, purpose TEXT NOT NULL,
                  status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                  model_calls INTEGER NOT NULL DEFAULT 0, guest_operations INTEGER NOT NULL DEFAULT 0,
                  worker_token TEXT, result TEXT, error_code TEXT,
                  UNIQUE(purpose, fixture, strategy, request_key)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS judge_heldout_once
                  ON judge_jobs(fixture,strategy) WHERE purpose='held_out';
                CREATE TABLE IF NOT EXISTS judge_model_calls (
                  job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL,
                  PRIMARY KEY(job_id,ordinal)
                );
            ''')
            db.execute('BEGIN IMMEDIATE')
            saved = db.execute("SELECT value FROM judge_meta WHERE key='authorization_sha256'").fetchone()
            if saved is None:
                db.execute('INSERT INTO judge_meta VALUES (?,?)', ('authorization_sha256', self.authorization_sha256))
            elif saved['value'] != self.authorization_sha256:
                raise AdmissionError('judge_authorization_changed')
            deployment_id = self._meta(db, 'deployment_id')
            if deployment_id is None:
                deployment_id = uuid.uuid4().hex
                self._set(db, 'deployment_id', deployment_id)
            expected_binding = {'deployment_id': deployment_id, 'state_root': str(self.root),
                                'authorization_sha256': self.authorization_sha256}
            if binding is not None and binding != expected_binding:
                raise AdmissionError('judge_deployment_state_changed')
        if binding is None:
            from .sandbox_live import _write
            _write(binding_path, (json.dumps(expected_binding, sort_keys=True) + '\n').encode())
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _check(self):
        _, digest = authorization(self.authorization_path, self.root)
        if digest != self.authorization_sha256:
            raise AdmissionError('judge_authorization_changed')

    @staticmethod
    def _meta(db, key, default=None):
        row = db.execute('SELECT value FROM judge_meta WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    @staticmethod
    def _set(db, key, value):
        db.execute('INSERT INTO judge_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

    def capability(self) -> dict | None:
        self._check()
        with self.connection() as db:
            value = self._meta(db, 'capability')
        if value:
            from .judge_live import _capability
            return _capability(json.loads(value))
        return None

    def reserve_capability(self):
        self._check()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._meta(db, 'capability_attempt') is not None:
                raise AdmissionError('capability_attempt_already_reserved')
            if self.clock() >= self.expires:
                raise AdmissionError('judging_expired')
            self._set(db, 'capability_attempt', 'reserved')

    def record_capability(self, value: dict):
        self._check()
        from .judge_live import _capability
        value = _capability(value)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._meta(db, 'capability_attempt') != 'reserved':
                raise AdmissionError('capability_not_reserved')
            previous = self._meta(db, 'capability')
            encoded = json.dumps(value, sort_keys=True)
            if previous is not None and previous != encoded:
                raise AdmissionError('capability_changed')
            self._set(db, 'capability', encoded)

    def heartbeat(self):
        with self.connection() as db:
            self._set(db, 'worker_heartbeat', self.clock())

    def _reason(self, db):
        if self.clock() >= self.expires:
            return 'judging_expired'
        if self._meta(db, 'paused') == 'true':
            return 'admission_paused'
        if self._meta(db, 'capability') is None:
            return 'activation_required'
        if self.clock() - float(self._meta(db, 'worker_heartbeat', '0')) > 180:
            return 'worker_unavailable'
        return None

    def summary(self):
        self._check()
        with self.connection() as db:
            total = db.execute('SELECT count(*) FROM judge_jobs').fetchone()[0]
            public = db.execute("SELECT count(*) FROM judge_jobs WHERE purpose='judge'").fetchone()[0]
            pending = db.execute("SELECT count(*) FROM judge_jobs WHERE status IN ('queued','running')").fetchone()[0]
            reason = self._reason(db)
        remaining = min(20 - total, 16 - public)
        if not reason and remaining <= 0:
            reason = 'attempt_limit_reached'
        return {'live_ready': reason is None, 'admission_reason': reason,
                'attempts_used': total, 'attempts_limit': 20,
                'attempts_remaining': max(0, remaining), 'pending_jobs': pending,
                'held_out_reserved_attempts': 4, 'expires_at_utc': self.config['expires_at_utc'],
                'billing_coverage': 'unverified', 'funding_intent': 'granted_credits_only'}

    def admit(self, request_key: str, *, fixture='source_only', strategy='agent', purpose='judge', freeze=None):
        self._check()
        try:
            parsed = uuid.UUID(request_key)
            if request_key not in {parsed.hex, str(parsed)} or not parsed.int:
                raise ValueError
            request_key = parsed.hex
        except (ValueError, AttributeError, TypeError):
            raise AdmissionError('invalid_request_key') from None
        if (fixture not in FIXTURES or strategy not in {'agent', 'one_shot'}
                or purpose not in {'judge', 'held_out'}
                or (purpose == 'judge' and (fixture != 'source_only' or strategy != 'agent'))
                or (purpose == 'held_out' and fixture == 'source_only')):
            raise AdmissionError('unsupported_fixed_case')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM judge_jobs WHERE request_key=?', (request_key,)).fetchone()
            if old:
                if (old['fixture'], old['strategy'], old['purpose']) != (fixture, strategy, purpose):
                    raise AdmissionError('request_key_conflict')
                return self._public(old)
            reason = self._reason(db)
            if reason:
                raise AdmissionError(reason)
            total = db.execute('SELECT count(*) FROM judge_jobs').fetchone()[0]
            public = db.execute("SELECT count(*) FROM judge_jobs WHERE purpose='judge'").fetchone()[0]
            if total >= 20 or (purpose == 'judge' and public >= 16):
                raise AdmissionError('attempt_limit_reached')
            queue_limit = 4 if purpose == 'held_out' else 3
            if db.execute("SELECT count(*) FROM judge_jobs WHERE status='queued'").fetchone()[0] >= queue_limit:
                raise AdmissionError('queue_full')
            if purpose == 'held_out':
                if not isinstance(freeze, str) or re.fullmatch('[0-9a-f]{64}', freeze) is None:
                    raise AdmissionError('held_out_freeze_required')
                old_freeze = self._meta(db, 'held_out_freeze')
                if old_freeze not in (None, freeze):
                    raise AdmissionError('held_out_controller_changed')
                self._set(db, 'held_out_freeze', freeze)
                old = db.execute("SELECT * FROM judge_jobs WHERE purpose='held_out' AND fixture=? AND strategy=?", (fixture, strategy)).fetchone()
                if old:
                    return self._public(old)
            now = self.clock()
            job_id = uuid.uuid4().hex
            db.execute('INSERT INTO judge_jobs(id,request_key,fixture,strategy,purpose,status,created,updated) VALUES (?,?,?,?,?,?,?,?)',
                       (job_id, request_key, fixture, strategy, purpose, 'queued', now, now))
            return self._public(db.execute('SELECT * FROM judge_jobs WHERE id=?', (job_id,)).fetchone())

    @staticmethod
    def _public(row):
        result = json.loads(row['result']) if row['result'] else {}
        return {'id': row['id'], 'status': row['status'], 'created_at': utc(row['created']),
                'updated_at': utc(row['updated']), 'outcome': result.get('outcome'),
                'has_artifacts': result.get('has_artifacts') is True,
                'error_code': row['error_code'], 'model_calls': row['model_calls'],
                'guest_operations': row['guest_operations']}

    def get(self, job_id):
        if not isinstance(job_id, str) or _JOB.fullmatch(job_id) is None:
            return None
        with self.connection() as db:
            row = db.execute('SELECT * FROM judge_jobs WHERE id=?', (job_id,)).fetchone()
        return self._public(row) if row else None

    def list_jobs(self):
        with self.connection() as db:
            return [self._public(row) for row in db.execute('SELECT * FROM judge_jobs ORDER BY created DESC LIMIT 20')]

    def claim(self):
        self._check()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM judge_jobs WHERE status='running'").fetchone():
                return None
            if self._reason(db):
                return None
            row = db.execute("SELECT * FROM judge_jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            token = uuid.uuid4().hex
            db.execute("UPDATE judge_jobs SET status='running',worker_token=?,updated=? WHERE id=?", (token, self.clock(), row['id']))
            return dict(db.execute('SELECT * FROM judge_jobs WHERE id=?', (row['id'],)).fetchone())

    def reserve(self, job_id, token, kind):
        self._check()
        column, limit = {'model': ('model_calls', 8), 'sandbox': ('guest_operations', 17)}[kind]
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM judge_jobs WHERE id=? AND worker_token=? AND status='running'", (job_id, token)).fetchone()
            if not row:
                raise AdmissionError('worker_claim_lost')
            if self.clock() >= self.expires:
                raise AdmissionError('judging_expired')
            if row[column] >= limit:
                raise AdmissionError(kind + '_attempt_limit')
            ordinal = row[column] + 1
            db.execute(f'UPDATE judge_jobs SET {column}=?,updated=? WHERE id=?', (ordinal, self.clock(), job_id))
            self._set(db, 'worker_heartbeat', self.clock())
            if kind == 'model':
                db.execute('INSERT INTO judge_model_calls VALUES (?,?,?)', (job_id, ordinal, 'reserved'))
            return ordinal

    def finish_model(self, job_id, ordinal, state):
        if state not in {'completed', 'uncertain'}:
            raise ValueError('invalid_model_call_state')
        with self.connection() as db:
            db.execute('UPDATE judge_model_calls SET state=? WHERE job_id=? AND ordinal=?', (state, job_id, ordinal))

    def finish(self, job_id, token, *, result=None, error_code=None):
        if error_code is not None and re.fullmatch('[a-z_]{1,80}', error_code) is None:
            raise ValueError('unsafe_error_code')
        safe = {key: (result or {}).get(key) for key in ('outcome', 'has_artifacts')}
        with self.connection() as db:
            count = db.execute("UPDATE judge_jobs SET status=?,result=?,error_code=?,updated=? WHERE id=? AND worker_token=? AND status='running'",
                               ('failed' if error_code else 'completed', json.dumps(safe), error_code, self.clock(), job_id, token)).rowcount
            if count != 1:
                raise AdmissionError('worker_claim_lost')
            if error_code:
                # An exception may leave an accepted remote operation in flight.
                # Do not start another job before the operator reconciles it.
                self._set(db, 'paused', 'true')

    def interrupt_abandoned(self):
        """Call only while holding the exclusive process worker lock."""
        with self.connection() as db:
            count = db.execute("UPDATE judge_jobs SET status='interrupted',error_code='worker_interrupted_no_automatic_retry',updated=? WHERE status='running'", (self.clock(),)).rowcount
            if count:
                self._set(db, 'paused', 'true')

    def job_artifact(self, job_id, name):
        job = self.get(job_id)
        if not job or job['status'] != 'completed' or not job['has_artifacts'] or name not in {'review.html', 'evidence.zip'}:
            return None
        path = self.root / 'jobs' / job_id / 'public' / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.root):
            return None
        return path
