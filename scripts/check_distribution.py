"""Build and check installed DocDrift artifacts using cached dependencies only.

No Docker or target-example execution occurs. Run with the project's Python 3.12
environment and an existing uv cache. This script uses only the standard library.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


MAX_FILE_BYTES = 1_048_576
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_FILES = 2000
WHEEL_FIXTURE = "docdrift/data/renamed_method/"
FORBIDDEN = {".git", ".aws", ".ssh", ".env", ".codex", ".agents", ".venv", "__pycache__"}


class DistributionError(RuntimeError):
    pass


def clean_environment() -> dict[str, str]:
    """Do not forward provider keys, Git credentials, proxy or Python settings."""
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR") if key in os.environ}
    environment.update({"UV_OFFLINE": "1", "UV_PYTHON_DOWNLOADS": "never", "UV_NO_CONFIG": "1",
                        "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"})
    return environment


def run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=environment or clean_environment(),
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise DistributionError(f"{Path(command[0]).name} failed: {(result.stderr or result.stdout)[-4096:]}")
    return result.stdout


def build_distributions(source_root: Path, output: Path, cache_dir: Path, uv_binary: str) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    run([uv_binary, "build", str(source_root), "--out-dir", str(output), "--offline", "--no-python-downloads",
         "--cache-dir", str(cache_dir), "--python", sys.executable], cwd=source_root)
    return find_distributions(output)


def find_distributions(directory: Path) -> tuple[Path, Path]:
    wheels = sorted(directory.glob("docdrift-*.whl"))
    sources = sorted(directory.glob("docdrift-*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise DistributionError("Use a directory containing exactly one DocDrift wheel and one source archive")
    return wheels[0].resolve(), sources[0].resolve()


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or "\x00" in name or ".." in path.parts
            or str(path) != name.rstrip("/") or any(part in FORBIDDEN for part in path.parts)
            or path.suffix in {".pyc", ".pyo"}):
        raise DistributionError("Distribution contains an unsafe or unintended file path")
    return str(path)


def archive_files(path: Path) -> dict[str, bytes]:
    files = {}
    total = 0

    def add(name: str, size: int, stream) -> None:
        nonlocal total
        name = safe_name(name)
        if name in files or len(files) >= MAX_FILES or size < 0 or size > MAX_FILE_BYTES:
            raise DistributionError("Distribution contains duplicate or excessive files")
        data = stream.read(MAX_FILE_BYTES + 1)
        total += len(data)
        if len(data) != size or len(data) > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES:
            raise DistributionError("Distribution exceeds its content limits")
        files[name] = data

    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                safe_name(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise DistributionError("Distribution symlinks are unsupported")
                if not member.is_dir():
                    with archive.open(member) as stream:
                        add(member.filename, member.file_size, stream)
    else:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                safe_name(member.name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise DistributionError("Distribution contains a nonregular archive member")
                stream = archive.extractfile(member)
                if stream is None:
                    raise DistributionError("Distribution member is unreadable")
                with stream:
                    add(member.name, member.size, stream)
    return files


def check_fixture(files: dict[str, bytes], prefix: str, expected_manifest: bytes) -> int:
    manifest_name = prefix + "manifest.json"
    if files.get(manifest_name) != expected_manifest:
        raise DistributionError("Frozen owned fixture is missing or its manifest changed")
    manifest = json.loads(expected_manifest)
    expected_names = {"manifest.json", *manifest["files"]}
    actual_names = {name.removeprefix(prefix) for name in files if name.startswith(prefix)}
    if expected_names != actual_names or manifest["algorithm"] != "sha256":
        raise DistributionError("Frozen fixture inventory changed in the distribution")
    for name, digest in manifest["files"].items():
        if hashlib.sha256(files[prefix + name]).hexdigest() != digest:
            raise DistributionError(f"Frozen fixture bytes changed: {name}")
    return len(expected_names)


def check_record(files: dict[str, bytes], record_path: str) -> None:
    rows = csv.reader(io.StringIO(files[record_path].decode()))
    seen = set()
    for row in rows:
        if len(row) != 3 or row[0] in seen or row[0] not in files:
            raise DistributionError("Wheel RECORD inventory is invalid")
        name, digest, size = row
        seen.add(name)
        if name == record_path:
            if digest or size:
                raise DistributionError("Wheel RECORD must omit its own hash")
            continue
        expected = base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).rstrip(b"=").decode()
        if digest != f"sha256={expected}" or size != str(len(files[name])):
            raise DistributionError("Wheel RECORD hash or size mismatch")
    if seen != set(files):
        raise DistributionError("Wheel RECORD omits distribution files")


def check_artifacts(wheel: Path, source_archive: Path, source_root: Path) -> dict:
    wheel_files = archive_files(wheel)
    source_files = archive_files(source_archive)
    manifest = (source_root / "fixtures" / "renamed_method" / "manifest.json").read_bytes()
    fixture_count = check_fixture(wheel_files, WHEEL_FIXTURE, manifest)
    roots = {name.split("/", 1)[0] for name in source_files}
    if len(roots) != 1:
        raise DistributionError("Source archive requires one project root")
    source_prefix = roots.pop() + "/"
    check_fixture(source_files, source_prefix + "fixtures/renamed_method/", manifest)
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "src/docdrift/cli.py", "scripts/check_distribution.py"):
        if source_prefix + name not in source_files:
            raise DistributionError(f"Source archive omits {name}")
    if source_files[source_prefix + "LICENSE"] != (source_root / "LICENSE").read_bytes():
        raise DistributionError("Source license changed")
    metadata_names = [name for name in wheel_files if name.endswith(".dist-info/METADATA")]
    if len(metadata_names) != 1:
        raise DistributionError("Wheel package metadata is missing or ambiguous")
    metadata_name = metadata_names[0]
    metadata = BytesParser().parsebytes(wheel_files[metadata_name])
    if metadata.get("Name", "").lower() != "docdrift" or metadata["License-Expression"] != "MIT":
        raise DistributionError("Wheel must declare DocDrift and the MIT license")
    metadata_prefix = metadata_name.removesuffix("METADATA")
    license_name = metadata_prefix + "licenses/LICENSE"
    if wheel_files.get(license_name) != (source_root / "LICENSE").read_bytes():
        raise DistributionError("Wheel omits its project license")
    entries = configparser.ConfigParser()
    entries.read_string(wheel_files.get(metadata_prefix + "entry_points.txt", b"").decode())
    if entries.get("console_scripts", "docdrift", fallback="") != "docdrift.cli:main":
        raise DistributionError("Installed wheel omits the DocDrift CLI entry point")
    if metadata_prefix + "RECORD" not in wheel_files:
        raise DistributionError("Wheel RECORD is missing")
    check_record(wheel_files, metadata_prefix + "RECORD")
    package_source = {
        "docdrift/" + path.relative_to(source_root / "src/docdrift").as_posix(): path.read_bytes()
        for path in (source_root / "src/docdrift").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }
    packaged_source = {name: data for name, data in wheel_files.items()
                       if name.startswith("docdrift/") and not name.startswith(WHEEL_FIXTURE)}
    if set(package_source) != set(packaged_source):
        raise DistributionError("Wheel package source inventory differs from the checkout")
    for name, data in packaged_source.items():
        if package_source[name] != data or source_files.get(source_prefix + "src/" + name) != data:
            raise DistributionError("Wheel package source differs from the source archive or checkout")
    return {"wheel": wheel.name, "sdist": source_archive.name, "version": metadata["Version"],
            "fixture_files": fixture_count, "fixture_hashes_preserved": True,
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "sdist_sha256": hashlib.sha256(source_archive.read_bytes()).hexdigest()}


# Installed smoke checks may only perform local Git operations. This is a test
# tripwire for this owned CLI, not a public untrusted-code sandbox.
SMOKE_GUARD = r'''
import os
import socket
import subprocess

def denied(*args, **kwargs):
    raise RuntimeError("Distribution smoke prohibits network access")

socket.create_connection = denied
socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
original_popen = subprocess.Popen

def local_git_only(args, *extra, **kwargs):
    if isinstance(args, str) or kwargs.get("shell") or kwargs.get("executable"):
        raise RuntimeError("Distribution smoke prohibits shell execution")
    if not args or os.path.basename(os.fspath(args[0])) != "git":
        raise RuntimeError("Distribution smoke prohibits Docker and other subprocesses")
    index = 1
    while index < len(args) and args[index] in {"-C", "-c"}:
        index += 2
    if index >= len(args) or args[index] not in {"init", "add", "commit", "rev-parse", "ls-tree", "archive"}:
        raise RuntimeError("Distribution smoke permits only local Git inspection")
    return original_popen(args, *extra, **kwargs)

subprocess.Popen = local_git_only
'''


def smoke_wheel(wheel: Path, source_root: Path, cache_dir: Path, uv_binary: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="docdrift-distribution-") as temporary:
        root = Path(temporary)
        environment_path = root / "installed"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(environment_path)
        interpreter = environment_path / "bin" / "python"
        requirements = root / "locked-runtime.txt"
        run([uv_binary, "export", "--project", str(source_root), "--locked", "--no-dev", "--no-emit-project",
             "--no-editable", "--format", "requirements.txt", "--output-file", str(requirements),
             "--offline", "--cache-dir", str(cache_dir)], cwd=root)
        run([uv_binary, "pip", "install", "--offline", "--require-hashes", "--python", str(interpreter),
             "--cache-dir", str(cache_dir), "--requirements", str(requirements)], cwd=root)
        run([uv_binary, "pip", "install", "--offline", "--no-deps", "--python", str(interpreter),
             "--cache-dir", str(cache_dir), str(wheel)], cwd=root)
        locations = json.loads(run([str(interpreter), "-I", "-c",
                                   "import json,sysconfig;import docdrift;print(json.dumps({'module':docdrift.__file__,'site':sysconfig.get_paths()['purelib']}))"], cwd=root))
        if not Path(locations["module"]).resolve().is_relative_to(environment_path.resolve()):
            raise DistributionError("Installed smoke imported the checkout instead of the wheel")
        (Path(locations["site"]) / "sitecustomize.py").write_text(SMOKE_GUARD)
        help_text = run([str(environment_path / "bin" / "docdrift"), "--help"], cwd=root)
        if "sandbox-contract-demo" not in help_text:
            raise DistributionError("Installed CLI help is incomplete")
        inspected = json.loads(run([str(interpreter), "-I", "-m", "docdrift", "demo", "--inspect-only"], cwd=root))
        if (inspected.get("execution") != "not_run" or inspected.get("behavior_verified") is not False
                or len(inspected.get("examples", [])) != 2):
            raise DistributionError("Installed fixture inspection failed or claimed execution")
        contract = json.loads(run([str(interpreter), "-I", "-m", "docdrift", "--state-dir", str(root / "state"),
                                  "sandbox-contract-demo"], cwd=root))
        if (contract.get("mode") != "offline_synthetic_contract" or contract.get("status") != "contract_checks_passed"
                or any(contract.get(key) != 0 for key in ("live_requests", "paid_calls", "code_executions"))
                or contract.get("behavior_verified") is not False or not all(contract.get("checks", {}).values())):
            raise DistributionError("Installed synthetic contract failed its zero-execution limits")
        challenge = json.loads(run([str(interpreter), "-I", "-m", "docdrift", "--state-dir", str(root / "state"),
                                   "challenge"], cwd=root))
        if (challenge.get("kind") != "static_policy_challenge" or challenge.get("all_expectations_met") is not True
                or any(challenge.get(key) is not False for key in ("execution_performed", "behavior_verified", "milestone_3_complete"))
                or challenge.get("static_controls_accepted") != 1 or challenge.get("rejected_proposals", 0) < 1):
            raise DistributionError("Installed static challenge failed or claimed execution")
        return {"installed_outside_checkout": True, "console_help": True, "fixture_inspection": True,
                "offline_synthetic_contract": True, "static_policy_challenge": True,
                "live_requests": 0, "paid_calls": 0, "code_executions": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--cache-dir", type=Path, required=True, help="Existing uv dependency/build cache; downloads stay disabled")
    parser.add_argument("--build", action="store_true", help="Build a wheel and source archive offline first")
    parser.add_argument("--artifacts-only", action="store_true", help="Validate archive contents without installing the wheel")
    args = parser.parse_args()
    try:
        source_root = args.source_root.resolve()
        uv_binary = shutil.which("uv")
        if uv_binary is None:
            raise DistributionError("uv is required for offline build/installed checks")
        wheel, source_archive = (build_distributions(source_root, args.dist_dir.resolve(), args.cache_dir.resolve(), uv_binary)
                                 if args.build else find_distributions(args.dist_dir.resolve()))
        report = check_artifacts(wheel, source_archive, source_root)
        if not args.artifacts_only:
            report["smoke"] = smoke_wheel(wheel, source_root, args.cache_dir.resolve(), uv_binary)
        print(json.dumps(report, indent=2))
    except (DistributionError, OSError, ValueError, zipfile.BadZipFile, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Distribution check failed: {error}\n")


if __name__ == "__main__":
    main()
