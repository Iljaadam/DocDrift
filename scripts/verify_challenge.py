"""Run constructed bad patches through the real local verifier, without inference.

Invalid whole-document/file-edit payloads stop at the existing submission gates.
Representable code replacements also enter the production engine with Docker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from docdrift.adapters import LocalDockerAdapter
from docdrift.challenge import _fixture_files, _proposals, run_challenge
from docdrift.cli import default_fixture_path, demo_repository
from docdrift.engine import start_run
from docdrift.markdown import extract_examples
from docdrift.profile import load_profile


def run(state: Path, image: str) -> dict:
    fixture = default_fixture_path().resolve()
    static = run_challenge(fixture)
    if not static['all_expectations_met']:
        raise ValueError('Static challenge failed; no execution started')
    files = _fixture_files(fixture)
    profile, _ = load_profile(fixture / 'profile.json')
    target = profile['target']
    document = files['repository/' + target['path']]
    selected = extract_examples(target['path'], document)[target['ordinal']]
    proposals = _proposals(document, selected, files[profile['known_repair']].decode(), files)
    state = state.resolve()
    if state.exists():
        raise ValueError('Use a new challenge directory; existing evidence is never reset or retried')
    state.mkdir(parents=True, mode=0o700)
    (state / 'static.json').write_text(json.dumps(static, indent=2) + '\n')
    adapter = LocalDockerAdapter(state / 'docker-operations')
    environment = adapter.preflight(image)
    image_id = environment['image_id']
    repository = state / 'repository'
    demo_repository(fixture / 'repository', repository)
    rows = []
    report = {
        'schema_version': 1, 'kind': 'constructed_verifier_challenge',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'proposal_origin': 'deliberately_constructed', 'backend': 'local_docker',
        'image_id': image_id, 'fixture': 'owned-renamed-method',
        'fixture_hashes': static['frozen_file_hashes'],
        'controller_hashes': {name: hashlib.sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                              for name in ['src/docdrift/engine.py', 'src/docdrift/challenge.py',
                                           'src/docdrift/policy.py', 'src/docdrift/profile.py',
                                           'src/docdrift/adapters.py', 'scripts/verify_challenge.py']},
        'inference_calls': 0, 'nebius_operations': 0, 'hosted_attempts_used': 0,
        'cases': rows,
        'coverage_note': 'Nine invalid document, file-edit, or non-text payloads stop at submission gates. '
                         'Seven bad code replacements and one manual control enter the real Docker engine. '
                         'Rejected candidates are never forced past a gate. This is local execution, '
                         'not a new model evaluation or Nebius Sandbox challenge.',
    }
    for proposal, boundary in zip(proposals, static['cases'], strict=True):
        row = {'id': proposal['id'], 'control': bool(proposal.get('control')),
               'static_verdict': boundary['verdict'], 'static_gate': boundary['gate'],
               'engine_run': False, 'candidate_executed': False, 'compute_operations': 0,
               'behavior_verified': False, 'expectation_met': boundary['expectation_met']}
        representable = ('document' not in proposal and not proposal.get('changes')
                         and isinstance(proposal.get('replacement'), str))
        if representable:
            candidate = state / (proposal['id'] + '.py')
            candidate.write_text(proposal['replacement'])
            # Persist admission before starting; an interruption leaves the ledger intact.
            (state / 'current-case.json').write_text(json.dumps({'id': proposal['id']}) + '\n')
            result = start_run(repository, 'HEAD', fixture / 'profile.json', candidate,
                               state / 'runs-state', image_id, adapter)
            candidate_results = [r for r in result['results'] if r['phase'] == 'final_repaired']
            row.update(engine_run=True, run_id=result['run_id'], status=result['status'],
                       repair_verdict=result['repair_verdict'], diagnosis=result['diagnosis'],
                       finding=result.get('finding'), candidate_executed=bool(candidate_results),
                       compute_operations=result['usage']['compute_operations'],
                       behavior_verified=result['behavior_verified'],
                       protected_hashes_preserved=result['protected_hashes_preserved'],
                       healthy_preservation=result.get('healthy_preservation'),
                       candidate_checks=[{'case_id': r['case_id'], 'exit_code': r['result']['exit_code'],
                                          'observable_passed': r['checks']['observable_passed'],
                                          'behavior_passed': r['checks']['behavior_passed']}
                                         for r in candidate_results])
            complete = (result['status'] in {'completed', 'rejected'}
                        and result['diagnosis'] == 'documentation_drift'
                        and result['protected_hashes_preserved'])
            row['expectation_met'] = complete and result['behavior_verified'] == row['control']
        rows.append(row)
        (state / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'case': row['id'], 'engine_run': row['engine_run'],
                          'behavior_verified': row['behavior_verified'],
                          'expectation_met': row['expectation_met']}), flush=True)
        if not row['expectation_met']:
            raise ValueError('Challenge failed; preserved evidence in the challenge directory')
    bad = [r for r in rows if not r['control']]
    report['summary'] = {'bad_proposals': len(bad),
                         'bad_proposals_behavior_verified': sum(r['behavior_verified'] for r in bad),
                         'bad_replacements_run_through_engine': sum(r['engine_run'] for r in bad),
                         'invalid_payloads_rejected_at_boundary': sum(not r['engine_run'] for r in bad),
                         'manual_control_behavior_verified': rows[-1]['behavior_verified'],
                         'compute_operations': sum(r['compute_operations'] for r in rows),
                         'all_expectations_met': all(r['expectation_met'] for r in rows)}
    (state / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Execute the owned fixture in local Docker')
    parser.add_argument('--image', default='python:3.12-slim', help='An already installed Python 3.12 image')
    parser.add_argument('--state-dir', type=Path, required=True, help='A new private evidence directory')
    parser.add_argument('--output', type=Path, help='Optional public summary; contains no controller paths')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required; no inference or cloud execution is supported')
    if args.output is not None and args.output.exists():
        parser.error('Output already exists; preserve the previous report')
    result = run(args.state_dir, args.image)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['summary'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
