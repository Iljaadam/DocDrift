"""Offline deployment checks; no user manager, provider, or external secret used."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("docdrift_judge_setup", ROOT / "scripts/docdrift_judge_setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


@pytest.fixture
def prepared(tmp_path):
    config = tmp_path / "config"
    state = tmp_path / "state"
    setup.prepare(config, state, "https://judge.example.ts.net:8443")
    return config, state


def test_secret_is_private_and_not_printed(tmp_path, capsys):
    assert setup.main(["--prepare", "--config-dir", str(tmp_path / "config"),
                       "--state-root", str(tmp_path / "state"),
                       "--public-origin", "https://judge.example.ts.net:8443"]) == 0
    password = (tmp_path / "config/judge-password.txt").read_text().strip()
    captured = capsys.readouterr()
    assert password not in captured.out + captured.err
    assert json.loads(captured.out)["provider_requests"] == 0
    assert json.loads(captured.out)["services_started"] is False
    for name in ("judge.env", "judge-password.txt"):
        assert stat.S_IMODE((tmp_path / "config" / name).stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "state").stat().st_mode) == 0o700


def test_preparation_is_idempotent_and_refuses_origin_change(prepared):
    config, state = prepared
    before = {path.name: path.read_bytes() for path in config.iterdir()}
    setup.prepare(config, state, "https://judge.example.ts.net:8443")
    assert before == {path.name: path.read_bytes() for path in config.iterdir()}
    with pytest.raises(setup.SetupError, match="differs"):
        setup.prepare(config, state, "https://another.example.ts.net:8443")
    assert before == {path.name: path.read_bytes() for path in config.iterdir()}


@pytest.mark.parametrize("origin", ["http://example.test", "https://user:password@example.test",
                                    "https://example.test/path", "https://example.test?query=1",
                                    "https://example.test/#fragment", "https://example.test?",
                                    "https://example.test/#", "https://example.test:0",
                                    "https://example.test\n", "https://éxample.test"])
def test_invalid_origin_is_rejected_before_writing(tmp_path, origin):
    with pytest.raises(setup.SetupError):
        setup.prepare(tmp_path / "config", tmp_path / "state", origin)
    assert not (tmp_path / "config").exists()


def test_explicit_loopback_origin_is_allowed():
    assert setup.public_origin("http://127.0.0.1:8765") == "http://127.0.0.1:8765"


def test_secret_symlink_is_not_followed(prepared, tmp_path):
    config, state = prepared
    outside = tmp_path / "untouched"
    outside.write_text("unrelated secret")
    (config / "judge.env").unlink()
    (config / "judge.env").symlink_to(outside)
    with pytest.raises(setup.SetupError):
        setup.prepare(config, state, "https://judge.example.ts.net:8443")
    assert outside.read_text() == "unrelated secret"


def test_loose_secret_permissions_are_refused(prepared):
    config, state = prepared
    (config / "judge-password.txt").chmod(0o644)
    with pytest.raises(setup.SetupError, match="mode-600"):
        setup.prepare(config, state, "https://judge.example.ts.net:8443")


def test_environment_without_password_is_left_unchanged(prepared):
    config, state = prepared
    before = (config / "judge.env").read_bytes()
    (config / "judge-password.txt").unlink()
    with pytest.raises(setup.SetupError):
        setup.prepare(config, state, "https://judge.example.ts.net:8443")
    assert not (config / "judge-password.txt").exists()
    assert (config / "judge.env").read_bytes() == before


def test_units_keep_api_key_out_of_web_environment(prepared, tmp_path):
    config, state = prepared
    units = setup.render_units(ROOT, config, state, tmp_path / "authorization.json")
    web = units["docdrift-judge-web.service"].decode()
    worker = units["docdrift-judge-worker.service"].decode()
    assert '--host 127.0.0.1 --port 8765' in web
    assert ' --live' not in web and ' --live' in worker
    assert f'EnvironmentFile={config / "nebius.env"}' not in web
    assert f'EnvironmentFile={config / "nebius.env"}' in worker
    assert 'UnsetEnvironment=NEBIUS_API_KEY NEBIUS_PROJECT_ID' in web
    for unit in (web, worker):
        assert 'MemoryMax=384M' in unit and 'TasksMax=32' in unit
        assert f'ReadWritePaths="{state}"' in unit
        assert 'InaccessiblePaths=' in unit and 'nebius.env' in unit
        assert '8501' not in unit and '--port 443' not in unit and '--port 80\n' not in unit


def test_unit_argument_escapes_systemd_specifiers_and_spaces():
    assert setup._unit_argument('/tmp/a path/%test') == '"/tmp/a path/%%test"'
    with pytest.raises(setup.SetupError):
        setup._unit_argument('/tmp/path\nExecStart=bad')


def test_install_does_not_read_provider_key_or_start_services(prepared, tmp_path, monkeypatch):
    config, state = prepared
    key_path = config / "nebius.env"
    key_path.write_text("NEBIUS_API_KEY=synthetic-forbidden-to-read\n")
    key_path.chmod(0o600)
    auth = tmp_path / "authorization.json"
    auth.write_text("{}")
    original_read = setup._private_bytes

    def private_read(path):
        assert path != key_path
        return original_read(path)

    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(setup, "_private_bytes", private_read)
    monkeypatch.setattr(setup.subprocess, "run", run)
    units = tmp_path / "units"
    result = setup.install(ROOT, config, units, state, auth)
    setup.install(ROOT, config, units, state, auth)
    assert result["services_started"] is False
    assert calls == [["systemctl", "--user", "daemon-reload"]] * 2
    assert sorted(path.name for path in units.iterdir()) == sorted(result["units"])


def test_existing_unrelated_unit_is_preserved_before_any_unit_write(prepared, tmp_path, monkeypatch):
    config, state = prepared
    (config / "nebius.env").write_text("synthetic key")
    (config / "nebius.env").chmod(0o600)
    auth = tmp_path / "authorization.json"
    auth.write_text("{}")
    units = tmp_path / "units"
    units.mkdir(mode=0o700)
    existing = units / "docdrift-judge-worker.service"
    existing.write_text("existing service\n")
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: pytest.fail("Do not reload after refusal"))
    with pytest.raises(setup.SetupError, match="will not be overwritten"):
        setup.install(ROOT, config, units, state, auth)
    assert existing.read_text() == "existing service\n"
    assert not (units / "docdrift-judge-web.service").exists()


def test_install_refuses_python_under_temporary_storage(prepared, tmp_path, monkeypatch):
    import shutil

    config, state = prepared
    (config / "nebius.env").write_text("synthetic key")
    (config / "nebius.env").chmod(0o600)
    auth = tmp_path / "authorization.json"
    auth.write_text("{}")
    repo = tmp_path / "repo"
    (repo / ".venv/bin").mkdir(parents=True)
    shutil.copytree(ROOT / "deploy", repo / "deploy")
    interpreter = tmp_path / "python3.12"
    interpreter.write_text("synthetic temporary interpreter\n")
    (repo / ".venv/bin/python").symlink_to(interpreter)
    units = tmp_path / "units"
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: pytest.fail("Do not reload units"))
    with pytest.raises(setup.SetupError, match="persistent"):
        setup.install(repo, config, units, state, auth)
    assert not units.exists()


@pytest.mark.parametrize("config_name", ["config", "config with space%name"])
def test_user_units_parse_with_systemd_when_available(tmp_path, config_name):
    import shutil

    binary = shutil.which("systemd-analyze")
    if not binary:
        pytest.skip("systemd-analyze is not installed")
    config, state = tmp_path / config_name, tmp_path / "state"
    setup.prepare(config, state, "https://judge.example.ts.net:8443")
    paths = []
    for name, content in setup.render_units(ROOT, config, state, tmp_path / "authorization.json").items():
        path = tmp_path / name
        path.write_bytes(content)
        paths.append(str(path))
    checked = subprocess.run([binary, "--user", "verify", *paths], capture_output=True, text=True,
                             timeout=20, env={**os.environ, "SYSTEMD_LOG_LEVEL": "warning"})
    if "Failed to lookup RuntimeDirectory path" in checked.stderr or "Failed to connect to bus" in checked.stderr:
        pytest.skip("The restricted session cannot access the user manager")
    assert checked.returncode == 0, checked.stderr
    # systemd may return success while ignoring an invalid directive.
    assert not checked.stderr.strip(), checked.stderr
