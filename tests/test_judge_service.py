"""Judge limits and worker tests use manufactured responses and no providers."""
import hashlib
import json
import shutil
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from docdrift.judge_service import BoundedModel, held_out, held_out_report, prepare, publish_evidence, run_job, worker
from docdrift.judge_store import AdmissionError, IMAGE_ID, JudgeStore, PROJECT_ID

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY = {'kind': 'docdrift_judge_sandbox_capability', 'status': 'verified',
              'project_id': PROJECT_ID, 'image_id': IMAGE_ID,
              'operation_id': '11111111-1111-4111-8111-111111111111',
              'python': [3, 12], 'euid': 65534, 'interfaces': ['lo'], 'synthetic': False}


def make_store(tmp_path, *, ready=True):
    root, auth = tmp_path / 'judge', tmp_path / 'access' / 'authorization.json'
    prepare(auth, root)
    clock = [1792627200.0]  # Oct 22; stable manufactured test clock.
    store = JudgeStore(root, auth, clock=lambda: clock[0])
    if ready:
        store.reserve_capability()
        store.record_capability(CAPABILITY)
        store.heartbeat()
    return store, clock


def admit(store):
    return store.admit(uuid.uuid4().hex)


def complete(store):
    job = store.claim()
    assert job is not None
    store.finish(job['id'], job['worker_token'], result={'outcome': 'behavior_verified'})
    return job


def test_offline_prepare_is_private_idempotent_and_scope_bound(tmp_path):
    store, _ = make_store(tmp_path, ready=False)
    first = store.authorization_path.read_bytes()
    prepare(store.authorization_path, store.root)
    assert store.authorization_path.read_bytes() == first
    assert store.authorization_path.stat().st_mode & 0o777 == 0o600
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.summary()['admission_reason'] == 'activation_required'
    with pytest.raises(AdmissionError, match='invalid_judge_authorization'):
        JudgeStore(tmp_path / 'different', store.authorization_path)


def test_changed_authorization_and_missing_database_stop_resets(tmp_path):
    store, _ = make_store(tmp_path)
    data = store.authorization_path.read_bytes()
    store.authorization_path.write_bytes(data + b'\n')
    with pytest.raises(AdmissionError, match='judge_authorization_changed'):
        store.summary()
    store.authorization_path.write_bytes(data)
    store.path.unlink()
    with pytest.raises(AdmissionError, match='judge_state_missing_preserve_allowance'):
        JudgeStore(store.root, store.authorization_path)


def test_capability_reservation_cannot_repeat_or_accept_bad_facts(tmp_path):
    store, _ = make_store(tmp_path, ready=False)
    store.reserve_capability()
    with pytest.raises(AdmissionError, match='already_reserved'):
        store.reserve_capability()
    with pytest.raises(ValueError):
        store.record_capability({'synthetic': True})
    store.record_capability(CAPABILITY)
    store.record_capability(CAPABILITY)
    assert store.capability() == CAPABILITY


def test_twenty_total_preserves_four_held_out_slots_and_once_only(tmp_path):
    store, _ = make_store(tmp_path)
    for _ in range(16):
        admit(store)
        complete(store)
    with pytest.raises(AdmissionError, match='attempt_limit_reached'):
        admit(store)
    first = held_out(store)
    again = held_out(store)
    assert first == again
    assert len({job['id'] for job in first['jobs']}) == 4
    for _ in range(4):
        complete(store)
    assert store.summary()['attempts_used'] == 20
    assert store.summary()['attempts_remaining'] == 0
    assert held_out(store) == {'status': 'held_out_queued_once', 'controller_sha256': first['controller_sha256'],
                              'jobs': [store.get(job['id']) for job in first['jobs']]}


def test_held_out_summary_keeps_failures_and_usage_without_new_runs(tmp_path):
    store, _ = make_store(tmp_path)
    assert held_out_report(store)['status'] == 'incomplete'
    held_out(store)
    for _ in range(4):
        job = store.claim()
        path = store.root / 'jobs' / job['id'] / 'outcome.json'
        path.parent.mkdir(parents=True)
        verified = job['strategy'] == 'agent'
        # This is manufactured metadata for the offline summary test.
        path.write_text(json.dumps({'evidence': 'live_inference', 'verified': verified,
                                    'outcome': 'behavior_verified' if verified else 'no_accepted_proposal'}))
        store.finish(job['id'], job['worker_token'], result={'outcome': 'test'})
    report = held_out_report(store)
    assert report['status'] == 'completed'
    assert report['summary']['agent']['verified_cases'] == 2
    assert report['summary']['one_shot']['verified_cases'] == 0
    assert store.summary()['attempts_used'] == 4


def test_concurrent_request_replays_and_claims_are_single(tmp_path):
    store, _ = make_store(tmp_path)
    request = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: store.admit(request), range(8)))
    assert len({job['id'] for job in jobs}) == 1
    assert store.summary()['attempts_used'] == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(4)))
    assert sum(job is not None for job in claims) == 1


@pytest.mark.parametrize('kind,limit', [('model', 8), ('sandbox', 17)])
def test_failed_and_uncertain_provider_attempts_stay_counted(tmp_path, kind, limit):
    store, _ = make_store(tmp_path)
    admitted = admit(store)
    job = store.claim()
    for ordinal in range(1, limit + 1):
        assert store.reserve(job['id'], job['worker_token'], kind) == ordinal
    with pytest.raises(AdmissionError, match=kind + '_attempt_limit'):
        store.reserve(job['id'], job['worker_token'], kind)
    with pytest.raises(AdmissionError, match='worker_claim_lost'):
        store.reserve(job['id'], 'wrong', kind)
    store.interrupt_abandoned()
    assert store.get(admitted['id'])['status'] == 'interrupted'
    assert store.summary()['attempts_used'] == 1
    assert store.claim() is None


def test_queue_and_expiry_do_not_erase_saved_results(tmp_path):
    store, clock = make_store(tmp_path)
    first = admit(store)
    admit(store)
    admit(store)
    with pytest.raises(AdmissionError, match='queue_full'):
        admit(store)
    job = store.claim()
    public = store.root / 'jobs' / job['id'] / 'public'
    public.mkdir(parents=True)
    (public / 'review.html').write_text('saved')
    store.finish(job['id'], job['worker_token'], result={'outcome': 'behavior_verified', 'has_artifacts': True})
    clock[0] = store.expires
    with pytest.raises(AdmissionError, match='judging_expired'):
        admit(store)
    assert store.get(first['id'])['has_artifacts'] is True
    assert store.job_artifact(job['id'], 'review.html').read_text() == 'saved'
    assert store.job_artifact(job['id'], '../../authorization.json') is None


@pytest.mark.parametrize('interrupted', [True, False])
def test_interruption_or_failure_pauses_other_jobs_until_reconciled(tmp_path, interrupted):
    store, _ = make_store(tmp_path)
    admit(store)
    admit(store)
    job = store.claim()
    if interrupted:
        store.interrupt_abandoned()
    else:
        store.finish(job['id'], job['worker_token'], error_code='manufactured_failure')
    assert store.summary()['admission_reason'] == 'admission_paused'
    assert store.claim() is None
    assert store.summary()['attempts_used'] == 2


def test_worker_models_reserve_before_calls_and_do_not_retry(tmp_path):
    store, _ = make_store(tmp_path)
    admit(store)
    job = store.claim()
    calls = []

    class Failing:
        live, model = True, 'manufactured'

        def complete(self, *args):
            calls.append(store.get(job['id'])['model_calls'])
            raise RuntimeError('manufactured failure')

    with pytest.raises(RuntimeError):
        BoundedModel(Failing(), store, job).complete([], None, 2048)
    assert calls == [1]
    with store.connection() as db:
        assert db.execute('SELECT state FROM judge_model_calls').fetchone()[0] == 'uncertain'


def test_worker_integration_keeps_key_out_of_status_and_counts_before_transport(tmp_path, monkeypatch):
    store, _ = make_store(tmp_path)
    admit(store)
    seen = []
    monkeypatch.setenv('NEBIUS_API_KEY', 'manufactured-private-key')

    class Client:
        live, model = True, 'manufactured'

        def complete(self, *args):
            seen.append(store.list_jobs()[0]['model_calls'])
            return {'choices': [{'message': {'content': 'manufactured'}}]}

    class Adapter:
        def __init__(self, key, state, fixture, reserve, *, capability):
            self.reserve = reserve
            assert key == 'manufactured-private-key' and capability == CAPABILITY

        def close(self):
            seen.append('closed')

    def evaluate(fixture, strategy, client, state, image, *, adapter):
        client.complete([], None, 2048)
        adapter.reserve()
        assert store.list_jobs()[0]['guest_operations'] == 1
        return {'outcome': 'no_accepted_proposal'}

    worker(store, once=True, job_runner=lambda s, j: run_job(s, j, client_factory=Client, adapter_factory=Adapter, evaluator=evaluate))
    status = store.list_jobs()[0]
    assert status['status'] == 'completed' and status['outcome'] == 'no_accepted_proposal'
    assert status['model_calls'] == status['guest_operations'] == 1
    assert 'manufactured-private-key' not in json.dumps(status)
    assert seen == [1, 'closed']


def test_whole_worker_engine_and_downloads_with_manufactured_provider_responses(tmp_path, monkeypatch):
    """Exercise the whole path; the oracle and guest outcomes are synthetic."""
    from docdrift.evidence import verify_evidence
    from docdrift.judge_live import JudgeExecutionAdapter
    from docdrift.repair import ScriptedModel
    from docdrift.sandbox_simulation import FixtureSandboxSimulation, IMAGE_ID as SIMULATED_IMAGE

    fixture = ROOT / 'fixtures/development/source_only'
    repair = (fixture / 'repair.py').read_text()  # Oracle fixture only, never a live model input.

    class Service(FixtureSandboxSimulation):
        def _observation(self, payload):
            return super()._observation({**payload, 'image': SIMULATED_IMAGE})

    simulated = Service(tmp_path / 'manufactured-service')
    simulated.register_profile(fixture / 'repository', fixture / 'profile.json', repair)
    response = {'choices': [{'message': {'content': None, 'tool_calls': [
        {'id': 'submit', 'type': 'function', 'function': {'name': 'submit_replacement',
         'arguments': json.dumps({'code': repair})}}]}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}
    store, _ = make_store(tmp_path)
    job = admit(store)
    monkeypatch.setenv('NEBIUS_API_KEY', 'manufactured-worker-key')

    def adapter(key, state, pinned, reserve, *, capability):
        return JudgeExecutionAdapter(key, state, pinned, reserve, capability=capability, transport=simulated.transport)

    worker(store, once=True, job_runner=lambda s, j: run_job(
        s, j, client_factory=lambda: ScriptedModel([response]), adapter_factory=adapter))
    result = store.get(job['id'])
    assert result['status'] == 'completed' and result['outcome'] == 'behavior_verified'
    assert result['model_calls'] == 1 and result['guest_operations'] == 13
    assert result['has_artifacts'] is True
    public = store.job_artifact(job['id'], 'evidence.zip')
    assert verify_evidence(public)['status'] == 'integrity_verified'
    with zipfile.ZipFile(public) as archive:
        report = json.loads(archive.read('report.json'))
        assert report['repair_source'] == 'synthetic_agent'
        assert all(b'manufactured-worker-key' not in archive.read(name) for name in archive.namelist())
    assert store.job_artifact(job['id'], 'review.html').is_file()


def archive_fixture(tmp_path, *, secret=None):
    state = tmp_path / 'attempt'
    run_id = uuid.uuid4().hex
    run = state / 'runs' / run_id
    run.mkdir(parents=True)
    source = ROOT / 'docs/demo/f6/agent/evidence.zip'
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if secret:
        name = next(name for name in files if name.endswith('.stdout.txt'))
        files[name] += secret.encode()
        manifest = {'algorithm': 'sha256', 'files': {n: hashlib.sha256(data).hexdigest() for n, data in files.items() if n != 'manifest.json'}}
        files['manifest.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(run / 'evidence.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return state, run_id


def test_export_sanitizes_and_keeps_held_out_label_and_integrity(tmp_path):
    from docdrift.evidence import verify_evidence
    state, run_id = archive_fixture(tmp_path)
    destination = state / 'public'
    publish_evidence(state, run_id, destination, purpose='held_out')
    result = verify_evidence(destination / 'evidence.zip')
    assert result['status'] == 'integrity_verified' and result['files_checked'] == 40
    assert result['execution_attested'] is False
    assert 'owned held-out fixture' in (destination / 'review.html').read_text()
    assert 'presentation.json' in zipfile.ZipFile(destination / 'evidence.zip').namelist()


def test_export_rejects_actual_key_even_if_pattern_is_unknown(tmp_path):
    secret = 'manufactured-opaque-value-with-no-known-key-prefix'
    state, run_id = archive_fixture(tmp_path, secret=secret)
    with pytest.raises(ValueError, match='credential_in_private_evidence'):
        publish_evidence(state, run_id, state / 'public', forbidden=(secret,))
    assert not (state / 'public').exists()
