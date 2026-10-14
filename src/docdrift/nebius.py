"""Documented Sandbox REST contract with live mutations permanently disabled.

Only explicitly selected ``httpx.MockTransport`` simulations can mutate. No
environment credentials are read, and this module makes no inference calls.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Callable, Mapping, TYPE_CHECKING

import httpx

from .profile import strict_json

if TYPE_CHECKING:
    from .remote_journal import SubmissionJournal


BASE_URL = "https://api.tokenfactory.nebius.com/sandboxes/v1/"
MAX_LOG_BYTES = 262_144
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_SERVICE_STATES = {"PENDING", "ASSIGNED", "EXECUTING", "SUCCESS", "FAILED", "CANCELLED"}
_TERMINAL_STATES = {"SUCCESS", "FAILED", "CANCELLED"}
_CREDENTIAL_NAMES = {".git", ".aws", ".ssh", ".env", ".codex", ".agents"}


class RemoteAdapterError(RuntimeError):
    """Safe machine codes only: never retain a request, headers, or raw errors."""

    def __init__(self, code: str, *, operation_id: str | None = None, attempt_id: str | None = None):
        super().__init__(code)
        self.code = code
        self.operation_id = operation_id
        self.attempt_id = attempt_id


class RemoteMutationsDisabled(RemoteAdapterError):
    def __init__(self):
        super().__init__("live_mutations_disabled_zero_personal_spend")


class UncertainSubmission(RemoteAdapterError):
    """Submission may exist remotely. Repeating its POST is prohibited."""


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an immutable UUID")
    try:
        normalized = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise ValueError(f"{name} must be an immutable UUID") from None
    if value != normalized or normalized == str(uuid.UUID(int=0)):
        raise ValueError(f"{name} must be a canonical nonzero UUID")
    return normalized


def _guest_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value or "\\" in value:
        raise ValueError("Invalid guest file path")
    path = PurePosixPath(value)
    if (not path.is_absolute() or ".." in path.parts or str(path) != value
            or not value.startswith("/work/docdrift/") or any(part in _CREDENTIAL_NAMES for part in path.parts)):
        raise ValueError("Guest files must be canonical paths beneath /work/docdrift/")
    return value


@dataclass(frozen=True)
class UploadedFile:
    uuid: str
    sha256: str
    size: int


@dataclass(frozen=True)
class RemoteExecutionRequest:
    image_id: str
    executable: str
    args: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    files: Mapping[str, UploadedFile | str] = field(default_factory=dict)
    disposable: bool = True
    timeout_seconds: int = 30
    log_limit_bytes: int = MAX_LOG_BYTES

    def __post_init__(self):
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))


@dataclass(frozen=True)
class RemoteResult:
    operation_id: str
    image_id: str | None
    result_image_id: str | None
    state: str
    service_state: str
    exit_code: int | None
    signal: int | None
    timed_out: bool
    observation_timed_out: bool
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    elapsed_seconds: float | None
    evidence_complete: bool
    resources: dict[str, int | float]
    error_code: str | None = None
    synthetic: bool = False

    @property
    def execution_passed(self) -> bool:
        # This is execution status only. It supplies no behavioral verdict.
        return (
            self.state == "completed" and self.service_state == "SUCCESS"
            and self.exit_code == 0 and self.signal in {None, 0}
            and not self.timed_out and not self.observation_timed_out
            and self.evidence_complete and not self.stdout_truncated and not self.stderr_truncated
        )


class NebiusSandboxAdapter:
    """GET-only live client; all operation contracts can be tested offline."""

    def __init__(self, api_key: str, project_id: str, *, transport: httpx.BaseTransport | None = None,
                 offline_simulation: bool = False, journal: SubmissionJournal | None = None):
        for name, value in (("api_key", api_key), ("project_id", project_id)):
            if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(char) < 32 or ord(char) > 126 for char in value):
                raise ValueError(f"Invalid {name}")
        if type(offline_simulation) is not bool:
            raise ValueError("offline_simulation must be explicit boolean")
        if offline_simulation and type(transport) is not httpx.MockTransport:
            raise ValueError("Offline simulation requires an explicit httpx.MockTransport")
        self._offline_simulation = offline_simulation
        self.journal = journal
        self._client = httpx.Client(
            base_url=BASE_URL, transport=transport, timeout=httpx.Timeout(20),
            headers={"Authorization": f"Bearer {api_key}", "Project": project_id, "Accept-Encoding": "identity"},
            trust_env=False, follow_redirects=False,
        )
        self._accepted: dict[str, str] = {}
        self._expected_images: dict[str, str] = {}
        self._expected_disposable: dict[str, bool] = {}
        self._uploads: dict[str, UploadedFile] = {}
        self._upload_attempts: set[str] = set()

    def close(self) -> None:
        self._client.close()

    @property
    def offline_simulation(self) -> bool:
        return self._offline_simulation

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _require_mutations(self) -> None:
        if (not self._offline_simulation or type(self._client._transport) is not httpx.MockTransport
                or any(transport is not None and transport is not self._client._transport for transport in self._client._mounts.values())):
            raise RemoteMutationsDisabled()

    def _request(self, method: str, path: str, *, payload: dict | None = None, content: bytes | None = None,
                 params: dict | None = None, limit: int = MAX_RESPONSE_BYTES) -> tuple[int, bytes]:
        if method not in {"GET", "HEAD"}:
            self._require_mutations()
        if (not isinstance(path, str) or path.startswith("/") or any(character in path for character in (":", "?", "#", "\\"))
                or any(part in {".", ".."} for part in path.split("/"))):
            raise RemoteAdapterError("invalid_rest_path")
        transport_failure = None
        try:
            with self._client.stream(method, path, json=payload, content=content, params=params,
                                     headers={"Content-Type": "application/octet-stream"} if content is not None else None) as response:
                if not 200 <= response.status_code < 300:
                    raise RemoteAdapterError(f"http_{response.status_code}")
                encoding = response.headers.get("content-encoding")
                if encoding is not None and encoding.lower().strip() != "identity":
                    raise RemoteAdapterError("compressed_response_forbidden")
                declared = response.headers.get("content-length")
                if declared is not None:
                    if re.fullmatch(r"[0-9]+", declared) is None:
                        raise RemoteAdapterError("invalid_content_length")
                    if len(declared) > 20 or int(declared) > limit:
                        raise RemoteAdapterError("response_limit_exceeded")
                data = bytearray()
                # HTTPX decoding can allocate a decompression bomb before a
                # caller checks the decoded length. Read bounded raw chunks.
                # MockTransport responses may already contain owned bytes.
                if response.is_stream_consumed:
                    if len(response.content) > limit:
                        raise RemoteAdapterError("response_limit_exceeded")
                    chunks = (response.content,)
                else:
                    chunks = response.iter_raw(chunk_size=8192)
                for chunk in chunks:
                    if len(data) + len(chunk) > limit:
                        raise RemoteAdapterError("response_limit_exceeded")
                    data.extend(chunk)
                return response.status_code, bytes(data)
        except httpx.TimeoutException:
            transport_failure = "transport_timeout"
        except httpx.TransportError:
            transport_failure = "transport_error"
        # Raise after leaving the exception handler: suppressing display with
        # ``from None`` alone would still retain the credential-bearing HTTPX
        # request on ``__context__``.
        raise RemoteAdapterError(transport_failure)

    @staticmethod
    def _object(data: bytes) -> dict:
        try:
            value = strict_json(data)
        except (ValueError, UnicodeDecodeError):
            value = None
        if not isinstance(value, dict):
            raise RemoteAdapterError("invalid_json_response")
        return value

    def preflight(self, image_id: str | None = None) -> dict:
        if image_id is not None:
            _uuid(image_id, "image_id")
        _, data = self._request("GET", "whoami")
        information = self._object(data)
        permissions = information.get("permissions")
        limits = information.get("limits", {})
        if not isinstance(permissions, dict) or not isinstance(limits, dict):
            raise RemoteAdapterError("invalid_preflight_response")
        permission_values = {key: value for key, value in permissions.items()
                             if isinstance(key, str) and re.fullmatch(r"[a-z_]{1,64}", key) and type(value) is bool}
        limit_values = {key: value for key, value in limits.items()
                        if isinstance(key, str) and re.fullmatch(r"[a-z_]{1,64}", key)
                        and type(value) in {int, float} and 0 <= value <= 1e100 and math.isfinite(value)}
        if image_id is not None:
            _, data = self._request("GET", f"inspect/{image_id}/")
            image = self._object(data)
            if image.get("uuid") != image_id:
                raise RemoteAdapterError("invalid_image_response")
        return {
            "permissions": permission_values, "limits": limit_values, "image_id": image_id,
            "synthetic": self.offline_simulation, "live_mutations_enabled": False,
            "personal_spend_limit": 0, "credit_coverage_confirmed": False,
            "network_isolation_tested": False,
        }

    def prepare(self, files: Mapping[str, bytes]) -> dict[str, UploadedFile]:
        """Upload frozen bytes only; image import/install is deliberately absent."""
        self._require_mutations()
        if len(files) > 2000:
            raise ValueError("Too many snapshot files")
        total = 0
        frozen = dict(files)
        for path, content in frozen.items():
            _guest_path(path)
            if not isinstance(content, bytes):
                raise TypeError("Upload inputs must be frozen bytes")
            total += len(content)
            if total > 50 * 1024 * 1024:
                raise ValueError("Upload inputs exceed repository size limit")
        uploaded = {}
        for path, content in frozen.items():
            digest = hashlib.sha256(content).hexdigest()
            if digest in self._uploads:
                uploaded[path] = self._uploads[digest]
                continue
            if digest in self._upload_attempts:
                raise RemoteAdapterError("upload_uncertain_no_retry")
            self._upload_attempts.add(digest)
            status, data = self._request("POST", "files", content=content)
            record = self._object(data)
            try:
                file_id = _uuid(record.get("uuid"), "file uuid")
                if status != 201 or record.get("sha256") != digest or type(record.get("size")) is not int or record["size"] not in {-1, len(content)}:
                    raise ValueError("Invalid upload identity")
            except ValueError:
                raise RemoteAdapterError("invalid_upload_response") from None
            uploaded[path] = UploadedFile(file_id, digest, record["size"])
            self._uploads[digest] = uploaded[path]
        return uploaded

    @staticmethod
    def _payload(request: RemoteExecutionRequest) -> dict:
        _uuid(request.image_id, "image_id")
        if (not isinstance(request.executable, str) or not request.executable.startswith("/")
                or str(PurePosixPath(request.executable)) != request.executable
                or ".." in PurePosixPath(request.executable).parts
                or any(char.isspace() or ord(char) < 32 for char in request.executable)):
            raise ValueError("Executable must be a direct absolute executable path; shell expressions are unsupported")
        if len(request.args) > 128 or any(not isinstance(arg, str) or "\x00" in arg or len(arg.encode()) > 65_536 for arg in request.args):
            raise ValueError("Invalid executable arguments")
        if type(request.disposable) is not bool:
            raise ValueError("disposable must be explicit boolean")
        if type(request.timeout_seconds) is not int or not 1 <= request.timeout_seconds <= 30:
            raise ValueError("Snippet timeout must be between 1 and 30 seconds")
        if type(request.log_limit_bytes) is not int or not 1 <= request.log_limit_bytes <= MAX_LOG_BYTES:
            raise ValueError("Invalid per-stream output limit")
        if set(request.environment) - {"DOCDRIFT_INPUT"}:
            raise ValueError("Only declared nonsecret DOCDRIFT_INPUT may enter the guest")
        if any(not isinstance(value, str) or "\x00" in value or len(value.encode()) > 65_536 for value in request.environment.values()):
            raise ValueError("Invalid guest environment value")
        if len(request.files) > 2000:
            raise ValueError("Too many injected files")
        injected = {}
        for path, file in request.files.items():
            _guest_path(path)
            file_id = file.uuid if isinstance(file, UploadedFile) else file
            injected[path] = {"uuid": _uuid(file_id, "uploaded file"), "uid": 65534, "gid": 65534, "mode": "0644"}
        return {
            "image": request.image_id, "command": request.executable, "args": list(request.args),
            "shell": False, "env": {"PYTHONPATH": "/work/docdrift", "PYTHONDONTWRITEBYTECODE": "1",
                                      "PYTHONNOUSERSITE": "1", **request.environment},
            "preserve_env": False, "networking": {"enabled": False}, "disposable": request.disposable,
            "cwd": f"/work/docdrift/operations/{uuid.uuid4()}", "uid": 65534, "gid": 65534,
            "resources_limits": {"max_layer_bytes": MAX_ARTIFACT_BYTES},
            "stdin": {"value": "", "encoding": "base64", "close": True},
            "timeout": request.timeout_seconds, "truncate_output_at": request.log_limit_bytes, "files": injected,
        }

    def submit(self, request: RemoteExecutionRequest, on_accepted: Callable[[str], None], *, run_id: str, phase: str) -> str:
        self._require_mutations()
        if self.journal is None:
            raise ValueError("A durable submission journal is required before POST")
        payload = self._payload(request)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt = self.journal.begin(run_id, phase, digest)
        attempt_id = receipt["attempt_id"]
        try:
            status, data = self._request("POST", "instances", payload=payload)
            returned = self._object(data)
            operation_id = _uuid(returned.get("uuid"), "operation_id")
        except (RemoteAdapterError, ValueError) as error:
            code = error.code if isinstance(error, RemoteAdapterError) else "invalid_submission_response"
            # Definitive 4xx errors are recorded, never automatically retried.
            # 429 and every 5xx/transport/parse failure remain ambiguous.
            rejected = re.fullmatch(r"http_4\d\d", code) is not None and code not in {"http_408", "http_429"}
            if rejected:
                self.journal.rejected(attempt_id, code)
                raise RemoteAdapterError(code, attempt_id=attempt_id) from None
            self.journal.uncertain(attempt_id, code)
            raise UncertainSubmission(code, attempt_id=attempt_id) from None
        persistence_failed = False
        try:
            self.journal.accepted(attempt_id, operation_id)
        except Exception:
            # The remote UUID remains available even if the local commit failed.
            persistence_failed = True
        if persistence_failed:
            raise RemoteAdapterError("acceptance_persistence_failed", operation_id=operation_id, attempt_id=attempt_id)
        self._accepted[operation_id] = attempt_id
        self._expected_images[operation_id] = request.image_id
        self._expected_disposable[operation_id] = request.disposable
        callback_failed = False
        try:
            on_accepted(operation_id)
        except Exception:
            callback_failed = True
        if callback_failed:
            raise RemoteAdapterError("acceptance_callback_failed", operation_id=operation_id, attempt_id=attempt_id)
        if status != 201:
            # An unexpected successful HTTP status cannot justify throwing
            # away an otherwise valid returned remote operation identity.
            raise RemoteAdapterError("invalid_submission_response", operation_id=operation_id, attempt_id=attempt_id)
        return operation_id

    def recover(self, run_id: str, phase: str, *, expected_image_id: str | None = None,
                expected_disposable: bool | None = None) -> dict | None:
        if self.journal is None:
            raise ValueError("A durable submission journal is required for recovery")
        receipt = self.journal.lookup(run_id, phase)
        if receipt and receipt["operation_id"]:
            self._accepted[_uuid(receipt["operation_id"], "operation_id")] = receipt["attempt_id"]
            if expected_image_id is not None:
                self._expected_images[receipt["operation_id"]] = _uuid(expected_image_id, "expected_image_id")
            if expected_disposable is not None:
                if type(expected_disposable) is not bool:
                    raise ValueError("expected_disposable must be boolean")
                self._expected_disposable[receipt["operation_id"]] = expected_disposable
        return receipt

    @staticmethod
    def _stream(value: object, limit: int) -> tuple[str, bool, bool]:
        if not isinstance(value, dict) or not isinstance(value.get("value"), str) or type(value.get("truncated")) is not bool:
            return "", True, False
        try:
            encoding = value.get("encoding")
            if encoding == "base64":
                decoded = base64.b64decode(value["value"], validate=True)
            elif encoding == "ascii":
                decoded = value["value"].encode("ascii")
            else:
                return "", True, False
        except (ValueError, UnicodeError, binascii.Error):
            return "", True, False
        return decoded[:limit].decode("utf-8", errors="replace"), value["truncated"] or len(decoded) > limit, True

    def _result(self, operation_id: str, payload: dict, *, observation_timed_out: bool = False) -> RemoteResult:
        if payload.get("uuid") != operation_id or payload.get("kind") != "instance" or payload.get("status") not in _SERVICE_STATES:
            raise RemoteAdapterError("invalid_operation_response", operation_id=operation_id)
        service_state = payload["status"]
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise RemoteAdapterError("invalid_operation_response", operation_id=operation_id)
        result = metadata.get("result")
        result = result if isinstance(result, dict) else {}
        process = result.get("state")
        process = process if isinstance(process, dict) else {}
        raw_resources = result.get("resources")
        raw_resources = raw_resources if isinstance(raw_resources, dict) else {}
        resources = {key: value for key, value in raw_resources.items()
                     if isinstance(key, str) and re.fullmatch(r"[a-z_]{1,64}", key)
                     and type(value) in {int, float} and abs(value) <= 1e100 and math.isfinite(value)}
        if len(resources) > 128:
            raise RemoteAdapterError("resource_limit_exceeded", operation_id=operation_id)
        limit = metadata.get("truncate_output_at", MAX_LOG_BYTES)
        limit = min(limit, MAX_LOG_BYTES) if type(limit) is int and limit > 0 else MAX_LOG_BYTES
        stdout, stdout_truncated, stdout_valid = self._stream(result.get("stdout"), limit)
        stderr, stderr_truncated, stderr_valid = self._stream(result.get("stderr"), limit)
        exit_code = process.get("exit_code")
        signal = process.get("signal")
        process_types_valid = (type(exit_code) is int or exit_code is None) and (type(signal) is int or signal is None) and type(process.get("timed_out")) is bool
        if ((exit_code is not None and type(exit_code) is int and not -(2**31) <= exit_code < 2**31)
                or (signal is not None and type(signal) is int and not 0 <= signal < 2**31)):
            process_types_valid = False
        if not process_types_valid:
            exit_code = None
            signal = None
        timed_out = process.get("timed_out") is True
        duration = payload.get("duration")
        elapsed = float(duration) if type(duration) in {int, float} and 0 <= duration <= 1e100 and math.isfinite(duration) else None
        evidence_complete = (stdout_valid and stderr_valid and process_types_valid and (exit_code is not None or signal is not None))
        image_id = payload.get("image_uuid")
        result_image_id = payload.get("result_image_uuid")
        for name, value in (("image_id", image_id), ("result_image_id", result_image_id)):
            if value is not None:
                try:
                    _uuid(value, name)
                except ValueError:
                    raise RemoteAdapterError("invalid_operation_image", operation_id=operation_id) from None
        identity_valid = image_id is not None and (
            operation_id not in self._expected_images or image_id == self._expected_images[operation_id]
        )
        if metadata.get("image") is not None and metadata["image"] != image_id:
            identity_valid = False
        if not identity_valid:
            evidence_complete = False
        normalized = "pending"
        error_code = "observation_timeout" if observation_timed_out else None
        if service_state == "CANCELLED":
            normalized = "cancelled"
        elif service_state == "FAILED":
            normalized = "failed"
            error_code = "service_failed"
        elif timed_out:
            normalized = "timed_out"
        elif service_state == "SUCCESS":
            normalized = "completed" if evidence_complete else "incomplete"
            if not evidence_complete:
                error_code = "incomplete_execution_evidence"
        if (metadata.get("networking") != {"enabled": False} or metadata.get("shell") is not False
                or metadata.get("preserve_env") is not False or type(metadata.get("disposable")) is not bool
                or operation_id in self._expected_disposable and metadata.get("disposable") != self._expected_disposable[operation_id]
                or metadata.get("disposable") is True and result_image_id is not None):
            evidence_complete = False
            error_code = "execution_contract_unconfirmed"
            if normalized == "completed":
                normalized = "incomplete"
        if not identity_valid:
            error_code = "execution_image_unconfirmed"
        return RemoteResult(
            operation_id, image_id, result_image_id, normalized, service_state, exit_code, signal,
            timed_out, observation_timed_out, stdout, stderr, stdout_truncated, stderr_truncated,
            elapsed, evidence_complete, resources, error_code, self.offline_simulation,
        )

    def observe(self, operation_id: str, timeout_seconds: float = 30, *, poll_interval_seconds: float = 0.25) -> RemoteResult:
        _uuid(operation_id, "operation_id")
        if type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 300:
            raise ValueError("Invalid observation wait timeout")
        if type(poll_interval_seconds) not in {int, float} or not math.isfinite(poll_interval_seconds) or not 0 <= poll_interval_seconds <= 5:
            raise ValueError("Invalid polling interval")
        deadline = time.monotonic() + timeout_seconds
        for _ in range(1000):
            _, data = self._request("GET", f"operations/{operation_id}")
            payload = self._object(data)
            result = self._result(operation_id, payload)
            if result.service_state in _TERMINAL_STATES:
                if operation_id in self._accepted and self.journal is not None:
                    safe = {key: getattr(result, key) for key in (
                        "operation_id", "image_id", "result_image_id", "state", "service_state", "exit_code",
                        "signal", "timed_out", "observation_timed_out", "elapsed_seconds", "stdout_truncated",
                        "stderr_truncated", "evidence_complete", "resources", "error_code",
                    )}
                    if safe["elapsed_seconds"] is None:
                        safe.pop("elapsed_seconds")
                    self.journal.completed(self._accepted[operation_id], safe)
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._result(operation_id, payload, observation_timed_out=True)
            time.sleep(min(poll_interval_seconds, remaining))
        return self._result(operation_id, payload, observation_timed_out=True)

    def cancel(self, operation_id: str) -> None:
        self._require_mutations()
        _uuid(operation_id, "operation_id")
        if operation_id not in self._accepted:
            raise RemoteAdapterError("operation_not_owned", operation_id=operation_id)
        status, _ = self._request("DELETE", f"operations/{operation_id}")
        if status != 202:
            raise RemoteAdapterError("invalid_cancellation_response", operation_id=operation_id)
        # Acceptance of cancellation is not proof of a terminal operation.

    def download(self, operation_id: str, paths: tuple[str, ...] = ()) -> dict[str, bytes]:
        _uuid(operation_id, "operation_id")
        if len(paths) > 2000 or len(set(paths)) != len(paths):
            raise ValueError("Invalid artifact path inventory")
        for path in paths:
            _guest_path(path)
        result = self.observe(operation_id, timeout_seconds=0)
        if not paths:
            return {}
        if result.service_state != "SUCCESS" or result.result_image_id is None:
            raise RemoteAdapterError("artifact_image_unavailable", operation_id=operation_id)
        artifacts = {}
        remaining = MAX_ARTIFACT_BYTES
        for path in paths:
            _, data = self._request("GET", f"inspect/{result.result_image_id}/download", params={"path": path}, limit=remaining)
            artifacts[path] = data
            remaining -= len(data)
        return artifacts
