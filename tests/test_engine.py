import json
from collections import Counter
from pathlib import Path

import pytest

from docdrift.adapters import ExecutionResult
from docdrift.cli import demo_repository
from docdrift.engine import export_evidence, resume_run, start_run
from docdrift.policy import PolicyError
from docdrift.snapshot import file_hashes
from docdrift.store import StateStore


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'renamed_method'
IMAGE_ID = 'sha256:' + 'a' * 64


class ContractAdapter:
    """In-memory contract double; never executes repository or proposal code."""

    def __init__(self, *, interrupt=False, final_failure=False, healthy_failure=False, flaky=False):
        self.requests = {}
        self.interrupt = interrupt
        self.final_failure = final_failure
        self.healthy_failure = healthy_failure
        self.flaky = flaky
        self.original_observations = 0
        self.observed = []

    def preflight(self, image):
        return {'image_id': IMAGE_ID, 'python_version': 'Python 3.12.0', 'network': 'none'}

    def execute(self, request, on_accepted):
        identifier = f'{len(self.requests) + 1:064x}'
        self.requests[identifier] = request
        on_accepted(identifier)
        if self.interrupt:
            self.interrupt = False
            raise RuntimeError('Simulated interruption after accepted operation persisted')
        return self.observe(identifier)

    def observe(self, identifier, timeout_seconds=30):
        self.observed.append(identifier)
        request = self.requests[identifier]
        original = '.tally(' in request.code
        healthy = '"distinct"' in request.code
        if original:
            self.original_observations += 1
            if not self.flaky or self.original_observations == 1:
                return ExecutionResult('completed', 1, '', "AttributeError: 'WordCounter' object has no attribute 'tally'\n", identifier, IMAGE_ID, 0.1)
        elif self.final_failure and not healthy:
            raise RuntimeError('Final verification interrupted; required cases were not run')
        values = json.loads(request.environment['DOCDRIFT_INPUT'])
        output = {'distinct': len(set(values)), 'total': len(values)} if healthy else dict(Counter(values))
        if self.healthy_failure and healthy:
            output = {'distinct': -1, 'total': -1}
        return ExecutionResult('completed', 0, json.dumps(output), '', identifier, IMAGE_ID, 0.1)

    def cancel(self, identifier):
        pass


def run_fixture(tmp_path, adapter, replacement=None):
    repository = tmp_path / 'repository'
    demo_repository(FIXTURE / 'repository', repository)
    state = tmp_path / 'state'
    report = start_run(repository, 'HEAD', FIXTURE / 'profile.json', replacement or FIXTURE / 'repair.py', state, IMAGE_ID, adapter)
    return report, state


def test_manual_slice_preserves_protected_inputs_and_all_healthy_cases(tmp_path):
    adapter = ContractAdapter()
    report, state = run_fixture(tmp_path, adapter)
    assert report['repair_verdict'] == 'behavior_verified'
    assert report['diagnosis'] == 'documentation_drift'
    assert {key: report['usage'][key] for key in ['inference_calls', 'paid_calls', 'compute_operations']} == {'inference_calls': 0, 'paid_calls': 0, 'compute_operations': 12}
    assert len(adapter.requests) == len(set(adapter.requests)) == 12
    assert report['healthy_preservation']['all_passed']
    root = state / 'runs' / report['run_id']
    original, patched = file_hashes(root / 'original'), file_hashes(root / 'patched')
    assert {name for name in original if original[name] != patched[name]} == {'README.md'}
    assert report['protected_hashes_preserved']
    assert all(item['verified'] for item in report['examples'])
    assert report['repair_source'] == 'supplied_manual_patch'


def test_resume_reconciles_recorded_id_without_resubmitting_baseline(tmp_path):
    adapter = ContractAdapter(interrupt=True)
    initial, state = run_fixture(tmp_path, adapter)
    assert initial['status'] == 'incomplete'
    first_id = next(iter(adapter.requests))
    resumed = resume_run(initial['run_id'], state, adapter)
    assert resumed['repair_verdict'] == 'behavior_verified'
    assert len(adapter.requests) == 12
    assert adapter.observed.count(first_id) == 1
    assert len(StateStore(state).operations(initial['run_id'])) == 12
    assert resume_run(initial['run_id'], state, adapter) == resumed


def test_interrupted_required_final_checks_never_verify_examples(tmp_path):
    report, _ = run_fixture(tmp_path, ContractAdapter(final_failure=True))
    assert report['status'] == 'incomplete'
    assert report['repair_verdict'] == 'unattempted'
    assert not any(item['verified'] for item in report['examples'])


def test_changed_original_failure_is_inconclusive(tmp_path):
    report, _ = run_fixture(tmp_path, ContractAdapter(flaky=True))
    assert report['status'] == 'incomplete'
    assert report['diagnosis'] == 'inconclusive'
    assert not any(item['verified'] for item in report['examples'])


def test_declared_healthy_failure_prevents_repair_claim(tmp_path):
    report, _ = run_fixture(tmp_path, ContractAdapter(healthy_failure=True))
    assert report['status'] == 'incomplete'
    assert report['diagnosis'] == 'inconclusive'
    assert report['repair_verdict'] == 'unattempted'


def test_bad_patch_is_rejected_before_final_candidate_execution(tmp_path):
    replacement = tmp_path / 'bad.py'
    replacement.write_text('print({})\n')
    adapter = ContractAdapter()
    report, _ = run_fixture(tmp_path, adapter, replacement)
    assert report['repair_verdict'] == 'rejected'
    assert len(adapter.requests) == 5
    assert not any(item['verified'] for item in report['examples'])


def test_modified_frozen_check_is_refused_before_resume(tmp_path):
    adapter = ContractAdapter(interrupt=True)
    report, state = run_fixture(tmp_path, adapter)
    (state / 'runs' / report['run_id'] / 'profile' / 'checks.py').write_text('tampered')
    with pytest.raises(PolicyError, match='Frozen profile'):
        resume_run(report['run_id'], state, adapter)
    assert len(adapter.requests) == 1


def test_deadline_prevents_operation_even_after_resume(tmp_path, monkeypatch):
    monkeypatch.setattr('docdrift.engine.MAX_RUN_SECONDS', -1)
    adapter = ContractAdapter()
    report, _ = run_fixture(tmp_path, adapter)
    assert report['status'] == 'incomplete'
    assert not adapter.requests
    assert 'budget exhausted' in report['finding']


def test_export_manifest_matches_every_member(tmp_path):
    import hashlib
    import zipfile
    report, state = run_fixture(tmp_path, ContractAdapter())
    archive = export_evidence(report['run_id'], state)
    with zipfile.ZipFile(archive) as stream:
        manifest = json.loads(stream.read('manifest.json'))
        assert set(stream.namelist()) == set(manifest['files']) | {'manifest.json'}
        assert all(hashlib.sha256(stream.read(name)).hexdigest() == digest for name, digest in manifest['files'].items())


def test_ast_policy_difference_alone_is_not_a_documentation_failure(tmp_path):
    class ObservableSuccess(ContractAdapter):
        def observe(self, identifier, timeout_seconds=30):
            request = self.requests[identifier]
            output = dict(Counter(json.loads(request.environment['DOCDRIFT_INPUT'])))
            return ExecutionResult('completed', 0, json.dumps(output), '', identifier, IMAGE_ID, 0.1)
    report, _ = run_fixture(tmp_path, ObservableSuccess())
    assert report['diagnosis'] == 'no_failure_found'
    assert report['repair_verdict'] == 'unattempted'


def test_mismatched_execution_environment_cannot_verify(tmp_path):
    class WrongImage(ContractAdapter):
        def observe(self, identifier, timeout_seconds=30):
            from dataclasses import replace
            return replace(super().observe(identifier, timeout_seconds), image_id='sha256:' + 'b' * 64)
    report, _ = run_fixture(tmp_path, WrongImage())
    assert report['status'] == 'incomplete'
    assert 'different environment image' in report['finding']
    assert report['repair_verdict'] == 'unattempted'


def test_unprofiled_and_unsupported_examples_never_enter_verified_count(tmp_path):
    repository = tmp_path / 'repository'
    demo_repository(FIXTURE / 'repository', repository)
    markdown = repository / 'README.md'
    markdown.write_text(markdown.read_text() + '\n```python\nprint("unprofiled")\n```\n\n```pycon\n>>> 1 + 1\n2\n```\n')
    import subprocess
    subprocess.run(['git', '-C', str(repository), 'add', 'README.md'], check=True)
    subprocess.run(['git', '-C', str(repository), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Additional inventory examples'], check=True)
    report = start_run(repository, 'HEAD', FIXTURE / 'profile.json', FIXTURE / 'repair.py', tmp_path / 'state', IMAGE_ID, ContractAdapter())
    assert report['repair_verdict'] == 'behavior_verified'
    assert len(report['examples']) == 4
    assert sum(item['verified'] for item in report['examples']) == 2
    assert not report['examples'][2]['profiled']
    assert not report['examples'][2]['verified']
    assert report['examples'][3]['status'] == 'unsupported'
    assert not report['examples'][3]['verified']


def test_export_failure_produces_incomplete_recoverable_run(tmp_path, monkeypatch):
    def failed_export(*args):
        raise ValueError('Evidence exceeds 20 MiB')
    monkeypatch.setattr('docdrift.engine.export_evidence', failed_export)
    report, state = run_fixture(tmp_path, ContractAdapter())
    assert report['status'] == 'incomplete'
    assert report['repair_verdict'] == 'execution_passed'
    assert not report['evidence_exported']
    assert not any(item['verified'] for item in report['examples'])
    assert 'finished' not in StateStore(state).run(report['run_id'])['phases']


def test_inputs_changed_during_execution_cannot_finish_verified(tmp_path):
    class TamperDuringExecution(ContractAdapter):
        def observe(self, identifier, timeout_seconds=30):
            request = self.requests[identifier]
            if request.snapshot.name == 'patched':
                checks = request.snapshot.parent / 'profile' / 'checks.py'
                checks.write_text(checks.read_text() + '\n# unexpected change\n')
            return super().observe(identifier, timeout_seconds)
    report, _ = run_fixture(tmp_path, TamperDuringExecution())
    assert report['status'] == 'incomplete'
    assert not report['protected_hashes_preserved']
    assert report['repair_verdict'] == 'execution_passed'
    assert not any(item['verified'] for item in report['examples'])
