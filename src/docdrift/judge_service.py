"""One private judge deployment: controller, single worker, and operator commands."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from .judge_store import AdmissionError, JudgeStore, IMAGE_ID, LIMITS, MODEL, PROJECT_ID

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = ROOT / '.docdrift/judge'
DEFAULT_AUTHORIZATION = ROOT / '.docdrift/access/judge-authorization-2026-10-22.json'
_SECRET = re.compile(r'(?i)(?:\btvly-[A-Za-z0-9_-]{12,}|\blsv2_[A-Za-z0-9_-]{12,}|\bsk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})')


def write_json(path: Path, value):
    from .sandbox_live import _write
    _write(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode())


def prepare(path: Path, root: Path):
    """Record the user's Oct 22 answers, offline; no credential is read."""
    record = {
        'kind': 'docdrift_judge_authorization', 'project_id': PROJECT_ID,
        'image_id': IMAGE_ID, 'model': MODEL, 'user_authorized_bounded_runs': True,
        'authorized_at_utc': '2026-10-22T00:00:00+00:00',
        'authorization_time_precision': 'date_only',
        'funding_intent': 'granted_credits_only', 'billing_coverage': 'unverified',
        'reported_credit_balance_usd': '30.98', 'credit_balance_source': 'user_report_2026_10_22',
        'state_root': str(root.resolve()), 'limits': LIMITS,
        'expires_at_utc': '2026-12-16T00:00:00+00:00',
        'source': 'User approved hosted VPS route, existing credentials, 20 attempts and held-out comparison; will inspect usage personally.',
    }
    if path.exists():
        store = JudgeStore(root, path)
        if store.config != record:
            raise AdmissionError('existing_authorization_differs')
    else:
        write_json(path, record)
        JudgeStore(root, path)
    return {'status': 'prepared_offline', 'authorization': str(path), 'state_root': str(root),
            'provider_requests': 0, 'inference_calls': 0, 'limits': LIMITS,
            'billing_coverage': 'unverified', 'funding_intent': 'granted_credits_only'}


def controller_fingerprint():
    return hashlib.sha256(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in sorted(Path(__file__).parent.glob('*.py'))}, sort_keys=True).encode()).hexdigest()


class BoundedModel:
    def __init__(self, client, store, job):
        self.client, self.store, self.job = client, store, job
        self.live, self.model = client.live, client.model

    def complete(self, messages, tools, max_tokens):
        ordinal = self.store.reserve(self.job['id'], self.job['worker_token'], 'model')
        try:
            response = self.client.complete(messages, tools, max_tokens)
            write_json(self.store.root / 'jobs' / self.job['id'] / 'model-calls' / f'{ordinal}.json', response)
        except BaseException:
            self.store.finish_model(self.job['id'], ordinal, 'uncertain')
            raise
        self.store.finish_model(self.job['id'], ordinal, 'completed')
        return response


def _sanitize(value):
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        value = value.replace(PROJECT_ID, 'REDACTED_NEBIUS_PROJECT_ID')
        return re.sub(r'/(?:home|root|tmp)/[^\s\"<>\]]+', 'REDACTED_CONTROLLER_PATH', value)
    return value


def publish_evidence(state_root: Path, run_id: str, destination: Path, *, forbidden=(), purpose='judge'):
    """Build presentation copies; never expose the original provider/state files."""
    from .evidence import verify_evidence
    from .review import render_review
    source = state_root / 'runs' / run_id / 'evidence.zip'
    original_integrity = verify_evidence(source)
    with zipfile.ZipFile(source) as archive:
        original = {name: archive.read(name) for name in archive.namelist()}
    forbidden_bytes = tuple(value.encode() if isinstance(value, str) else value for value in forbidden if value)
    if any(secret in data or secret in name.encode() for secret in forbidden_bytes for name, data in original.items()):
        raise ValueError('credential_in_private_evidence_no_publication')
    members = dict(original)
    redacted = []
    for name, data in original.items():
        if name.endswith('.json') and name != 'manifest.json':
            sanitized = _sanitize(json.loads(data))
            members[name] = (json.dumps(sanitized, indent=2, ensure_ascii=False) + '\n').encode()
            if members[name] != data:
                redacted.append(name)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='judge-presentation-', dir=destination.parent) as directory:
        staged = Path(directory)
        for name, data in members.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        review = render_review(json.loads(members['report.json']), staged, archive_available=True)
        scope = 'owned held-out fixture' if purpose == 'held_out' else 'owned development fixture'
        notice = ('<p class="qualification">Fresh run on one ' + scope + '. '
                  'Presentation copies redact controller paths and project metadata. '
                  'The unsigned manifest checks internal bytes, not authenticity or execution attestation. '
                  'Billing coverage remains unverified.</p>')
        members['review.html'] = review.replace('<main>', '<main>' + notice, 1).encode()
        provenance = {'kind': 'judge_evidence_presentation',
                      'original_archive_sha256': original_integrity['archive_sha256'],
                      'original_member_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in original.items()},
                      'reserialized_json_files': redacted,
                      'redactions': ['Controller host paths', 'Nebius project identifier'],
                      'other_changes': ['Regenerated HTML and unsigned manifest'],
                      'execution_attested': False, 'authenticity_attested': False}
        members['presentation.json'] = (json.dumps(provenance, indent=2) + '\n').encode()
        for name, data in members.items():
            if name == 'manifest.json':
                continue
            text = data.decode('utf-8')
            if _SECRET.search(text) or PROJECT_ID in text or any(secret in data for secret in forbidden_bytes):
                raise ValueError('unsafe_presentation_artifact')
            if re.search(r'/(?:home|root|tmp)/[^\s\"<>]+', text):
                raise ValueError('private_path_in_presentation_artifact')
        members['manifest.json'] = (json.dumps({'algorithm': 'sha256', 'files': {
            name: hashlib.sha256(data).hexdigest() for name, data in sorted(members.items())
            if name != 'manifest.json'}}, indent=2) + '\n').encode()
        for name, data in members.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        (staged / 'evidence.zip').write_bytes(stream.getvalue())
        verify_evidence(staged / 'evidence.zip')
        if destination.exists():
            raise ValueError('presentation_already_exists')
        staged.rename(destination)


def run_job(store, job, *, client_factory=None, adapter_factory=None, evaluator=None):
    from .evaluation import evaluate_fixture
    from .judge_live import JudgeExecutionAdapter
    from .repair import TokenFactoryClient
    from .sandbox_live import _write
    fixture = ROOT / 'fixtures' / ('development/source_only' if job['fixture'] == 'source_only'
                                  else 'evaluation/' + job['fixture'])
    state = store.root / 'jobs' / job['id']
    adapter = None
    try:
        if job['purpose'] == 'held_out':
            with store.connection() as db:
                if store._meta(db, 'held_out_freeze') != controller_fingerprint():
                    raise AdmissionError('held_out_controller_changed')
        key = os.environ.get('NEBIUS_API_KEY', '')
        if not key and client_factory is None:
            raise AdmissionError('nebius_key_missing')
        client = (client_factory or (lambda: TokenFactoryClient(MODEL, key)))()
        wrapped = BoundedModel(client, store, job)
        adapter = (adapter_factory or JudgeExecutionAdapter)(
            key, state, fixture,
            lambda: store.reserve(job['id'], job['worker_token'], 'sandbox'), capability=store.capability())
        row = (evaluator or evaluate_fixture)(fixture, job['strategy'], wrapped, state, IMAGE_ID, adapter=adapter)
        write_json(state / 'outcome.json', row)
        artifacts = False
        if row.get('run_id'):
            publish_evidence(state, row['run_id'], state / 'public', forbidden=(key,), purpose=job['purpose'])
            artifacts = True
        store.finish(job['id'], job['worker_token'], result={'outcome': row.get('outcome'), 'has_artifacts': artifacts})
    except Exception as exc:
        # Preserve private journals/accepted IDs; only safe machine codes enter HTTP.
        code = str(exc) if isinstance(exc, AdmissionError) else 'judge_run_failed_see_private_receipts'
        store.finish(job['id'], job['worker_token'], error_code=code)
    finally:
        if adapter is not None:
            adapter.close()


def worker(store, *, once=False, job_runner=run_job):
    lock_path = store.root / 'worker.lock'
    with lock_path.open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AdmissionError('judge_worker_already_running') from None
        store.interrupt_abandoned()
        while True:
            store.heartbeat()
            job = store.claim()
            if job:
                job_runner(store, job)
            if once:
                return
            time.sleep(2)


def held_out(store):
    freeze = controller_fingerprint()
    result = []
    for fixture in ('renamed_import', 'changed_return_shape'):
        for strategy in ('one_shot', 'agent'):
            request = uuid.uuid5(uuid.NAMESPACE_URL, f'docdrift-held-out-once:{fixture}:{strategy}').hex
            result.append(store.admit(request, fixture=fixture, strategy=strategy, purpose='held_out', freeze=freeze))
    return {'status': 'held_out_queued_once', 'controller_sha256': freeze, 'jobs': result}


def held_out_report(store):
    """Summarize the four once-only jobs offline, including unsuccessful outcomes."""
    with store.connection() as db:
        jobs = [dict(row) for row in db.execute("SELECT * FROM judge_jobs WHERE purpose='held_out' ORDER BY fixture,strategy")]
        freeze = store._meta(db, 'held_out_freeze')
    rows = []
    for job in jobs:
        path = store.root / 'jobs' / job['id'] / 'outcome.json'
        outcome = json.loads(path.read_bytes()) if path.is_file() else {}
        row = {'case': job['fixture'], 'strategy': job['strategy'], 'split': 'held_out',
               'job_id': job['id'], 'job_status': job['status'], 'error_code': job['error_code'],
               'model_calls_attempted': job['model_calls'], 'guest_operations_attempted': job['guest_operations'],
               'scored': job['status'] == 'completed' and outcome.get('evidence') == 'live_inference',
               'verified': outcome.get('verified') is True}
        row.update({key: outcome[key] for key in ('detected', 'outcome', 'usage', 'run_id', 'proposal_sha256') if key in outcome})
        rows.append(row)
    report = {'kind': 'docdrift_held_out_judge_comparison',
              'status': 'completed' if len(rows) == 4 and all(row['scored'] for row in rows) else 'incomplete',
              'controller_sha256': freeze,
              'inventory_sha256': hashlib.sha256((ROOT / 'fixtures/evaluation/index.json').read_bytes()).hexdigest(),
              'scope': 'Two reserved owned broken cases, one_shot and agent once each; earlier development results are separate.',
              'billing_coverage': 'unverified', 'rows': rows,
              'summary': {strategy: {'planned_cases': 2,
                                    'completed_scored_cases': sum(row['scored'] for row in rows if row['strategy'] == strategy),
                                    'verified_cases': sum(row['verified'] and row['scored'] for row in rows if row['strategy'] == strategy)}
                          for strategy in ('one_shot', 'agent')}}
    write_json(store.root / 'held-out-comparison.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'activate', 'status', 'web', 'worker', 'held-out', 'held-out-report'))
    parser.add_argument('--state-root', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--authorization', type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'prepare':
            result = prepare(args.authorization, args.state_root)
        else:
            store = JudgeStore(args.state_root, args.authorization)
            if args.command == 'status':
                result = store.summary()
            elif args.command == 'held-out-report':
                result = held_out_report(store)
            elif args.command == 'web':
                from .judge_web import serve
                serve(store, password_sha256=os.environ.get('DOCDRIFT_JUDGE_PASSWORD_SHA256', ''),
                      public_origin=os.environ.get('DOCDRIFT_JUDGE_PUBLIC_ORIGIN', ''), host=args.host, port=args.port)
                return 0
            else:
                if not args.live:
                    raise AdmissionError('explicit_live_flag_required')
                if args.command == 'activate':
                    from .judge_live import run_capability
                    key = os.environ.get('NEBIUS_API_KEY', '')
                    if not key:
                        raise AdmissionError('nebius_key_missing')
                    lock = store.root / 'activation.lock'
                    with lock.open('a+b') as stream:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        value = run_capability(key, store.root / 'startup', store.reserve_capability)
                        store.record_capability(value)
                    result = {'status': 'activated', 'capability': value, 'billing_coverage': 'unverified'}
                elif args.command == 'worker':
                    if not os.environ.get('NEBIUS_API_KEY'):
                        raise AdmissionError('nebius_key_missing')
                    worker(store, once=args.once)
                    return 0
                else:
                    result = held_out(store)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        code = str(exc) if isinstance(exc, AdmissionError) else 'judge_command_failed'
        print(json.dumps({'status': 'blocked', 'error_code': code}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
