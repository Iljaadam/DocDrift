"""Prepare an isolated judge service locally; never start it or call a provider.

Run this from the owner's normal terminal. Secrets stay outside the repository;
the web process receives a password digest and no provider key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


class SetupError(RuntimeError):
    pass


def _directory(path: Path) -> None:
    if path.is_symlink():
        raise SetupError(f"Directory must not be a symlink: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise SetupError(f"Directory must be owned by this user and not writable by others: {path}")


def _private_bytes(path: Path) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise SetupError(f"Cannot open private file: {path}") from exc
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
            raise SetupError(f"Private file must be a regular, owned mode-600 file of at most 4 KiB: {path}")
        return stream.read(4097)


def _new_file(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    except FileExistsError as exc:
        raise SetupError(f"Existing file will not be replaced: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def public_origin(value: str) -> str:
    """Accept an exact HTTPS origin, or the explicit local inspection origin."""
    if value == "http://127.0.0.1:8765":
        return value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SetupError("Public origin must be an HTTPS origin without a path") from exc
    if (not value.isascii() or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or value not in {f"https://{parsed.netloc}", f"https://{parsed.netloc}/"}
            or any(ord(character) <= 32 or ord(character) == 127 for character in value)
            or port == 0 or "\\" in value):
        raise SetupError("Public origin must be an HTTPS origin without a path")
    return value.rstrip("/")


def prepare(config_dir: Path, state_root: Path, origin: str) -> dict[str, object]:
    origin = public_origin(origin)
    _directory(config_dir)
    _directory(state_root)
    password_path = config_dir / "judge-password.txt"
    environment_path = config_dir / "judge.env"
    if environment_path.exists() or environment_path.is_symlink():
        environment = _private_bytes(environment_path)
        password = _private_bytes(password_path).rstrip(b"\n")
    else:
        environment = None
        if password_path.exists() or password_path.is_symlink():
            password = _private_bytes(password_path).rstrip(b"\n")
        else:
            password = secrets.token_urlsafe(32).encode("ascii")
            _new_file(password_path, password + b"\n")
    if len(password) < 32 or len(password) > 256 or not password.isascii() or any(c <= 32 for c in password):
        raise SetupError("Saved judge password has an unsupported format; it was left unchanged")
    expected = (f"DOCDRIFT_JUDGE_PASSWORD_SHA256={hashlib.sha256(password).hexdigest()}\n"
                f"DOCDRIFT_JUDGE_PUBLIC_ORIGIN={origin}\n").encode("ascii")
    if environment is None:
        _new_file(environment_path, expected)
    elif environment != expected:
        raise SetupError("Saved judge.env differs; no secret was replaced. Review it before changing the origin")
    return {"status": "prepared_offline", "password_file": str(password_path),
            "environment_file": str(environment_path), "public_origin": origin,
            "state_root": str(state_root), "services_started": False, "provider_requests": 0}


def _unit_path(value: Path | str) -> str:
    value = str(value)
    if any(character in value for character in ("\n", "\r", "\x00")):
        raise SetupError("Service paths must not contain control characters")
    return value.replace("%", "%%")


def _unit_argument(value: Path | str) -> str:
    return '"' + _unit_path(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_units(repo_root: Path, config_dir: Path, state_root: Path, authorization: Path) -> dict[str, bytes]:
    substitutions = {
        # These directives consume one whole path, not a quoted argv word.
        "@REPO_ROOT@": _unit_path(repo_root),
        "@PYTHON@": _unit_argument(repo_root / ".venv/bin/python"),
        "@JUDGE_ENV@": _unit_path(config_dir / "judge.env"),
        "@NEBIUS_ENV@": _unit_path(config_dir / "nebius.env"),
        "@PRIVATE_FILES@": " ".join(_unit_argument("-" + str(path)) for path in
                                     (config_dir / "judge-password.txt", config_dir / "nebius.env")),
        "@STATE_ROOT@": _unit_argument(state_root),
        "@AUTHORIZATION@": _unit_argument(authorization),
    }
    rendered = {}
    for role in ("web", "worker"):
        name = f"docdrift-judge-{role}.service"
        template = (repo_root / "deploy" / name).read_text()
        for token, value in substitutions.items():
            template = template.replace(token, value)
        if "@" in template:
            raise SetupError("Service template contains an unresolved placeholder")
        rendered[name] = template.encode()
    return rendered


def install(repo_root: Path, config_dir: Path, unit_dir: Path, state_root: Path,
            authorization: Path) -> dict[str, object]:
    # Validate without reading or copying the provider key.
    _private_bytes(config_dir / "judge.env")
    _private_bytes(config_dir / "judge-password.txt")
    key_path = config_dir / "nebius.env"
    info = key_path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise SetupError("The existing nebius.env must be an owned mode-600 regular file")
    if not (repo_root / ".venv/bin/python").is_file() or not authorization.is_file():
        raise SetupError("The repository virtualenv and prepared authorization record must exist")
    if authorization.is_symlink():
        raise SetupError("The authorization record must not be a symlink")
    _directory(state_root)
    _directory(unit_dir)
    units = render_units(repo_root, config_dir, state_root, authorization)
    # Check both before writing either; an unrelated service file is never replaced.
    for name, content in units.items():
        destination = unit_dir / name
        if destination.is_symlink() or (destination.exists() and destination.read_bytes() != content):
            raise SetupError(f"Existing unit differs and will not be overwritten: {destination}")
    for name, content in units.items():
        destination = unit_dir / name
        if not destination.exists():
            _new_file(destination, content)
    completed = subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=20)
    if completed.returncode:
        raise SetupError("Units were written, but systemctl --user daemon-reload failed; inspect your user manager")
    return {"status": "user_units_installed", "unit_directory": str(unit_dir),
            "units": list(units), "services_started": False, "provider_requests": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="Create a private passphrase and digest environment, offline")
    action.add_argument("--install", action="store_true", help="Install user units and reload the user manager; do not start them")
    parser.add_argument("--public-origin", help="Exact HTTPS origin; http://127.0.0.1:8765 is allowed for local inspection")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".config/docdrift")
    parser.add_argument("--unit-dir", type=Path, default=Path.home() / ".config/systemd/user")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.absolute()
    state_root = (args.state_root or repo_root / ".docdrift/judge").absolute()
    authorization = (args.authorization or repo_root / ".docdrift/access/judge-authorization-2026-10-22.json").absolute()
    try:
        if args.prepare:
            if not args.public_origin:
                raise SetupError("--prepare requires --public-origin")
            result = prepare(args.config_dir.absolute(), state_root, args.public_origin)
        else:
            if args.public_origin:
                raise SetupError("--public-origin belongs to --prepare")
            result = install(repo_root, args.config_dir.absolute(), args.unit_dir.absolute(), state_root, authorization)
    except (SetupError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"setup_failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
