"""Run the frozen evaluation inventory under comparable strategies.

Strategies share one baseline observation per case and the same final verifier:

- ``execution_only``: flags drift when the example process fails. No repair.
- ``one_shot``: frozen-check detection, then one model call without tools.
- ``agent``: frozen-check detection, then the bounded tool-using repair loop.

Held-out cases run only when explicitly included. Public reference candidates
remain ``pending_reproduction`` and are never scored. A run that uses a
non-live model client is labelled synthetic and is not evaluation evidence.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .adapters import ExecutionRequest
from .markdown import extract_examples
from .profile import ProfileError, check_result, load_profile
from .repair import STRATEGIES, RepairBudget, RepairContext, describe_failure
from .snapshot import resolve_local


ALL_STRATEGIES = ('execution_only', 'one_shot', 'agent')


def load_cases(index_path: Path, *, include_held_out: bool = False) -> list[dict]:
    index = json.loads(index_path.read_text())
    splits = {'development', 'reference'} | ({'held_out'} if include_held_out else set())
    return [case for case in index['cases'] if case['split'] in splits]


class _Executor:
    def __init__(self, adapter, image: str):
        self.adapter = adapter
        self.image_id = None
        self.image = image
        self.operations = 0

    def run(self, snapshot: Path, code: str, env: dict) -> dict:
        if self.image_id is None:
            preflight = self.adapter.preflight(self.image)
            self.image_id = preflight.get('image_id') or preflight.get('image')
        self.operations += 1
        result = asdict(self.adapter.execute(ExecutionRequest(snapshot=snapshot, code=code, environment=env, image=self.image_id, timeout_seconds=30), on_accepted=lambda _: None))
        if result.get('operation_id'):
            self.adapter.cancel(result['operation_id'])
            if hasattr(self.adapter, 'cleanup'):
                self.adapter.cleanup(result['operation_id'])
        return result


def _abstention(case: dict, root: Path) -> dict:
    if case['kind'] == 'setup_failure':
        try:
            load_profile(root / case['profile'])
        except ProfileError as exc:
            return {'outcome': 'abstained_setup', 'reason': str(exc), 'verified': False}
        return {'outcome': 'setup_profile_accepted', 'verified': False}
    document = case['example']['path']
    examples = extract_examples(document, (root / case['repository'] / document).read_bytes())
    example = examples[case['example']['ordinal']]
    if example.status != 'candidate':
        return {'outcome': 'abstained_unsupported', 'reason': example.reason, 'verified': False}
    return {'outcome': 'treated_as_supported', 'verified': False}


def _profiled_case(source: Path, profile_path: Path, selected: dict, strategies: list[str], executor: _Executor, *,
                   client, budget: RepairBudget, state_root: Path, image: str, prepare_repository) -> list[dict]:
    from .engine import start_run
    rows = []
    with tempfile.TemporaryDirectory(prefix='docdrift-eval-') as temporary:
        repository, snapshot = Path(temporary) / 'repository', Path(temporary) / 'snapshot'
        prepare_repository(source, repository)
        resolve_local(repository, 'HEAD', snapshot)
        profile, _ = load_profile(profile_path)
        path, ordinal = selected['path'], selected['ordinal']
        spec = next(item for item in profile['examples'] if item['path'] == path and item['ordinal'] == ordinal)
        example = extract_examples(path, (snapshot / path).read_bytes())[ordinal]
        first = spec['cases'][0]
        observed = executor.run(snapshot, example.code, first['env'])
        checks = check_result(observed, first, example.code, spec['required_call'], spec['operation_ast_sha256'])
        for name in strategies:
            row = {'strategy': name, 'scored': True}
            rows.append(row)
            if name == 'execution_only':
                row['detected'] = not checks['execution_passed']
                row['outcome'] = 'drift_reported' if row['detected'] else 'no_failure_found'
                continue
            row['detected'] = not checks['observable_passed']
            if not row['detected']:
                row['outcome'] = 'no_failure_found'
                continue
            if spec['role'] != 'target':
                row['outcome'] = 'drift_reported_without_repair_profile'
                continue
            runner = lambda code, env=first['env']: executor.run(snapshot, code, env)
            context = RepairContext(snapshot, path, example, describe_failure(observed, checks['observable_errors']), run_python=runner)
            proposal = STRATEGIES[name](context, client, budget)
            row.update({'repair_status': proposal['status'], 'usage': proposal['usage']})
            if proposal['status'] != 'proposed':
                row['outcome'] = 'no_accepted_proposal'
                continue
            replacement = Path(temporary) / f'{name}-replacement.py'
            replacement.write_text(proposal['replacement'])
            report = start_run(repository, 'HEAD', profile_path, replacement, state_root, image, executor.adapter, repair_record=proposal)
            row.update({'outcome': report['repair_verdict'], 'run_id': report['run_id'], 'run_status': report['status'],
                        'verified': report['repair_verdict'] == 'behavior_verified'})
            executor.operations += report['usage']['compute_operations']
    return rows


def evaluate_fixture(fixture: Path, strategy: str, client, state_root: Path, image: str,
                     budget: RepairBudget = RepairBudget(), *, adapter=None, prepare_repository=None) -> dict:
    """Detect and repair one owned fixture's profiled target with one model strategy."""
    from .adapters import LocalDockerAdapter
    from .cli import demo_repository
    from .store import StateStore
    profile_path = fixture / 'profile.json'
    profile, _ = load_profile(profile_path)
    adapter = adapter or LocalDockerAdapter(StateStore(state_root).root / 'docker-operations')
    executor = _Executor(adapter, image)
    [row] = _profiled_case(fixture / 'repository', profile_path, profile['target'], [strategy], executor, client=client, budget=budget,
                           state_root=state_root, image=image, prepare_repository=prepare_repository or demo_repository)
    row['evidence'] = 'live_inference' if getattr(client, 'live', False) else 'synthetic_not_evidence'
    row['compute_operations'] = executor.operations
    return row


def evaluate(index_path: Path, strategies: list[str], state_root: Path, *, adapter, image: str,
             client=None, budget: RepairBudget = RepairBudget(), include_held_out: bool = False,
             prepare_repository: Callable[[Path, Path], None] | None = None) -> dict:
    from .cli import demo_repository
    unknown = set(strategies) - set(ALL_STRATEGIES)
    if unknown or not strategies:
        raise ValueError(f'Unknown strategies: {sorted(unknown)}')
    if any(name in STRATEGIES for name in strategies) and client is None:
        raise ValueError('Model strategies need a model client')
    prepare_repository = prepare_repository or demo_repository
    root = index_path.resolve().parents[2]
    executor = _Executor(adapter, image)
    rows = []
    for case in load_cases(index_path, include_held_out=include_held_out):
        base = {'case': case['id'], 'kind': case['kind'], 'split': case['split'], 'label': case['label']}
        if case['split'] == 'reference':
            rows += [base | {'strategy': name, 'outcome': 'pending_reproduction', 'scored': False} for name in strategies]
            continue
        if case['profile'] is None or case['kind'] == 'setup_failure':
            result = _abstention(case, root)
            rows += [base | {'strategy': name, 'scored': True, 'detected': False} | result for name in strategies]
            continue
        results = _profiled_case(root / case['repository'], root / case['profile'], case['example'], strategies, executor,
                                 client=client, budget=budget, state_root=state_root, image=image, prepare_repository=prepare_repository)
        rows += [base | row for row in results]
    live = client is not None and bool(getattr(client, 'live', False))
    evidence = 'no_model' if client is None else 'live_inference' if live else 'synthetic_not_evidence'
    return {'kind': 'docdrift_evaluation', 'evidence': evidence, 'execution_backend': type(adapter).__name__,
            'model': getattr(client, 'model', None), 'strategies': strategies, 'include_held_out': include_held_out,
            'budget': asdict(budget), 'rows': rows, 'summary': summarize(rows, strategies),
            'compute_operations': executor.operations}


def summarize(rows: list[dict], strategies: list[str]) -> dict:
    summary = {}
    for name in strategies:
        scored = [row for row in rows if row['strategy'] == name and row.get('scored')]
        broken = [row for row in scored if row['kind'] == 'broken']
        healthy = [row for row in scored if row['kind'] == 'healthy']
        abstain = [row for row in scored if row['kind'] in {'unsupported', 'setup_failure'}]
        usage = [row['usage'] for row in scored if 'usage' in row]
        summary[name] = {
            'broken_cases': len(broken),
            'drift_detected': sum(row['detected'] for row in broken),
            'behavior_verified_repairs': sum(row.get('outcome') == 'behavior_verified' for row in broken),
            'healthy_cases': len(healthy),
            'false_drift_reports': sum(row['detected'] for row in healthy),
            'unsupported_or_setup_cases': len(abstain),
            'correct_abstentions': sum(row['outcome'].startswith('abstained') for row in abstain),
            'unsupported_incorrectly_verified': sum(bool(row.get('verified')) for row in abstain),
            'model_calls': sum(item['model_calls'] for item in usage),
            'prompt_tokens': sum(item['prompt_tokens'] for item in usage),
            'completion_tokens': sum(item['completion_tokens'] for item in usage),
            'agent_snippet_runs': sum(item['snippet_runs'] for item in usage),
        }
    return summary


def markdown_summary(report: dict) -> str:
    def ratio(part: int, whole: int) -> str:
        return f'{part}/{whole} ({100 * part / whole:.0f}%)' if whole else '0/0'
    lines = [f"Evidence: **{report['evidence']}** · model: `{report['model']}` · execution: {report['execution_backend']} · held-out included: {report['include_held_out']}", '',
             '| Strategy | Drift detected | Verified repairs | False drift reports | Correct abstentions | Model calls | Tokens |',
             '|---|---|---|---|---|---|---|']
    for name, item in report['summary'].items():
        lines.append(f"| {name} | {ratio(item['drift_detected'], item['broken_cases'])} | "
                     f"{'n/a' if name == 'execution_only' else ratio(item['behavior_verified_repairs'], item['broken_cases'])} | "
                     f"{ratio(item['false_drift_reports'], item['healthy_cases'])} | {ratio(item['correct_abstentions'], item['unsupported_or_setup_cases'])} | "
                     f"{item['model_calls']} | {item['prompt_tokens'] + item['completion_tokens']} |")
    return '\n'.join(lines) + '\n'
