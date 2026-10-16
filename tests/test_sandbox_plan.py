"""Offline preparation must bind a fresh run to the unchanged saved F6 bytes."""

import hashlib
import json
import socket
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

from docdrift.evidence import EvidenceError
from docdrift.sandbox_execution import GUEST_EXAMPLE, GUEST_REPOSITORY, GUEST_RUNNER, RUNNER_BYTES
from docdrift.sandbox_plan import (
    DEFAULT_EVIDENCE_PATH, DEFAULT_PROPOSAL_PATH, F6_EVIDENCE_SHA256, F6_PROPOSAL_SHA256,
    F6_RUN_ID, initialize_f6_run, prepare_f6_plan, validate_f6_plan,
)
from docdrift.snapshot import file_hashes
from docdrift.store import StateStore


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / DEFAULT_EVIDENCE_PATH
PROPOSAL = ROOT / DEFAULT_PROPOSAL_PATH
IMAGE = '11111111-1111-4111-8111-111111111111'
CONTRACT = {'synthetic': False, 'network': 'disabled_in_request', 'disposable': True}


def prepare(tmp_path):
    path = tmp_path / 'plan'
    return path, prepare_f6_plan(path, EVIDENCE, PROPOSAL)


def rewrite(path, content):
    path.chmod(0o600)
    path.write_bytes(content)


def test_preparation_freezes_original_bytes_without_network_processes_or_inference(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline preparation must not use sockets or subprocesses')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    original_hashes = (hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
                       hashlib.sha256(PROPOSAL.read_bytes()).hexdigest())
    root, plan = prepare(tmp_path)
    assert validate_f6_plan(root) == plan
    assert plan['source_evidence_sha256'] == F6_EVIDENCE_SHA256
    assert plan['source_proposal_sha256'] == F6_PROPOSAL_SHA256
    assert plan['current_inference_calls'] == 0
    assert all(value == 0 for value in plan['current_inference_usage'].values())
    assert plan['historical_generation']['usage']['model_calls'] == 5
    assert plan['historical_generation']['live_inference'] is True
    with zipfile.ZipFile(EVIDENCE) as archive:
        for name in plan['files']:
            expected = PROPOSAL.read_bytes() if name == 'proposal.json' else archive.read(
                'report.json' if name == 'saved-report.json' else name)
            assert (root / name).read_bytes() == expected
            assert stat.S_IMODE((root / name).stat().st_mode) == 0o444
    assert file_hashes(root / 'original') == plan['original_source_hashes']
    assert file_hashes(root / 'profile') == plan['profile_hashes']
    assert (hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
            hashlib.sha256(PROPOSAL.read_bytes()).hexdigest()) == original_hashes


def test_preparation_is_idempotent_for_valid_unchanged_plan(tmp_path):
    root, plan = prepare(tmp_path)
    before = file_hashes(root)
    assert prepare_f6_plan(root, EVIDENCE, PROPOSAL) == plan
    assert file_hashes(root) == before


def test_exact_verifier_phases_cover_pristine_original_and_healthy_regressions(tmp_path):
    _, plan = prepare(tmp_path)
    target = 'ex_67a84a7505e8ce0d2b61'
    healthy = 'ex_e491531653032a5fe83e'
    cases = ['empty', 'repeated', 'exact-strings']
    expected = [f'baseline_target/{target}/empty', f'confirm_original/{target}/empty']
    expected += [f'healthy_baseline/{healthy}/{case}' for case in cases]
    expected += [f'final_original/{target}/empty']
    expected += [f'final_repaired/{target}/{case}' for case in cases]
    expected += [f'healthy_regression/{healthy}/{case}' for case in cases]
    assert [phase['phase'] for phase in plan['phases']] == expected
    assert plan['max_verifier_operations'] == len(expected) == 12
    assert [phase['snapshot'] for phase in plan['phases']] == ['original'] * 6 + ['patched'] * 6
    uploads = {digest for phase in plan['phases'] for digest in phase['files'].values()}
    assert plan['allowed_upload_sha256'] == sorted(uploads)
    assert len(uploads) == 9
    baseline, repaired = plan['phases'][0], plan['phases'][6]
    readme = f'{GUEST_REPOSITORY}/README.md'
    assert baseline['files'][readme] == plan['original_source_hashes']['README.md']
    assert baseline['files'][readme] != repaired['files'][readme]
    assert baseline['files'][GUEST_EXAMPLE] == baseline['code_sha256']
    assert repaired['files'][GUEST_EXAMPLE] == repaired['code_sha256']
    for phase in plan['phases']:
        assert phase['files'][GUEST_RUNNER] == hashlib.sha256(RUNNER_BYTES).hexdigest()
        assert set(phase['environment']) == {'DOCDRIFT_INPUT'}
        assert phase['files'][f'{GUEST_REPOSITORY}/drift_demo/__init__.py'] == plan['original_source_hashes']['drift_demo/__init__.py']


def test_changed_published_proposal_is_rejected_before_output_creation(tmp_path):
    proposal = tmp_path / 'changed-proposal.json'
    proposal.write_bytes(PROPOSAL.read_bytes() + b'\n')
    output = tmp_path / 'plan'
    with pytest.raises(ValueError, match='pinned published bytes'):
        prepare_f6_plan(output, EVIDENCE, proposal)
    assert not output.exists()


def test_unsafe_archive_never_extracts_any_member(tmp_path):
    evidence = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(evidence, 'w') as archive:
        archive.writestr('../escaped.py', b'raise AssertionError("must never run")')
        archive.writestr('manifest.json', b'{}')
    with pytest.raises(EvidenceError, match='Unsafe'):
        prepare_f6_plan(tmp_path / 'plan', evidence, PROPOSAL)
    assert not (tmp_path / 'escaped.py').exists()
    assert not (tmp_path / 'plan').exists()


def test_changed_unsigned_archive_with_valid_manifest_is_still_not_approved_input(tmp_path):
    with zipfile.ZipFile(EVIDENCE) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if name != 'manifest.json'}
    files['original/drift_demo/__init__.py'] += b'\n'
    files['manifest.json'] = json.dumps({
        'algorithm': 'sha256',
        'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }).encode()
    evidence = tmp_path / 'changed.zip'
    with zipfile.ZipFile(evidence, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError, match='pinned published F6 archive'):
        prepare_f6_plan(tmp_path / 'plan', evidence, PROPOSAL)
    assert not (tmp_path / 'plan').exists()


def test_plan_output_cannot_traverse_a_symlink(tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        prepare_f6_plan(alias / 'plan', EVIDENCE, PROPOSAL)
    assert list(target.iterdir()) == []


@pytest.mark.parametrize('relative', [
    'original/drift_demo/__init__.py', 'profile/checks.py', 'replacement.py',
    'proposal.json', 'saved-report.json',
])
def test_frozen_input_tampering_blocks_initialization_even_with_updated_manifest(tmp_path, relative):
    root, plan = prepare(tmp_path)
    changed = (root / relative).read_bytes() + b'\n'
    rewrite(root / relative, changed)
    plan['files'][relative] = hashlib.sha256(changed).hexdigest()
    rewrite(root / 'plan.json', json.dumps(plan).encode())
    with pytest.raises(ValueError, match='pinned published bytes'):
        initialize_f6_run(root, tmp_path / 'state', IMAGE, CONTRACT)
    assert not (tmp_path / 'state').exists()


def test_scope_changes_cannot_expand_fixed_verification_or_uploads(tmp_path):
    root, plan = prepare(tmp_path)
    plan['phases'].append(dict(plan['phases'][0], phase='extra/operation'))
    plan['max_verifier_operations'] = 13
    plan['allowed_upload_sha256'].append('0' * 64)
    rewrite(root / 'plan.json', json.dumps(plan).encode())
    with pytest.raises(ValueError, match='scope or hashes changed'):
        validate_f6_plan(root)


@pytest.mark.parametrize('unsafe', ['symlink', 'extra', 'fifo'])
def test_frozen_inventory_rejects_nonregular_or_unlisted_content(tmp_path, unsafe):
    root, _ = prepare(tmp_path)
    if unsafe == 'symlink':
        (root / 'outside').symlink_to(PROPOSAL)
    elif unsafe == 'fifo':
        import os
        os.mkfifo(root / 'pipe')
    else:
        (root / 'extra.py').write_text('raise AssertionError("do not run")')
    with pytest.raises(ValueError):
        initialize_f6_run(root, tmp_path / 'state', IMAGE, CONTRACT)
    assert not (tmp_path / 'state').exists()


def test_initialize_fresh_run_preserves_saved_generation_but_records_zero_new_usage(tmp_path, monkeypatch):
    root, plan = prepare(tmp_path)
    frozen_hashes = file_hashes(root)
    def forbidden(*args, **kwargs):
        raise AssertionError('Run initialization must not execute anything')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    state = tmp_path / 'state'
    run_id = initialize_f6_run(root, state, IMAGE, CONTRACT)
    assert len(run_id) == 32 and run_id != F6_RUN_ID
    saved = StateStore(state).run(run_id)
    metadata = saved['metadata']
    run_root = state / 'runs' / run_id
    assert metadata['repair_source'] == 'saved_model_agent'
    assert metadata['inference_usage']['model_calls'] == 0
    assert metadata['paid_calls_enabled'] is False
    assert metadata['historical_generation'] == plan['historical_generation']
    assert metadata['synthetic_execution'] is False
    assert metadata['provenance']['kind'] == 'saved_f6_evidence'
    assert 'commit' not in metadata['provenance']
    assert metadata['provenance']['historical_provenance']['commit'] == '3d016ba0fd68bf0417cb29d434808a41d017c25b'
    assert saved['operations'] == [] and set(saved['phases']) == {'frozen'}
    assert file_hashes(run_root / 'original') == plan['original_source_hashes']
    assert file_hashes(run_root / 'profile') == plan['profile_hashes']
    assert (run_root / 'repair.json').read_bytes() == PROPOSAL.read_bytes()
    assert file_hashes(root) == frozen_hashes


@pytest.mark.parametrize('image,contract', [('python:3.12', CONTRACT), (IMAGE, {'synthetic': True})])
def test_invalid_environment_contract_never_creates_a_run(tmp_path, image, contract):
    root, _ = prepare(tmp_path)
    with pytest.raises(ValueError):
        initialize_f6_run(root, tmp_path / 'state', image, contract)
    assert not (tmp_path / 'state').exists()
