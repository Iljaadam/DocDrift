"""Offline local containers for trusted development, never host execution.

This adapter is not a public sandbox and does not establish Nebius access or
competition eligibility. It uses existing local images only.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable


MAX_LOG_BYTES = 262_144
_IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}\Z")
_OPERATION_ID = re.compile(r"[a-f0-9]{12,64}\Z")
_FORBIDDEN_SNAPSHOT_NAMES = {".git", ".aws", ".ssh", ".codex", ".agents", ".env"}


@dataclass(frozen=True)
class ExecutionRequest:
    snapshot: Path
    code: str
    environment: dict[str, str]
    image: str
    timeout_seconds: int = 30
    log_limit_bytes: int = MAX_LOG_BYTES

    def __post_init__(self) -> None:
        # A frozen dataclass alone would still expose a mutable caller-owned
        # environment dictionary between preflight and execution.
        object.__setattr__(self, "snapshot", Path(self.snapshot))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))


@dataclass(frozen=True)
class ExecutionResult:
    state: str
    exit_code: int | None
    stdout: str
    stderr: str
    operation_id: str | None
    image_id: str | None
    elapsed_seconds: float | None
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    service_state: str | None = None
    signal: int | None = None
    observation_timed_out: bool = False
    evidence_complete: bool = True
    synthetic: bool = False
    error_code: str | None = None


class AdapterError(RuntimeError):
    def __init__(self, message: str, operation_id: str | None = None):
        super().__init__(message)
        self.operation_id = operation_id


# This runs only inside the container. Draining pipes prevents an example from
# filling controller RAM or Docker's log storage. The outer local log driver is
# bounded as a second defense. This capture process is not an acceptance oracle.
_CAPTURE_RUNNER = r'''
import base64
import json
import os
import signal
import subprocess
import sys
import threading
import time

limit = int(sys.argv[1])
started = time.monotonic()
child = subprocess.Popen(
    [sys.executable, "-B", "/work/example.py"],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    start_new_session=True,
)
captured = {"stdout": bytearray(), "stderr": bytearray()}
truncated = {"stdout": False, "stderr": False}

def terminate(signum, frame):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

signal.signal(signal.SIGTERM, terminate)

def drain(name, stream):
    while True:
        chunk = stream.read(8192)
        if not chunk:
            break
        remaining = limit - len(captured[name])
        captured[name].extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated[name] = True

threads = [threading.Thread(target=drain, args=(name, stream), daemon=True)
           for name, stream in (("stdout", child.stdout), ("stderr", child.stderr))]
for thread in threads:
    thread.start()
exit_code = child.wait()
# A descendant retaining pipe handles must not keep collection alive forever.
for thread in threads:
    thread.join(timeout=1)
for name, thread in zip(("stdout", "stderr"), threads):
    if thread.is_alive():
        truncated[name] = True
print(json.dumps({
    "format": "docdrift-local-v1", "exit_code": exit_code,
    "stdout": base64.b64encode(captured["stdout"]).decode("ascii"),
    "stderr": base64.b64encode(captured["stderr"]).decode("ascii"),
    "stdout_truncated": truncated["stdout"], "stderr_truncated": truncated["stderr"],
    "elapsed_seconds": time.monotonic() - started,
}), flush=True)
sys.exit(exit_code if 0 <= exit_code <= 255 else 1)
'''


class LocalDockerAdapter:
    def __init__(self, work_root: Path | None = None, *, docker_binary: str = "docker"):
        self.work_root = Path(work_root) if work_root is not None else Path(tempfile.mkdtemp(prefix="docdrift-docker-"))
        self.work_root = self.work_root.resolve()
        self.work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.docker_binary = docker_binary
        self._images: dict[str, dict] = {}

    def _run(self, arguments: list[str], *, timeout: float = 15, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                [self.docker_binary, *arguments], stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=timeout, check=False,
            )
        except FileNotFoundError as error:
            raise AdapterError("Docker CLI is unavailable; target examples were not run") from error
        except subprocess.TimeoutExpired:
            raise
        if check and result.returncode != 0:
            message = (result.stderr or result.stdout).strip()[:4096]
            raise AdapterError(f"Docker {arguments[0]} failed: {message}")
        return result

    @staticmethod
    def _isolation() -> list[str]:
        return [
            "--network", "none", "--read-only", "--user", "65534:65534",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1",
            "--ipc", "none", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
            "--ulimit", "nofile=64:64", "--entrypoint", "python",
        ]

    def preflight(self, image: str) -> dict:
        if not isinstance(image, str) or not image or len(image) > 256 or "\x00" in image:
            raise ValueError("A local Docker image reference is required")
        try:
            inspected = self._run(["image", "inspect", "--format", "{{json .}}", "--", image])
            details = json.loads(inspected.stdout)
        except (json.JSONDecodeError, TypeError) as error:
            raise AdapterError("Docker returned invalid image metadata") from error
        if not isinstance(details, dict):
            raise AdapterError("Docker returned invalid image metadata")
        image_id = details.get("Id", "")
        if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
            raise AdapterError("Preflight did not resolve an immutable Docker image ID")
        if details.get("Os", "linux") != "linux":
            raise AdapterError("Only Linux Docker images are supported")
        version = self._run([
            "run", "--rm", "--pull", "never", *self._isolation(),
            image_id, "--version",
        ])
        python_version = (version.stdout or version.stderr).strip()
        if not re.fullmatch(r"Python 3\.12\.\d+", python_version):
            raise AdapterError(f"Python 3.12 is required in the existing image (found {python_version!r})")
        information = {
            "image": image, "image_id": image_id, "python_version": python_version,
            "network": "none", "trusted_local_only": True,
        }
        self._images[image] = information
        self._images[image_id] = information
        return dict(information)

    @staticmethod
    def _validate_request(request: ExecutionRequest) -> None:
        if not isinstance(request.timeout_seconds, int) or not 1 <= request.timeout_seconds <= 300:
            raise ValueError("Execution timeout must be between 1 and 300 seconds")
        if not isinstance(request.log_limit_bytes, int) or not 1 <= request.log_limit_bytes <= MAX_LOG_BYTES:
            raise ValueError("Log limit must be between 1 and 262144 bytes per stream")
        if len(request.code.encode("utf-8")) > MAX_LOG_BYTES:
            raise ValueError("Example code exceeds the 256 KiB limit")
        if set(request.environment) - {"DOCDRIFT_INPUT"}:
            raise ValueError("Only the nonsecret DOCDRIFT_INPUT guest environment variable is allowed")
        for key, value in request.environment.items():
            if not isinstance(value, str) or "\x00" in value or len(value.encode("utf-8")) > 65_536:
                raise ValueError(f"Invalid guest environment value for {key}")

    @staticmethod
    def _copy_snapshot(source: Path, destination: Path) -> None:
        source = Path(source)
        if source.is_symlink() or any(part in _FORBIDDEN_SNAPSHOT_NAMES for part in source.parts):
            raise ValueError("Execution snapshot cannot be a credential/metadata directory or symlink")
        source = source.resolve()
        if not source.is_dir():
            raise ValueError("Execution snapshot must be a directory")
        count = 0
        total = 0
        for directory, folders, files in os.walk(source, followlinks=False):
            for name in folders + files:
                path = Path(directory) / name
                if name in _FORBIDDEN_SNAPSHOT_NAMES:
                    raise ValueError(f"Snapshot contains prohibited credential/metadata entry: {name}")
                if path.is_symlink():
                    raise ValueError("Symlinks are not allowed in execution snapshots")
            for name in files:
                path = Path(directory) / name
                if not path.is_file():
                    raise ValueError("Snapshot contains a nonregular file")
                count += 1
                total += path.stat().st_size
                if count > 2000 or total > 50 * 1024 * 1024:
                    raise ValueError("Execution snapshot exceeds repository limits")
        shutil.copytree(source, destination)
        destination.chmod(0o755)
        for directory, folders, files in os.walk(destination):
            for name in folders:
                (Path(directory) / name).chmod(0o755)
            for name in files:
                (Path(directory) / name).chmod(0o644)

    def submit(self, request: ExecutionRequest, on_accepted: Callable[[str], None]) -> str:
        self._validate_request(request)
        information = self._images.get(request.image) or self.preflight(request.image)
        request_id = uuid.uuid4().hex
        directory = self.work_root / request_id
        directory.mkdir(mode=0o755)
        snapshot = directory / "snapshot"
        work = directory / "work"
        try:
            self._copy_snapshot(request.snapshot, snapshot)
            work.mkdir(mode=0o755)
            (work / "example.py").write_text(request.code, encoding="utf-8")
            (work / "capture.py").write_text(_CAPTURE_RUNNER, encoding="utf-8")
            for file in work.iterdir():
                file.chmod(0o644)
            arguments = [
                "create", "--pull", "never", *self._isolation(),
                "--label", "docdrift.managed=true", "--label", f"docdrift.request={request_id}",
                "--label", f"docdrift.log-limit={request.log_limit_bytes}",
                "--label", f"docdrift.timeout={request.timeout_seconds}",
                "--log-driver", "local", "--log-opt", "max-size=2m", "--log-opt", "max-file=1",
                "--log-opt", "compress=false",
                "--workdir", "/snapshot",
                "--mount", f"type=bind,src={snapshot},dst=/snapshot,readonly",
                "--mount", f"type=bind,src={work},dst=/work,readonly",
                "--env", "PYTHONPATH=/snapshot", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "PYTHONNOUSERSITE=1",
            ]
            for key, value in sorted(request.environment.items()):
                arguments.extend(["--env", f"{key}={value}"])
            arguments.extend([information["image_id"], "-B", "/work/capture.py", str(request.log_limit_bytes)])
            operation_id = self._run(arguments).stdout.strip()
            if not _OPERATION_ID.fullmatch(operation_id):
                raise AdapterError("Docker create returned an invalid operation ID")
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        try:
            # If this fails, leave the unstarted known container for recovery.
            on_accepted(operation_id)
        except Exception as error:
            raise AdapterError("Operation was created but its acceptance callback failed; it was not started", operation_id) from error
        try:
            self._run(["start", operation_id])
        except Exception as error:
            raise AdapterError(
                f"Known operation could not be started; reconcile its recorded ID: {str(error)[:4096]}",
                operation_id,
            ) from error
        return operation_id

    def _inspect(self, operation_id: str) -> dict:
        if not _OPERATION_ID.fullmatch(operation_id):
            raise ValueError("Invalid Docker operation ID")
        result = self._run(["inspect", "--format", "{{json .}}", operation_id])
        try:
            details = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AdapterError("Docker returned invalid operation metadata", operation_id) from error
        if not isinstance(details, dict):
            raise AdapterError("Docker returned invalid operation metadata", operation_id)
        if details.get("Config", {}).get("Labels", {}).get("docdrift.managed") != "true":
            raise AdapterError("Refusing to manage a container outside DocDrift", operation_id)
        return details

    def observe(self, operation_id: str, timeout_seconds: int = 30) -> ExecutionResult:
        if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
            raise ValueError("Observation timeout must be between 1 and 300 seconds")
        started = time.monotonic()
        details = self._inspect(operation_id)
        status = details.get("State", {}).get("Status")
        if status == "created":
            self._run(["start", operation_id])
            details = self._inspect(operation_id)
            status = details.get("State", {}).get("Status")
        timed_out = False
        if status in {"running", "restarting", "paused"}:
            # Recovery must not reset the original execution's runtime budget.
            limit = min(timeout_seconds, int(details.get("Config", {}).get("Labels", {}).get("docdrift.timeout", timeout_seconds)))
            remaining = float(limit)
            started_at = details.get("State", {}).get("StartedAt")
            if started_at:
                try:
                    execution_start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - execution_start).total_seconds()
                    remaining = max(0, limit - max(0, age))
                except (ValueError, TypeError):
                    raise AdapterError("Known operation has an invalid execution start time", operation_id)
            try:
                if remaining == 0:
                    raise subprocess.TimeoutExpired([self.docker_binary, "wait", operation_id], limit)
                self._run(["wait", operation_id], timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                self.cancel(operation_id)
        details = self._inspect(operation_id)
        state = details.get("State", {})
        image_id = details.get("Image")
        result = self.download(operation_id)
        if result.get("capture_valid"):
            exit_code = result["exit_code"]
            stdout = result["stdout"]
            stderr = result["stderr"]
            elapsed = result["elapsed_seconds"]
            stdout_truncated = result["stdout_truncated"]
            stderr_truncated = result["stderr_truncated"]
            execution_limit = int(details.get("Config", {}).get("Labels", {}).get("docdrift.timeout", timeout_seconds))
            if elapsed > execution_limit:
                # A controller interruption may allow the guest to finish
                # after its deadline. Its completed output is still evidence,
                # but it cannot become a successful bounded execution.
                timed_out = True
        else:
            exit_code = state.get("ExitCode") if state.get("Status") in {"exited", "dead"} else None
            stdout = ""
            stderr = result["stderr"]
            elapsed = time.monotonic() - started
            stdout_truncated = True
            stderr_truncated = True
        terminal = state.get("Status") in {"exited", "dead"}
        outcome = "timed_out" if timed_out else (
            "completed" if terminal and result.get("capture_valid") else "error"
        )
        return ExecutionResult(
            state=outcome, exit_code=exit_code, stdout=stdout, stderr=stderr,
            operation_id=operation_id, image_id=image_id, elapsed_seconds=elapsed,
            timed_out=timed_out, stdout_truncated=stdout_truncated, stderr_truncated=stderr_truncated,
        )

    def download(self, operation_id: str) -> dict:
        details = self._inspect(operation_id)
        limit = int(details.get("Config", {}).get("Labels", {}).get("docdrift.log-limit", MAX_LOG_BYTES))
        limit = min(max(limit, 1), MAX_LOG_BYTES)
        logs = self._run(["logs", "--tail", "1", operation_id], check=False)
        try:
            payload = json.loads(logs.stdout)
            if not isinstance(payload, dict):
                raise ValueError("Invalid capture envelope")
            if payload.get("format") != "docdrift-local-v1":
                raise ValueError("Unrecognized capture envelope")
            decoded = {}
            for name in ("stdout", "stderr"):
                value = base64.b64decode(payload[name], validate=True)
                decoded[name] = value[:limit].decode("utf-8", errors="replace")
                decoded[f"{name}_truncated"] = bool(payload[f"{name}_truncated"]) or len(value) > limit
            exit_code = payload["exit_code"]
            elapsed = payload["elapsed_seconds"]
            if not isinstance(exit_code, int) or not isinstance(elapsed, (int, float)) or not 0 <= elapsed < float("inf"):
                raise ValueError("Invalid capture result types")
            return {"capture_valid": True, "exit_code": exit_code, "elapsed_seconds": float(elapsed), **decoded}
        except (ValueError, TypeError, KeyError):
            return {
                "capture_valid": False,
                "stderr": "Execution capture is unavailable or invalid; output evidence is incomplete.\n"
                + (logs.stderr or "")[:limit],
            }

    def cancel(self, operation_id: str) -> None:
        details = self._inspect(operation_id)
        status = details.get("State", {}).get("Status")
        if status in {"running", "restarting", "paused"}:
            self._run(["stop", "--time", "1", operation_id], timeout=10)

    def cleanup(self, operation_id: str) -> None:
        details = self._inspect(operation_id)
        request_id = details.get("Config", {}).get("Labels", {}).get("docdrift.request", "")
        if details.get("State", {}).get("Status") in {"running", "restarting", "paused"}:
            self.cancel(operation_id)
        self._run(["rm", operation_id])
        if re.fullmatch(r"[a-f0-9]{32}", request_id):
            shutil.rmtree(self.work_root / request_id, ignore_errors=True)

    def execute(self, request: ExecutionRequest, on_accepted: Callable[[str], None]) -> ExecutionResult:
        operation_id = self.submit(request, on_accepted)
        return self.observe(operation_id, request.timeout_seconds)
