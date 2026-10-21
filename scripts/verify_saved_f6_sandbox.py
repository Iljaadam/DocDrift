"""Prepare, then verify the saved F6 repair on a bounded Nebius Sandbox run.

``prepare`` is offline and needs only the committed demo bundle. ``run`` also
requires an explicit credit-coverage record and NEBIUS_API_KEY in the environment.
Neither command performs inference or evaluates held-out examples.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import UUID

from docdrift.engine import resume_run
from docdrift.evidence import verify_evidence
from docdrift.nebius import RemoteAdapterError
from docdrift.sandbox_plan import initialize_f6_run, prepare_f6_plan, validate_f6_plan


ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'aiproject-e00a0rb50jb0emajfv'
# Public Docker Hub metadata read on October 16, 2026. Pin the Linux amd64
# manifest rather than this aarch64 host's local Docker image or a mutable tag.
REGISTRY_IMAGE = (
    'docker://docker.io/library/python@sha256:'
    '2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe'
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def remote_error_ids(error: RemoteAdapterError) -> dict[str, str]:
    """Retain known receipt identities without logging arbitrary error data."""
    result = {}
    for name in ('operation_id', 'attempt_id'):
        value = getattr(error, name, None)
        if not isinstance(value, str):
            continue
        try:
            parsed = UUID(value)
        except ValueError:
            continue
        if str(parsed) == value and parsed.int != 0:
            result[name] = value
    return result


def preparation(args) -> dict:
    plan = prepare_f6_plan(
        args.plan_root, evidence_path=ROOT / 'docs/demo/f6/agent/evidence.zip',
        proposal_path=ROOT / 'docs/demo/f6/proposals/agent.json',
    )
    return {
        'status': 'prepared_offline',
        'plan_path': str(args.plan_root / 'plan.json'),
        'source_run_id': plan['source_run_id'],
        'verifier_operation_limit': plan['max_verifier_operations'],
        'runtime_probe_limit': 3,
        'private_image_import_limit': 1,
        'registry_image': args.registry_image,
        'current_inference_calls': 0,
        'provider_requests': 0,
        'credit_coverage': 'A separate factual confirmation is required before run.',
    }


def verification(args) -> dict:
    # Keep the ordinary CLI and Sandbox contract adapter unchanged. Import the
    # fixed-scope activation only when that separate operation is requested.
    from docdrift.sandbox_live import ARTIFACT_BYTES, F6ExecutionAdapter, F6SandboxRemote

    plan = validate_f6_plan(args.plan_root)
    if not args.coverage.is_file():
        raise ValueError(
            'Sandbox credit coverage is unconfirmed. Supply the factual coverage '
            'record described in docs/SANDBOX_VERIFICATION.md; no provider request was made.'
        )
    key = os.environ.get('NEBIUS_API_KEY')
    if not key:
        raise ValueError('NEBIUS_API_KEY is required in the environment; no credentials are read automatically.')
    report_path = args.state_root / 'runtime-report.json'
    report = {
        'kind': 'saved_f6_sandbox_verification',
        'status': 'incomplete',
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_run_id': plan['source_run_id'],
        'source_evidence_sha256': plan['source_evidence_sha256'],
        'source_proposal_sha256': plan['source_proposal_sha256'],
        'current_inference_calls': 0,
        'held_out_evaluation': False,
        'execution_backend': 'nebius_sandbox',
        'registry_image': args.registry_image,
        'coverage_record': str(args.coverage),
        'limits': {'image_imports': 1, 'runtime_probes': 3, 'verifier_operations': 12},
        'probes': {},
    }
    with F6SandboxRemote(
        api_key=key, project_id=args.project, plan_root=args.plan_root,
        state_root=args.state_root, registry_image=args.registry_image,
        coverage_path=args.coverage,
    ) as remote:
        write_json(report_path, report)
        failure = None
        try:
            image = remote.import_image()
            remote.bind_image(image)
            report['image_id'] = image
            write_json(report_path, report)

            for name in ('capability', 'artifact'):
                result = remote.run_probe(name)
                report['probes'][name] = asdict(result)
                write_json(report_path, report)
                if not result.execution_passed:
                    raise ValueError(f'{name} probe is incomplete or failed; retain its saved operation ID.')
            artifact = remote.download_probe_artifact()
            report['artifact_bytes_match'] = artifact == ARTIFACT_BYTES
            write_json(report_path, report)
            if artifact != ARTIFACT_BYTES:
                raise ValueError('Downloaded retained artifact differs from the fixed probe bytes.')

            result = remote.run_probe('cancellation')
            report['probes']['cancellation_before_request'] = asdict(result)
            write_json(report_path, report)
            result = remote.cancel_probe()
            report['probes']['cancellation'] = asdict(result)
            write_json(report_path, report)
            if result.service_state != 'CANCELLED':
                raise ValueError('Cancellation did not reach CANCELLED; retain the recorded outcome.')

            adapter = F6ExecutionAdapter(remote)
            run_id = remote.run_id
            if run_id is None:
                run_id = initialize_f6_run(
                    args.plan_root, args.state_root, image,
                    adapter.execution_contract, backend_name=adapter.backend_name,
                )
                remote.bind_run(run_id)
            report['verification_run_id'] = run_id
            write_json(report_path, report)
            result = resume_run(run_id, args.state_root, adapter=adapter)
            report['verifier_status'] = result['status']
            report['repair_verdict'] = result['repair_verdict']
            report['verifier_operations'] = result['usage']['compute_operations']
            report['verifier_inference_calls'] = result['usage']['inference_calls']
            report['protected_hashes_preserved'] = result.get('protected_hashes_preserved')
            report['verification_report'] = str(args.state_root / 'runs' / run_id / 'report.json')
            if result.get('evidence_exported') is True:
                archive = args.state_root / 'runs' / run_id / 'evidence.zip'
                report['archive_integrity'] = verify_evidence(archive)
                report['review_path'] = str(archive.with_name('review.html'))
            if (result['status'] == 'completed' and result['repair_verdict'] == 'behavior_verified'
                    and report.get('protected_hashes_preserved') is True
                    and report['verifier_operations'] == 12
                    and report['verifier_inference_calls'] == 0
                    and 'archive_integrity' in report):
                report['status'] = 'completed'
        except (RemoteAdapterError, ValueError, OSError) as exc:
            failure = exc
            # Adapter errors contain machine codes, never request/header objects.
            report['error'] = exc.code if isinstance(exc, RemoteAdapterError) else str(exc)
            if isinstance(exc, RemoteAdapterError):
                report['error_context'] = remote_error_ids(exc)
            raise
        finally:
            try:
                try:
                    report['operation_attempts'] = remote.operation_counts
                except (ValueError, OSError):
                    report['operation_attempts_unavailable'] = True
                report['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
                write_json(report_path, report)
            except Exception:
                # A local reporting failure must not hide the original error's
                # accepted remote IDs; main still prints them for reconciliation.
                if failure is None:
                    raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run'))
    parser.add_argument('--plan-root', type=Path, default=ROOT / '.docdrift/sandbox-f6-plan')
    parser.add_argument('--state-root', type=Path, default=ROOT / '.docdrift/sandbox-f6')
    parser.add_argument('--coverage', type=Path, default=ROOT / '.docdrift/access/sandbox-coverage.json')
    parser.add_argument('--project', default=PROJECT)
    parser.add_argument('--registry-image', default=REGISTRY_IMAGE)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = preparation(args) if args.command == 'prepare' else verification(args)
    except (RemoteAdapterError, ValueError, OSError) as exc:
        message = exc.code if isinstance(exc, RemoteAdapterError) else str(exc)
        if isinstance(exc, RemoteAdapterError):
            identities = remote_error_ids(exc)
            if identities:
                message += ' ' + ' '.join(f'{name}={value}' for name, value in identities.items())
        print(message, file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in {'completed', 'prepared_offline'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
