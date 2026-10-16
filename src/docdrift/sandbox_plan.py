"""Prepare a bounded re-verification of the saved F6 repair, entirely offline.

This module grants no provider access. Its allowlist is derived from the pinned
published evidence and proposal; neither saved verdicts nor archive integrity
are a fresh execution attestation.
"""

from __future__ import annotations

import io
import json
import os
import re
import stat
import uuid
import zipfile
from pathlib import Path

from .evidence import MAX_ARCHIVE_BYTES, verify_evidence
from .markdown import extract_examples
from .policy import apply_replacement
from .profile import strict_json
from .sandbox_execution import GUEST_EXAMPLE, GUEST_REPOSITORY, GUEST_RUNNER, RUNNER_BYTES, _image_uuid
from .snapshot import sha256
from .store import StateStore


F6_EVIDENCE_SHA256 = 'ac8bd589d9455a897563e4cac1afab27ebd219d2ccb98c933ebde6a6a185944b'
F6_PROPOSAL_SHA256 = 'bf2432df7af32780096e4591a6f331e3c0c5678203c1308dce3dbd026722e370'
F6_RUN_ID = '4fd82cb8be7a449e8815d5366665f4ac'
DEFAULT_EVIDENCE_PATH = Path('docs/demo/f6/agent/evidence.zip')
DEFAULT_PROPOSAL_PATH = Path('docs/demo/f6/proposals/agent.json')
_FILE_LIMIT = 256 * 1024
_SOURCE_HASHES = {
    'LICENSE': 'bc7417ddec752e01427a3870ed5a4de61bd2961c30d603470d16c9ed40403c30',
    'README.md': '2a8cbd301bd4cea315b91fc68a97cf796feb86908ed33a4ac834f2c1cf68e9f2',
    'drift_demo/__init__.py': 'f28dc9c30fe883195db44e8979f6d7b914a62ae30dee0071a8240692ce860ce8',
    'pyproject.toml': 'd48b46a439f062826b19dce8ee6dd41a1cffec9560597f172a3cb754f91fbc04',
}
_PROFILE_HASHES = {
    'checks.py': '47af70a0f9cdd12e92615cff3594db629c8a93f33858d7220dc9dba5ebb09462',
    'profile.json': '3ed2b6fe4fa05739f508e380407bb94ee7d5af8ea4a065ca21e32d66ef6979b2',
}
_FROZEN_HASHES = {
    **{f'original/{name}': digest for name, digest in _SOURCE_HASHES.items()},
    **{f'profile/{name}': digest for name, digest in _PROFILE_HASHES.items()},
    'replacement.py': '9e7931d832359dbbbdda763dd27a40f477533e97c0ab4469dcd2fb24cb5e2f66',
    'proposal.json': F6_PROPOSAL_SHA256,
    'saved-report.json': 'e11aba0dfdcf38e949a74af3958910657f23332985b9980a2f3296aa16eeb284',
}
_CURRENT_INFERENCE = {
    'model_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0,
    'snippet_runs': 0, 'malformed_responses': 0,
}


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _read_regular(path: Path, limit: int = _FILE_LIMIT) -> bytes:
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Frozen inputs must not traverse symlinks')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Frozen inputs must be regular files')
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Frozen input exceeds its size limit')
    return content


def _build_plan(files: dict[str, bytes]) -> dict:
    hashes = {name: sha256(content) for name, content in files.items()}
    if hashes != _FROZEN_HASHES:
        raise ValueError('Frozen F6 inputs do not match the pinned published bytes')
    report = strict_json(files['saved-report.json'])
    proposal = strict_json(files['proposal.json'])
    profile = strict_json(files['profile/profile.json'])
    if (report['run_id'] != F6_RUN_ID or report['provenance']['files'] != _SOURCE_HASHES
            or report['frozen_profile_hashes'] != _PROFILE_HASHES
            or proposal['replacement'].encode() != files['replacement.py']):
        raise ValueError('Saved F6 provenance or replacement is inconsistent')

    source = {name: files[f'original/{name}'] for name in _SOURCE_HASHES}
    examples = extract_examples('README.md', source['README.md'])
    target_spec, healthy_spec = profile['examples']
    target, healthy = examples[target_spec['ordinal']], examples[healthy_spec['ordinal']]
    patched = dict(source)
    patched['README.md'] = apply_replacement('README.md', source['README.md'], target.id,
                                            target.source_hash, files['replacement.py'].decode())
    repaired = extract_examples('README.md', patched['README.md'])[target_spec['ordinal']]
    phases = []

    def phase(name, example, case, snapshot):
        uploaded = {f'{GUEST_REPOSITORY}/{path}': sha256(content)
                    for path, content in (source if snapshot == 'original' else patched).items()}
        uploaded[GUEST_EXAMPLE] = sha256(example.code.encode())
        uploaded[GUEST_RUNNER] = sha256(RUNNER_BYTES)
        phases.append({
            'phase': f"{name}/{example.id}/{case['id']}", 'snapshot': snapshot,
            'example_id': example.id, 'case_id': case['id'],
            'code_sha256': sha256(example.code.encode()), 'environment': dict(case['env']),
            'files': dict(sorted(uploaded.items())),
        })

    first = target_spec['cases'][0]
    phase('baseline_target', target, first, 'original')
    phase('confirm_original', target, first, 'original')
    for case in healthy_spec['cases']:
        phase('healthy_baseline', healthy, case, 'original')
    phase('final_original', target, first, 'original')
    for case in target_spec['cases']:
        phase('final_repaired', repaired, case, 'patched')
    for case in healthy_spec['cases']:
        phase('healthy_regression', healthy, case, 'patched')
    if len(phases) != 12 or len({item['phase'] for item in phases}) != 12:
        raise ValueError('Saved F6 profile does not have the fixed 12-operation scope')
    return {
        'kind': 'saved_f6_sandbox_verification_plan', 'schema_version': 1,
        'source_evidence_sha256': F6_EVIDENCE_SHA256,
        'source_proposal_sha256': F6_PROPOSAL_SHA256, 'source_run_id': F6_RUN_ID,
        'files': dict(sorted(hashes.items())),
        'original_source_hashes': dict(_SOURCE_HASHES), 'profile_hashes': dict(_PROFILE_HASHES),
        'replacement_sha256': hashes['replacement.py'],
        'historical_generation': {
            'source_run_id': F6_RUN_ID, 'strategy': proposal['strategy'], 'model': proposal['model'],
            'live_inference': proposal['live_inference'], 'usage': proposal['usage'],
            'proposal_sha256': F6_PROPOSAL_SHA256,
            'note': 'Saved October 15 model generation; no new inference in this verification.',
        },
        'current_inference_calls': 0, 'current_inference_usage': dict(_CURRENT_INFERENCE),
        'max_verifier_operations': 12, 'phases': phases,
        'allowed_upload_sha256': sorted({digest for item in phases for digest in item['files'].values()}),
        'coverage_note': 'Offline preparation only. Saved evidence is unsigned; '
                         'no provider requests, guest execution, or fresh behavioral verdict.',
    }


def prepare_f6_plan(output: Path, evidence_path: Path = DEFAULT_EVIDENCE_PATH,
                    proposal_path: Path = DEFAULT_PROPOSAL_PATH) -> dict:
    """Freeze only the approved published inputs; do not extract arbitrary paths."""
    evidence = _read_regular(evidence_path, MAX_ARCHIVE_BYTES)
    integrity = verify_evidence(evidence_path)
    if (sha256(evidence) != F6_EVIDENCE_SHA256
            or integrity['archive_sha256'] != F6_EVIDENCE_SHA256):
        raise ValueError('Evidence is not the pinned published F6 archive')
    files = {'proposal.json': _read_regular(proposal_path)}
    with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
        for name in _FROZEN_HASHES:
            if name == 'proposal.json':
                continue
            member = 'report.json' if name == 'saved-report.json' else name
            info = archive.getinfo(member)
            if info.file_size > _FILE_LIMIT:
                raise ValueError('Selected F6 archive member exceeds its size limit')
            with archive.open(info) as stream:
                files[name] = stream.read(_FILE_LIMIT + 1)
    plan = _build_plan(files)
    output = Path(output)
    if any(path.is_symlink() for path in (output, *output.absolute().parents)):
        raise ValueError('F6 plan output must not traverse symlinks')
    if output.exists():
        if validate_f6_plan(output) != plan:
            raise ValueError('Existing F6 plan differs from its pinned inputs')
        return plan
    output.mkdir(parents=True, mode=0o700)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(content)
        path.chmod(0o444)
    (output / 'plan.json').write_bytes(_json_bytes(plan))
    (output / 'plan.json').chmod(0o444)
    return plan


def _load_plan(root: Path) -> tuple[dict, dict[str, bytes]]:
    root = Path(root)
    expected_names = set(_FROZEN_HASHES) | {'plan.json'}
    names = set()
    if root.is_symlink():
        raise ValueError('F6 plan cannot be a symlink')
    for directory, folders, filenames in os.walk(root, followlinks=False):
        for name in folders + filenames:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError('F6 plan contains a symlink')
            mode = path.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError('F6 plan contains a nonregular file')
            names.add(path.relative_to(root).as_posix())
    if names != expected_names:
        raise ValueError('F6 plan file inventory changed')
    files = {name: _read_regular(root / name) for name in _FROZEN_HASHES}
    expected = _build_plan(files)
    plan_bytes = _read_regular(root / 'plan.json')
    plan = strict_json(plan_bytes)
    if plan != expected or plan_bytes != _json_bytes(expected):
        raise ValueError('F6 plan scope or hashes changed')
    return plan, files


def validate_f6_plan(root: Path) -> dict:
    """Recheck fixed content and scope, including changes to the hash manifest."""
    return _load_plan(root)[0]


def initialize_f6_run(plan_root: Path, state_root: Path, image_uuid: str,
                      execution_contract: dict, backend_name: str = 'nebius_sandbox') -> str:
    """Create a fresh engine ledger from saved bytes, without running its phases."""
    image_uuid = _image_uuid(image_uuid)
    if not isinstance(backend_name, str) or re.fullmatch(r'[a-z][a-z0-9_]{0,63}', backend_name) is None:
        raise ValueError('Expected a bounded execution backend name')
    if not isinstance(execution_contract, dict) or execution_contract.get('synthetic') is True:
        raise ValueError('Saved F6 live verification requires a nonsynthetic execution contract')
    # Freeze the caller's public contract before creating any ledger state.
    execution_contract = strict_json(_json_bytes(execution_contract))
    plan, files = _load_plan(plan_root)
    saved_report = strict_json(files['saved-report.json'])
    run_id = uuid.uuid4().hex
    store = StateStore(state_root)
    run_root = store.root / 'runs' / run_id
    run_root.mkdir(parents=True, mode=0o700)
    for name in [*[f'original/{name}' for name in _SOURCE_HASHES],
                 *[f'profile/{name}' for name in _PROFILE_HASHES], 'replacement.py']:
        path = run_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[name])
    (run_root / 'repair.json').write_bytes(files['proposal.json'])
    metadata = {
        'provenance': {
            'kind': 'saved_f6_evidence', 'origin': str(DEFAULT_EVIDENCE_PATH),
            'archive_sha256': F6_EVIDENCE_SHA256, 'files': dict(_SOURCE_HASHES),
            'license_files': saved_report['provenance']['license_files'],
            'source_run_id': F6_RUN_ID, 'historical_provenance': saved_report['provenance'],
        },
        'profile_hashes': dict(_PROFILE_HASHES), 'replacement_sha256': plan['replacement_sha256'],
        'repair_record_sha256': F6_PROPOSAL_SHA256, 'image': image_uuid,
        'adapter': backend_name, 'synthetic_execution': False,
        'execution_contract': execution_contract, 'repair_source': 'saved_model_agent',
        'model': plan['historical_generation']['model'], 'paid_calls_enabled': False,
        'inference_usage': dict(_CURRENT_INFERENCE),
        'historical_generation': plan['historical_generation'],
        'sandbox_plan_sha256': sha256(_json_bytes(plan)),
    }
    store.create_run(run_id, metadata)
    store.event(run_id, 'frozen', {'profile_hashes': dict(_PROFILE_HASHES),
                                 'source_run_id': F6_RUN_ID, 'sandbox_plan_sha256': metadata['sandbox_plan_sha256']})
    return run_id
