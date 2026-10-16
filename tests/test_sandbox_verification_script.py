"""The fixed saved-repair workflow must stop before unconfirmed provider use."""

import json
from pathlib import Path
import runpy
import socket
import subprocess
import sys

import httpx

from docdrift.sandbox_plan import validate_f6_plan


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(ROOT / 'scripts/verify_saved_f6_sandbox.py'))


def deny_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No provider request, guest execution, or subprocess is authorized here')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(httpx.Client, '__init__', forbidden)


def command(monkeypatch, tmp_path, name):
    monkeypatch.setattr(sys, 'argv', [
        'verify_saved_f6_sandbox.py', name,
        '--plan-root', str(tmp_path / 'plan'),
        '--state-root', str(tmp_path / 'state'),
        '--coverage', str(tmp_path / 'coverage.json'),
    ])
    return SCRIPT['main']()


def test_prepare_works_outside_checkout_with_network_and_processes_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'prepared_offline'
    assert result['provider_requests'] == result['current_inference_calls'] == 0
    assert result['verifier_operation_limit'] == 12
    assert result['runtime_probe_limit'] == 3
    assert result['private_image_import_limit'] == 1
    assert '@sha256:' in result['registry_image']
    assert len(validate_f6_plan(tmp_path / 'plan')['phases']) == 12
    assert not (tmp_path / 'state').exists()


def test_run_without_coverage_stops_before_key_lookup_client_or_state(tmp_path, monkeypatch, capsys):
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'run') == 2
    message = capsys.readouterr().err
    assert 'credit coverage is unconfirmed' in message
    assert 'no provider request was made' in message
    assert not (tmp_path / 'state').exists()


def test_unconfirmed_coverage_cannot_become_a_live_switch(tmp_path, monkeypatch, capsys):
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    (tmp_path / 'coverage.json').write_text(json.dumps({
        'kind': 'docdrift_sandbox_credit_coverage',
        'project_id': SCRIPT['PROJECT'], 'personal_spend_limit': 0,
        'execution': 'unknown', 'image_import': 'unknown', 'storage': 'unknown',
        'confirmation': 'Access works; coverage has not been established.',
        'confirmed_at_utc': '2026-10-16T00:00:00+00:00',
    }))
    (tmp_path / 'coverage.json').chmod(0o600)
    monkeypatch.setenv('NEBIUS_API_KEY', 'synthetic-not-a-real-provider-key')
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'run') == 2
    message = capsys.readouterr().err.lower()
    assert 'coverage' in message or 'covered' in message
    assert not (tmp_path / 'state').exists()


def test_changed_source_is_rejected_before_missing_coverage_or_provider(tmp_path, monkeypatch, capsys):
    assert command(monkeypatch, tmp_path, 'prepare') == 0
    capsys.readouterr()
    source = tmp_path / 'plan/original/drift_demo/__init__.py'
    source.chmod(0o600)
    source.write_bytes(source.read_bytes() + b'\n# changed after approval\n')
    deny_side_effects(monkeypatch)
    assert command(monkeypatch, tmp_path, 'run') == 2
    assert 'pinned published bytes' in capsys.readouterr().err
    assert not (tmp_path / 'state').exists()
