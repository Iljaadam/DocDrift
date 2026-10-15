"""Check the installed wheel, frozen fixture, and offline smoke boundary."""

import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import runpy
import shutil
import tarfile
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = runpy.run_path(str(ROOT / "scripts" / "check_distribution.py"))
DistributionError = CHECKER["DistributionError"]
PREFIX = "docdrift/data/renamed_method/"
METADATA = "docdrift-0.1.0.dist-info/"


def artifact_files():
    fixture = ROOT / "fixtures" / "renamed_method"
    frozen = {str(path.relative_to(fixture)): path.read_bytes() for path in fixture.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    wheel = {PREFIX + name: data for name, data in frozen.items()}
    wheel.update({
        "docdrift/cli.py": (ROOT / "src/docdrift/cli.py").read_bytes(),
        METADATA + "METADATA": b"Metadata-Version: 2.4\nName: docdrift\nVersion: 0.1.0\nLicense-Expression: MIT\n",
        METADATA + "entry_points.txt": b"[console_scripts]\ndocdrift = docdrift.cli:main\n",
        METADATA + "licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
    })
    source = {"fixtures/renamed_method/" + name: data for name, data in frozen.items()}
    source.update({name: (ROOT / name).read_bytes() for name in (
        "pyproject.toml", "uv.lock", "README.md", "LICENSE", "src/docdrift/cli.py", "scripts/check_distribution.py",
    )})
    for path in (ROOT / "src/docdrift").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
            relative = path.relative_to(ROOT / "src").as_posix()
            wheel[relative] = path.read_bytes()
            source["src/" + relative] = path.read_bytes()
    return wheel, source


def write_artifacts(tmp_path, wheel, source):
    wheel = dict(wheel)
    record = io.StringIO()
    rows = csv.writer(record, lineterminator="\n")
    for name, data in sorted(wheel.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.writerow([name, "sha256=" + digest, str(len(data))])
    rows.writerow([METADATA + "RECORD", "", ""])
    wheel[METADATA + "RECORD"] = record.getvalue().encode()
    wheel_path = tmp_path / "docdrift-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for name, data in wheel.items():
            archive.writestr(name, data)
    source_path = tmp_path / "docdrift-0.1.0.tar.gz"
    with tarfile.open(source_path, "w:gz") as archive:
        for name, data in source.items():
            member = tarfile.TarInfo("docdrift-0.1.0/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return wheel_path, source_path


def test_artifact_checker_accepts_complete_frozen_distribution(tmp_path):
    wheel, source = artifact_files()
    result = CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)
    assert result["fixture_files"] == 9 and result["fixture_hashes_preserved"]
    assert len(result["wheel_sha256"]) == len(result["sdist_sha256"]) == 64


def test_missing_wheel_fixture_reproduces_original_installed_demo_bug(tmp_path):
    wheel, source = artifact_files()
    wheel = {name: data for name, data in wheel.items() if not name.startswith(PREFIX)}
    with pytest.raises(DistributionError, match="fixture is missing"):
        CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)


@pytest.mark.parametrize("mutation", ["profile", "check", "license", "extra", "manifest"])
def test_changed_or_unfrozen_fixture_payload_is_rejected(tmp_path, mutation):
    wheel, source = artifact_files()
    if mutation == "extra":
        wheel[PREFIX + "unexpected.py"] = b"print('extra')"
    elif mutation == "manifest":
        wheel[PREFIX + "manifest.json"] = b'{}'
    else:
        name = {"profile": "profile.json", "check": "checks.py", "license": "repository/LICENSE"}[mutation]
        wheel[PREFIX + name] += b"\nchanged"
    with pytest.raises(DistributionError, match="fixture|manifest"):
        CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)


def test_source_archive_cannot_omit_frozen_profile_or_dependency_lock(tmp_path):
    wheel, source = artifact_files()
    source.pop("uv.lock")
    with pytest.raises(DistributionError, match="uv.lock"):
        CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)


def test_missing_package_license_or_console_entrypoint_is_rejected(tmp_path):
    wheel, source = artifact_files()
    wheel.pop(METADATA + "licenses/LICENSE")
    with pytest.raises(DistributionError, match="project license"):
        CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)
    wheel, source = artifact_files()
    wheel[METADATA + "entry_points.txt"] = b"[console_scripts]\n"
    with pytest.raises(DistributionError, match="entry point"):
        CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)


def test_wheel_and_source_module_disagreement_is_rejected(tmp_path):
    wheel, source = artifact_files()
    wheel["docdrift/cli.py"] += b"\n# wheel-only change\n"
    with pytest.raises(DistributionError, match="differs"):
        CHECKER["check_artifacts"](*write_artifacts(tmp_path, wheel, source), ROOT)


def test_record_does_not_allow_tampered_files(tmp_path):
    wheel, source = artifact_files()
    wheel_path, _ = write_artifacts(tmp_path, wheel, source)
    files = CHECKER["archive_files"](wheel_path)
    files["docdrift/cli.py"] += b"\n# changed after RECORD\n"
    with pytest.raises(DistributionError, match="RECORD hash"):
        CHECKER["check_record"](files, METADATA + "RECORD")


@pytest.mark.parametrize("name", ["../outside", "/absolute", "package/.aws/credentials", "package/__pycache__/code.pyc", "package\\escape"])
def test_archive_paths_cannot_leak_metadata_or_escape(name):
    with pytest.raises(DistributionError):
        CHECKER["safe_name"](name)


def test_smoke_environment_excludes_provider_credentials_and_checkout_paths(monkeypatch):
    for name, value in (("NEBIUS_API_KEY", "synthetic"), ("AWS_SECRET_ACCESS_KEY", "synthetic"),
                        ("PYTHONPATH", "/checkout/src"), ("HTTPS_PROXY", "https://proxy.invalid")):
        monkeypatch.setenv(name, value)
    environment = CHECKER["clean_environment"]()
    assert not set(environment) & {"NEBIUS_API_KEY", "AWS_SECRET_ACCESS_KEY", "PYTHONPATH", "HTTPS_PROXY"}
    assert environment["UV_OFFLINE"] == "1" and environment["UV_PYTHON_DOWNLOADS"] == "never"


def test_actual_wheel_installs_outside_checkout_and_runs_only_offline_commands(tmp_path):
    uv_binary = shutil.which("uv")
    assert uv_binary, "Development checks require uv with a populated offline cache"
    cache = Path(os.environ.get("UV_CACHE_DIR", "/tmp/docdrift-uv-cache"))
    wheel, source = CHECKER["build_distributions"](ROOT, tmp_path / "dist", cache, uv_binary)
    artifacts = CHECKER["check_artifacts"](wheel, source, ROOT)
    smoke = CHECKER["smoke_wheel"](wheel, ROOT, cache, uv_binary)
    assert artifacts["fixture_hashes_preserved"] and smoke["installed_outside_checkout"]
    assert smoke["fixture_inspection"] and smoke["offline_synthetic_contract"]
    assert smoke["static_policy_challenge"]
    assert smoke['synthetic_sandbox_repair'] and smoke['evidence_integrity']
    assert smoke["live_requests"] == smoke["paid_calls"] == smoke["code_executions"] == 0
