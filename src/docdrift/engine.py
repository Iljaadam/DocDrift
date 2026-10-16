"""Manual vertical slice: deterministic phases and fresh local verification."""

from __future__ import annotations

import difflib
import fcntl
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .adapters import ExecutionRequest, LocalDockerAdapter
from .challenge import validate_protected_changes
from .execution import backend_name, is_simulated, perform_execution
from .markdown import extract_examples
from .policy import PolicyError, apply_replacement
from .profile import ProfileError, check_result, freeze_profile, load_profile
from .review import render_review
from .snapshot import file_hashes, resolve_local, sha256
from .store import StateStore


MAX_OPERATIONS = 24
MAX_RUN_SECONDS = 900


def failure_signature(record: dict) -> tuple | None:
    result = record['result']
    if (result.get('state') != 'completed' or result.get('timed_out') or result.get('observation_timed_out')
            or result.get('evidence_complete', True) is not True or result.get('signal') not in {None, 0}
            or result.get('service_state') not in {None, 'SUCCESS'} or type(result.get('exit_code')) is not int):
        return None
    if result.get('stdout_truncated') or result.get('stderr_truncated'):
        return None
    if result['exit_code'] != 0:
        lines = result.get('stderr', '').strip().splitlines()
        return ('process_exit', result['exit_code'], lines[-1] if lines else '')
    if not record['checks']['observable_passed']:
        return ('frozen_acceptance_check', tuple(record['checks']['observable_errors']))
    return None


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def inventory(snapshot: Path, documents: list[str]) -> list[dict]:
    found = []
    for document in documents:
        content = (snapshot / document).read_bytes()
        if len(content) > 256 * 1024:
            raise ProfileError(f'Document exceeds 256 KiB: {document}')
        for ordinal, example in enumerate(extract_examples(document, content)):
            item = asdict(example)
            item['ordinal'] = ordinal
            found.append(item)
    return found


def inspect_repository(repository: Path, ref: str, documents: list[str]) -> dict:
    from .snapshot import safe_path
    if not 1 <= len(documents) <= 5 or len(set(documents)) != len(documents):
        raise ProfileError('Select one to five unique Markdown files')
    for document in documents:
        if not safe_path(document).endswith('.md'):
            raise ProfileError('Select Markdown paths only')
    with tempfile.TemporaryDirectory(prefix='docdrift-inspect-') as root:
        snapshot = Path(root) / 'snapshot'
        provenance = resolve_local(repository, ref, snapshot)
        examples = inventory(snapshot, documents)
    return {'provenance': provenance, 'examples': examples, 'execution': 'not_run', 'behavior_verified': False}


def inspect_github(repository: str, ref: str, documents: list[str], *, client=None) -> dict:
    """Inspect a pinned public snapshot; never execute downloaded code."""
    from .github import resolve_public_github
    from .snapshot import safe_path
    if not 1 <= len(documents) <= 5 or len(set(documents)) != len(documents):
        raise ProfileError('Select one to five unique Markdown files')
    for document in documents:
        if not safe_path(document).endswith('.md'):
            raise ProfileError('Select Markdown paths only')
    with tempfile.TemporaryDirectory(prefix='docdrift-public-inspect-') as temporary:
        snapshot = Path(temporary) / 'snapshot'
        provenance = resolve_public_github(repository, ref, snapshot, client=client)
        examples = inventory(snapshot, documents)
    return {'provenance': provenance, 'examples': examples, 'execution': 'not_run', 'behavior_verified': False}


def start_run(repository: Path, ref: str, profile_path: Path, replacement_path: Path, state_root: Path, image: str, adapter=None, *, repair_record: dict | None = None) -> dict:
    """Verify a replacement. ``repair_record`` is a model outcome from ``docdrift.repair``; without it the replacement is a supplied manual patch."""
    repository = repository.resolve(strict=True)
    profile_path = profile_path.resolve(strict=True)
    if profile_path.is_relative_to(repository):
        raise ProfileError('The frozen profile must live outside the target repository')
    profile, profile_files = load_profile(profile_path)
    check_source = (profile_path.parent / profile['checks']).resolve(strict=True)
    if check_source.is_relative_to(repository):
        raise ProfileError('Acceptance checks must live outside the target repository')
    replacement = replacement_path.read_bytes()
    if len(replacement) > 256 * 1024:
        raise PolicyError('Replacement is too large')
    replacement.decode('utf-8')
    store = StateStore(state_root)
    run_id = uuid.uuid4().hex
    run_dir = store.root / 'runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    provenance = resolve_local(repository, ref, run_dir / 'original')
    profile_hashes = freeze_profile(profile_files, run_dir / 'profile')
    (run_dir / 'replacement.py').write_bytes(replacement)
    metadata = {'provenance': provenance, 'profile_hashes': profile_hashes, 'replacement_sha256': sha256(replacement), 'image': image, 'adapter': backend_name(adapter), 'synthetic_execution': is_simulated(adapter), 'execution_contract': getattr(adapter, 'execution_contract', None), 'repair_source': 'supplied_manual_patch', 'paid_calls_enabled': False}
    if repair_record is not None:
        if repair_record.get('replacement') != replacement.decode('utf-8'):
            raise PolicyError('The repair record does not match the replacement being verified')
        record = json.dumps(repair_record, indent=2, ensure_ascii=False).encode()
        (run_dir / 'repair.json').write_bytes(record)
        live = bool(repair_record.get('live_inference'))
        metadata.update({'repair_source': f"model_{repair_record['strategy']}" if live else f"synthetic_{repair_record['strategy']}", 'repair_record_sha256': sha256(record), 'model': repair_record.get('model'), 'inference_usage': repair_record['usage'], 'paid_calls_enabled': live})
    store.create_run(run_id, metadata)
    store.event(run_id, 'frozen', {'run_directory': str(run_dir), 'profile_hashes': profile_hashes})
    return resume_run(run_id, state_root, adapter=adapter)


def resume_run(run_id: str, state_root: Path, adapter=None) -> dict:
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise ValueError('Expected a saved 32-character run ID')
    state_root = state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    with (state_root / 'engine.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another DocDrift run holds this state directory') from exc
        try:
            return _resume_run(run_id, state_root, adapter)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _resume_run(run_id: str, state_root: Path, adapter=None) -> dict:
    store = StateStore(state_root)
    saved = store.run(run_id)
    root = store.root / 'runs' / run_id
    metadata = saved['metadata']
    if file_hashes(root / 'original') != metadata['provenance']['files']:
        raise PolicyError('The pinned original snapshot changed')
    if file_hashes(root / 'profile') != metadata['profile_hashes']:
        raise PolicyError('Frozen profile or checks changed')
    if sha256((root / 'replacement.py').read_bytes()) != metadata['replacement_sha256']:
        raise PolicyError('Saved replacement changed')
    if 'repair_record_sha256' in metadata and sha256((root / 'repair.json').read_bytes()) != metadata['repair_record_sha256']:
        raise PolicyError('Saved repair record changed')
    profile, _ = load_profile(root / 'profile' / 'profile.json')
    report_path = root / 'report.json'
    if 'finished' in saved['phases'] and report_path.is_file():
        return json.loads(report_path.read_text())
    adapter = adapter or LocalDockerAdapter(store.root / 'docker-operations')
    if backend_name(adapter) != metadata['adapter']:
        raise ValueError('Resume requires the same execution backend as the saved run')
    synthetic = is_simulated(adapter)
    if synthetic != metadata.get('synthetic_execution', False):
        raise ValueError('Saved execution evidence type does not match the adapter')
    deadline = datetime.fromisoformat(saved['created_at']).timestamp() + MAX_RUN_SECONDS
    report = {'schema_version': 1, 'run_id': run_id, 'status': 'incomplete', 'diagnosis': 'inconclusive', 'repair_verdict': 'unattempted', 'adapter': metadata['adapter'], 'synthetic_execution': synthetic, 'execution_evidence': 'synthetic_not_execution' if synthetic else 'recorded_execution', 'repair_source': metadata['repair_source'], 'provider_qualification': 'unconfirmed', 'provenance': metadata['provenance'], 'frozen_profile_hashes': metadata['profile_hashes'], 'examples': [], 'results': [], 'usage': {'inference_calls': metadata.get('inference_usage', {}).get('model_calls', 0), 'paid_calls': metadata.get('inference_usage', {}).get('model_calls', 0) if metadata.get('paid_calls_enabled') else 0, 'compute_operations': 0}, 'coverage_note': 'Only the frozen JSON outputs across declared inputs, the required API call, and that call result reaching the printed output (static must-flow check) are checked. This owned-fixture result alone does not establish competition eligibility.'}
    if synthetic:
        report['coverage_note'] = 'Synthetic Sandbox responses exercise controller contracts only. No guest code executed and no provider access, network isolation, Python capability, or behavioral repair is established.'
        report.update(live_requests=0, code_executions=0)
    write_json(report_path, report)

    def finish(status: str) -> dict:
        report['status'] = status
        operation_count = len(store.operations(run_id))
        report['usage']['compute_operations'] = 0 if synthetic else operation_count
        report['usage']['simulated_operations'] = operation_count if synthetic else 0
        report['protected_hashes_preserved'] = file_hashes(root / 'original') == metadata['provenance']['files'] and file_hashes(root / 'profile') == metadata['profile_hashes']
        if 'patched_file_hashes' in report:
            report['protected_hashes_preserved'] = report['protected_hashes_preserved'] and file_hashes(root / 'patched') == report['patched_file_hashes']
        if not report['protected_hashes_preserved']:
            report['status'] = 'incomplete'
            report['repair_verdict'] = 'execution_passed' if report['repair_verdict'] == 'behavior_verified' else report['repair_verdict']
            report['finding'] = 'Frozen or patched inputs changed during verification'
            for item in report['examples']:
                item['verified'] = False
        report['evidence_exported'] = True
        report['usage']['operation_count_scope'] = 'Simulated snippet receipts; no guest code execution' if synthetic else 'Snippet operations; excludes local Python-version preflight probes'
        if metadata['adapter'] == 'nebius_sandbox':
            report['usage']['operation_count_scope'] = 'Verifier snippet operations; image import and runtime capability probes are recorded separately'
        report['behavior_verified'] = not synthetic and report['repair_verdict'] == 'behavior_verified' and report['status'] == 'completed'
        write_json(report_path, report)
        try:
            export_evidence(run_id, state_root)
        except (ValueError, OSError) as exc:
            report['status'] = 'incomplete'
            report['evidence_exported'] = False
            report['repair_verdict'] = 'execution_passed' if report['repair_verdict'] == 'behavior_verified' else report['repair_verdict']
            report['finding'] = f'Evidence export is incomplete: {exc}'
            report['behavior_verified'] = False
            for item in report['examples']:
                item['verified'] = False
            write_json(report_path, report)
            for name in ['review.html', 'evidence.zip']:
                (root / name).unlink(missing_ok=True)
            store.event(run_id, 'evidence_incomplete', {'message': str(exc)})
        if report['status'] in {'completed', 'rejected'}:
            store.event(run_id, 'finished', {'status': report['status'], 'verdict': report['repair_verdict']})
        return report

    try:
        preflight = saved['phases'].get('prepared')
        if preflight is None:
            preflight = adapter.preflight(metadata['image'])
            store.event(run_id, 'prepared', preflight)
        report['environment'] = preflight
        image_id = preflight.get('image_id') or preflight.get('image')
        if not image_id:
            raise RuntimeError('Preflight did not provide an immutable image ID')
        examples = inventory(root / 'original', profile['documentation'])
        by_key = {(item['path'], item['ordinal']): item for item in examples}
        selected = []
        for spec in profile['examples']:
            item = by_key.get((spec['path'], spec['ordinal']))
            if item is None or item['status'] != 'candidate':
                raise ProfileError('A selected example is absent or unsupported')
            selected.append((spec, item))
        report['examples'] = examples
        for item in report['examples']:
            item['profiled'] = any(spec['path'] == item['path'] and spec['ordinal'] == item['ordinal'] for spec in profile['examples'])
            item['verified'] = False
        target_spec, target = next(pair for pair in selected if pair[0]['role'] == 'target')
        healthy = [pair for pair in selected if pair[0]['role'] == 'healthy']
        # Reserve every final check before executing baseline work.
        required_operations = 3 + len(target_spec['cases']) + 2 * sum(len(spec['cases']) for spec, _ in healthy)
        if required_operations > MAX_OPERATIONS:
            raise ProfileError('Profile exceeds the 24-operation budget including final verification')

        def execute(phase: str, spec: dict, example: dict, case: dict, snapshot: Path) -> dict:
            key = f"{phase}/{example['id']}/{case['id']}"
            operations = store.operations(run_id)
            existing = next((op for op in operations if op['phase'] == key), None)
            if existing and existing['result'] is not None:
                result = existing['result']
            else:
                if datetime.now(timezone.utc).timestamp() > deadline:
                    raise RuntimeError('Run time budget exhausted; verification is incomplete')
                if not existing and len(operations) >= MAX_OPERATIONS:
                    raise RuntimeError('Operation budget exhausted; verification is incomplete')
                request = ExecutionRequest(snapshot=snapshot, code=example['code'], environment=case['env'], image=image_id, timeout_seconds=30)
                result = perform_execution(adapter, store, run_id, key, request)
            if result.get('image_id') != image_id:
                raise RuntimeError('Execution result came from a different environment image')
            if result.get('synthetic') and not synthetic:
                raise RuntimeError('Synthetic observations cannot verify a recorded-execution run')
            checks = check_result(result, case, example['code'], spec['required_call'], spec['operation_ast_sha256'])
            record = {'phase': phase, 'example_id': example['id'], 'case_id': case['id'], 'result': result, 'checks': checks}
            report['results'].append(record)
            write_json(report_path, report)
            if result.get('observation_timed_out') or result.get('state') == 'pending':
                raise RuntimeError('Operation observation is incomplete; resume will reconcile its saved ID')
            return record

        initial_case = target_spec['cases'][0]
        original = execute('baseline_target', target_spec, target, initial_case, root / 'original')
        if original['checks']['observable_passed']:
            report['diagnosis'] = 'no_failure_found'
            return finish('completed')
        original_result = original['result']
        if failure_signature(original) is None:
            return finish('incomplete')
        confirmed = execute('confirm_original', target_spec, target, initial_case, root / 'original')
        if failure_signature(original) is None or failure_signature(confirmed) != failure_signature(original):
            return finish('incomplete')
        report['diagnosis'] = 'simulated_documentation_drift' if synthetic else 'documentation_drift'
        report['original_failure_kind'] = 'process_exit' if original_result['exit_code'] != 0 else 'frozen_acceptance_check'
        for spec, item in healthy:
            for case in spec['cases']:
                if not execute('healthy_baseline', spec, item, case, root / 'original')['checks']['behavior_passed']:
                    report['diagnosis'] = 'inconclusive'
                    report['finding'] = 'A declared healthy example failed baseline checks'
                    return finish('incomplete')
        patched = root / 'patched'
        if patched.exists():
            shutil.rmtree(patched)
        shutil.copytree(root / 'original', patched)
        path = target['path']
        original_bytes = (patched / path).read_bytes()
        changed = apply_replacement(path, original_bytes, target['id'], target['source_hash'], (root / 'replacement.py').read_text())
        (patched / path).write_bytes(changed)
        hashes = file_hashes(patched)
        validate_protected_changes(metadata['provenance']['files'], hashes, target_path=path, approved_target_hash=sha256(changed))
        repaired = next(item for item in inventory(patched, profile['documentation']) if item['id'] == target['id'])
        (root / 'original.py').write_text(target['code'])
        (root / 'repaired.py').write_text(repaired['code'])
        diff = ''.join(difflib.unified_diff(original_bytes.decode().splitlines(keepends=True), changed.decode().splitlines(keepends=True), fromfile=f'a/{path}', tofile=f'b/{path}'))
        (root / 'repair.patch').write_text(diff)
        report['patched_file_hashes'] = hashes
        rerun = execute('final_original', target_spec, target, initial_case, root / 'original')
        if failure_signature(rerun) != failure_signature(original):
            report['diagnosis'] = 'inconclusive'
            return finish('incomplete')
        final = [execute('final_repaired', target_spec, repaired, case, patched) for case in target_spec['cases']]
        regressions = [execute('healthy_regression', spec, item, case, patched) for spec, item in healthy for case in spec['cases']]
        checks_pass = all(record['checks']['behavior_passed'] for record in final + regressions)
        execution_pass = all(record['checks']['execution_passed'] for record in final + regressions)
        report['repair_verdict'] = ('synthetic_contract_passed' if checks_pass else 'synthetic_contract_failed') if synthetic else 'behavior_verified' if checks_pass else 'execution_passed' if execution_pass else 'rejected'
        if checks_pass and not synthetic:
            for item in report['examples']:
                item['verified'] = item['profiled'] and item['status'] == 'candidate'
        report['healthy_preservation'] = {'required_examples': len(healthy), 'required_cases': len(regressions), 'all_passed': all(record['checks']['behavior_passed'] for record in regressions)}
        return finish('completed')
    except PolicyError as exc:
        report['repair_verdict'] = 'rejected'
        report['finding'] = str(exc)
        return finish('rejected')
    except Exception as exc:
        report['finding'] = f'{type(exc).__name__}: {exc}'
        store.event(run_id, 'interrupted', {'error_type': type(exc).__name__, 'message': str(exc)})
        return finish('incomplete')


def export_evidence(run_id: str, state_root: Path) -> Path:
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise ValueError('Expected a saved 32-character run ID')
    store = StateStore(state_root)
    run = store.run(run_id)
    root = store.root / 'runs' / run_id
    review = root / 'review.html'
    temporary_review = root / 'review.html.tmp'
    archive = root / 'evidence.zip'
    temporary_archive = root / 'evidence.zip.tmp'
    manifest = root / 'manifest.json'
    temporary_manifest = root / 'manifest.json.tmp'
    exported = False
    try:
        write_json(root / 'ledger.json', run)
        commands = []
        logs = root / 'logs'
        logs.mkdir(exist_ok=True)
        contract = run['metadata'].get('execution_contract') or {'executable': 'python', 'arguments': ['-B', '/work/example.py'], 'network': 'none'}
        for operation in run['operations']:
            commands.append({**contract, 'operation_id': operation['operation_id'], 'phase': operation['phase'], 'timeout_seconds': 30})
            if operation['result']:
                for stream_name in ['stdout', 'stderr']:
                    (logs / f"{operation['operation_id']}.{stream_name}.txt").write_text(operation['result'][stream_name])
        write_json(root / 'commands.json', {'operations': commands})
        report = json.loads((root / 'report.json').read_text())
        temporary_review.write_text(render_review(report, root, archive_available=True), encoding='utf-8')
        members = ['report.json', 'review.html', 'ledger.json', 'commands.json', 'replacement.py', 'repair.json', 'original.py', 'repaired.py', 'repair.patch']
        members += [path.relative_to(root).as_posix() for directory in ['profile', 'original', 'logs'] for path in sorted((root / directory).rglob('*')) if path.is_file()]
        sources = {name: temporary_review if name == 'review.html' else root / name for name in members}
        sources = {name: path for name, path in sources.items() if path.is_file()}
        if sum(path.stat().st_size for path in sources.values()) > 20 * 1024 * 1024:
            raise ValueError('Evidence exceeds 20 MiB; archive export is incomplete')
        temporary_manifest.write_text(json.dumps({'algorithm': 'sha256', 'files': {name: sha256(path.read_bytes()) for name, path in sources.items()}}, indent=2) + '\n', encoding='utf-8')
        if temporary_manifest.stat().st_size + sum(path.stat().st_size for path in sources.values()) > 20 * 1024 * 1024:
            raise ValueError('Evidence including manifest exceeds 20 MiB; archive export is incomplete')
        with zipfile.ZipFile(temporary_archive, 'w', zipfile.ZIP_DEFLATED) as stream:
            for name, path in sources.items():
                stream.write(path, name)
            stream.write(temporary_manifest, 'manifest.json')
        temporary_archive.replace(archive)
        temporary_review.replace(review)
        temporary_manifest.replace(manifest)
        exported = True
    finally:
        for path in [temporary_review, temporary_archive, temporary_manifest]:
            path.unlink(missing_ok=True)
        if not exported:
            for path in [review, archive, manifest]:
                path.unlink(missing_ok=True)
    return archive
