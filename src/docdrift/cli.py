"""Foreground CLI. Provider execution remains disabled; public inspection is read-only."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .engine import export_evidence, inspect_github, inspect_repository, resume_run, start_run


def default_fixture_path() -> Path:
    package_root = Path(__file__).resolve().parent
    bundled = package_root / 'data' / 'renamed_method'
    if (bundled / 'manifest.json').is_file():
        return bundled
    return package_root.parents[1] / 'fixtures' / 'renamed_method'


def demo_repository(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME='DocDrift fixture', GIT_AUTHOR_EMAIL='fixture@docdrift.invalid', GIT_COMMITTER_NAME='DocDrift fixture', GIT_COMMITTER_EMAIL='fixture@docdrift.invalid', GIT_AUTHOR_DATE='2026-10-12T00:00:00Z', GIT_COMMITTER_DATE='2026-10-12T00:00:00Z')
    for args in (['init', '-q', '--initial-branch=main'], ['add', '.'], ['-c', 'core.hooksPath=/dev/null', 'commit', '-q', '-m', 'Frozen owned renamed-method fixture']):
        subprocess.run(['git', '-C', str(destination)] + args, env=env, check=True, capture_output=True)


def model_client(args):
    """Build a live client only on explicit request; otherwise a synthetic replay or nothing."""
    from .repair import ScriptedModel, TokenFactoryClient
    if args.live and args.replay:
        raise ValueError('Choose --live or --replay, not both')
    if args.live:
        if not args.model:
            raise ValueError('--live requires an explicit --model ID')
        return TokenFactoryClient(args.model, os.environ.get('NEBIUS_API_KEY', ''))
    if args.replay:
        return ScriptedModel(json.loads(args.replay.read_text()))
    return None


def add_model_arguments(command) -> None:
    command.add_argument('--model', help='Explicit Token Factory model ID (no default)')
    command.add_argument('--live', action='store_true', help='Send real inference requests; uses NEBIUS_API_KEY and may consume credits')
    command.add_argument('--replay', type=Path, help='Synthetic scripted responses (JSON list); not model evidence')
    command.add_argument('--max-model-calls', type=int, default=8)


def main() -> None:
    parser = argparse.ArgumentParser(description='Inspect pinned Markdown examples and verify a supplied local repair.')
    parser.add_argument('--state-dir', type=Path, default=Path('.docdrift'))
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Resolve a local Git commit and inventory examples without execution')
    inspect.add_argument('repository', type=Path)
    inspect.add_argument('--ref', default='HEAD')
    inspect.add_argument('--doc', action='append', default=None)
    github = commands.add_parser('inspect-github', help='Inventory a pinned public GitHub snapshot without execution')
    github.add_argument('repository', help='owner/name or a canonical HTTPS GitHub repository URL')
    github.add_argument('--ref', default='HEAD')
    github.add_argument('--doc', action='append', default=None)
    commands.add_parser('sandbox-contract-demo', help='Exercise synthetic Sandbox responses offline; no credentials or provider calls')
    challenge = commands.add_parser('challenge', help='Check deliberately constructed bad patches with static policy; no execution')
    challenge.add_argument('--fixture', type=Path, default=default_fixture_path())
    challenge.add_argument('--output', type=Path, default=None)
    run = commands.add_parser('run', help='Run a curator-profiled manual repair in fresh local Docker containers')
    run.add_argument('repository', type=Path)
    run.add_argument('--ref', default='HEAD')
    run.add_argument('--profile', type=Path, required=True)
    run.add_argument('--replacement', type=Path, required=True)
    run.add_argument('--image', default='python:3.12-slim')
    run.add_argument('--trusted-local', action='store_true', required=True, help='Acknowledge this is a curated, trusted local development input')
    demo = commands.add_parser('demo', help='Run the owned renamed-method fixture with its supplied repair')
    demo.add_argument('--fixture', type=Path, default=default_fixture_path())
    demo.add_argument('--image', default='python:3.12-slim')
    demo.add_argument('--inspect-only', action='store_true')
    repair = commands.add_parser('repair', help='Propose a model repair for one owned fixture, then verify it in local Docker')
    repair.add_argument('--fixture', type=Path, default=default_fixture_path())
    repair.add_argument('--strategy', choices=['one_shot', 'agent'], default='agent')
    repair.add_argument('--image', default='python:3.12-slim')
    add_model_arguments(repair)
    evaluate = commands.add_parser('evaluate', help='Score strategies over the frozen evaluation inventory with local Docker')
    evaluate.add_argument('--index', type=Path, default=Path(__file__).resolve().parents[2] / 'fixtures' / 'evaluation' / 'index.json')
    evaluate.add_argument('--strategies', default='execution_only', help='Comma-separated: execution_only,one_shot,agent')
    evaluate.add_argument('--include-held-out', action='store_true', help='Only for the final scored run')
    evaluate.add_argument('--image', default='python:3.12-slim')
    evaluate.add_argument('--output', type=Path, default=None)
    add_model_arguments(evaluate)
    resume = commands.add_parser('resume', help='Reconcile saved local operation IDs and continue frozen phases')
    resume.add_argument('run_id')
    export = commands.add_parser('export', help='Export a saved run and its checksum manifest')
    export.add_argument('run_id')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            result = inspect_repository(args.repository, args.ref, args.doc or ['README.md'])
        elif args.command == 'inspect-github':
            result = inspect_github(args.repository, args.ref, args.doc or ['README.md'])
        elif args.command == 'sandbox-contract-demo':
            from .contract_demo import run_contract_demo
            result = run_contract_demo(args.state_dir)
            result = {key: result[key] for key in ['run_id', 'mode', 'status', 'live_requests', 'code_executions', 'paid_calls', 'behavior_verified', 'checks', 'report_path']}
        elif args.command == 'challenge':
            from .challenge import run_challenge
            output = args.output or args.state_dir / 'challenges' / 'static-policy.json'
            report = run_challenge(args.fixture, output)
            result = {'kind': report['kind'], 'all_expectations_met': report['all_expectations_met'],
                'rejected_proposals': sum(case['verdict'] == 'rejected' for case in report['cases']),
                'static_controls_accepted': sum(case['verdict'] == 'accepted_static' for case in report['cases']),
                'execution_performed': False, 'behavior_verified': False, 'milestone_3_complete': False,
                'report_path': str(output.resolve())}
            if not report['all_expectations_met']:
                print(json.dumps(result, indent=2))
                raise SystemExit(1)
        elif args.command == 'run':
            result = start_run(args.repository, args.ref, args.profile, args.replacement, args.state_dir, args.image)
        elif args.command == 'demo':
            with tempfile.TemporaryDirectory(prefix='docdrift-owned-fixture-') as temporary:
                repository = Path(temporary) / 'repository'
                demo_repository(args.fixture / 'repository', repository)
                if args.inspect_only:
                    result = inspect_repository(repository, 'HEAD', ['README.md'])
                else:
                    result = start_run(repository, 'HEAD', args.fixture / 'profile.json', args.fixture / 'repair.py', args.state_dir, args.image)
        elif args.command == 'repair':
            from .evaluation import evaluate_fixture
            from .repair import RepairBudget
            client = model_client(args)
            if client is None:
                raise ValueError('repair needs --live (real inference) or --replay (synthetic)')
            result = evaluate_fixture(args.fixture, args.strategy, client, args.state_dir, args.image, RepairBudget(max_model_calls=args.max_model_calls))
        elif args.command == 'evaluate':
            from .adapters import LocalDockerAdapter
            from .evaluation import evaluate as run_evaluation, markdown_summary
            from .repair import RepairBudget
            from .store import StateStore
            strategies = [name.strip() for name in args.strategies.split(',') if name.strip()]
            store = StateStore(args.state_dir)
            report = run_evaluation(args.index, strategies, args.state_dir, adapter=LocalDockerAdapter(store.root / 'docker-operations'), image=args.image,
                                    client=model_client(args), budget=RepairBudget(max_model_calls=args.max_model_calls), include_held_out=args.include_held_out)
            output = args.output or args.state_dir / 'evaluations' / 'latest.json'
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
            output.with_suffix('.md').write_text(markdown_summary(report))
            result = {'evidence': report['evidence'], 'summary': report['summary'], 'report_path': str(output.resolve())}
        elif args.command == 'resume':
            result = resume_run(args.run_id, args.state_dir)
        else:
            result = {'archive': str(export_evidence(args.run_id, args.state_dir))}
        if args.command in {'run', 'resume'} or args.command == 'demo' and not args.inspect_only:
            result['evidence_archive'] = str(args.state_dir.resolve() / 'runs' / result['run_id'] / 'evidence.zip') if result.get('evidence_exported', True) else None
            print(json.dumps({key: result.get(key) for key in ['run_id', 'status', 'diagnosis', 'repair_verdict', 'finding', 'usage', 'evidence_archive']}, indent=2))
            if result['status'] in {'incomplete', 'rejected'} or result['repair_verdict'] == 'rejected':
                raise SystemExit(1)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(2, f'docdrift: {exc}\n')
