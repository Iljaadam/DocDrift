"""Foreground CLI. Provider execution remains disabled; local inspection runs no repository code."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .engine import export_evidence, inspect_repository, resume_run, start_run


def demo_repository(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME='DocDrift fixture', GIT_AUTHOR_EMAIL='fixture@docdrift.invalid', GIT_COMMITTER_NAME='DocDrift fixture', GIT_COMMITTER_EMAIL='fixture@docdrift.invalid', GIT_AUTHOR_DATE='2026-10-12T00:00:00Z', GIT_COMMITTER_DATE='2026-10-12T00:00:00Z')
    for args in (['init', '-q', '--initial-branch=main'], ['add', '.'], ['-c', 'core.hooksPath=/dev/null', 'commit', '-q', '-m', 'Frozen owned renamed-method fixture']):
        subprocess.run(['git', '-C', str(destination)] + args, env=env, check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='Inspect pinned Markdown examples and verify a supplied local repair.')
    parser.add_argument('--state-dir', type=Path, default=Path('.docdrift'))
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Resolve a local Git commit and inventory examples without execution')
    inspect.add_argument('repository', type=Path)
    inspect.add_argument('--ref', default='HEAD')
    inspect.add_argument('--doc', action='append', default=None)
    run = commands.add_parser('run', help='Run a curator-profiled manual repair in fresh local Docker containers')
    run.add_argument('repository', type=Path)
    run.add_argument('--ref', default='HEAD')
    run.add_argument('--profile', type=Path, required=True)
    run.add_argument('--replacement', type=Path, required=True)
    run.add_argument('--image', default='python:3.12-slim')
    run.add_argument('--trusted-local', action='store_true', required=True, help='Acknowledge this is a curated, trusted local development input')
    demo = commands.add_parser('demo', help='Run the owned renamed-method fixture with its supplied repair')
    demo.add_argument('--fixture', type=Path, default=Path(__file__).resolve().parents[2] / 'fixtures' / 'renamed_method')
    demo.add_argument('--image', default='python:3.12-slim')
    demo.add_argument('--inspect-only', action='store_true')
    resume = commands.add_parser('resume', help='Reconcile saved local operation IDs and continue frozen phases')
    resume.add_argument('run_id')
    export = commands.add_parser('export', help='Export a saved run and its checksum manifest')
    export.add_argument('run_id')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            result = inspect_repository(args.repository, args.ref, args.doc or ['README.md'])
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
