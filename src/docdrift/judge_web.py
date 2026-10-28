"""Private HTTP controller for the fixed-fixture judging queue.

The controller delegates durable admission to the store; it never runs repairs
or reads provider credentials. Put HTTPS in front of the loopback-only server.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from .judge_ui import CSS, HTML, JS


MAX_BODY_BYTES = 1024
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
SAVED_ROOT = Path(__file__).resolve().parents[2] / "docs/demo/f6-sandbox"
_JOB_ID = r"[a-f0-9]{32}"
_REQUEST_KEY = re.compile(r"(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})\Z")
_JOB_FIELDS = (
    "id", "status", "created_at", "updated_at", "outcome", "has_artifacts",
    "error_code", "model_calls", "guest_operations",
)
_MESSAGES = {
    "paused": "Fresh runs are paused by the operator.",
    "expired": "The judging run window has ended.",
    "allowance_exhausted": "The shared run allowance has been used.",
    "budget_exhausted": "The shared run allowance has been used.",
    "queue_full": "The queue is full. Please wait for an active attempt to finish.",
    "funding_unconfirmed": "Fresh runs require confirmed credit coverage.",
    "not_ready": "Fresh runs have not been activated yet.",
    "idempotency_conflict": "This request ID belongs to a different request.",
    "invalid_request_key": "A fresh request ID is required.",
    "request_key_conflict": "This request ID belongs to a different request.",
    "judging_expired": "The judging run window has ended.",
    "admission_paused": "Fresh runs are paused for operator review.",
    "activation_required": "Fresh runs have not been activated yet.",
    "worker_unavailable": "The worker is unavailable. Please try again later.",
    "attempt_limit_reached": "The shared run allowance has been used.",
    "unsupported_fixed_case": "Only the fixed documentation example is available.",
    "judge_authorization_changed": "The operator must review the deployment authorization.",
}


class JudgeStoreProtocol(Protocol):
    def summary(self) -> dict[str, Any]: ...
    def list_jobs(self) -> list[dict[str, Any]]: ...
    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def admit(self, request_key: str) -> dict[str, Any]: ...
    def job_artifact(self, job_id: str, name: str) -> Path | None: ...


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: job[key] for key in _JOB_FIELDS if key in job}


def _check_config(password_sha256: str, public_origin: str) -> None:
    if not re.fullmatch(r"[a-fA-F0-9]{64}", password_sha256):
        raise ValueError("judge password must be a SHA-256 hexadecimal digest")
    try:
        origin = urlsplit(public_origin)
        port = origin.port
    except ValueError as exc:
        raise ValueError("public_origin must be an HTTP(S) origin") from exc
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or origin.path
        or origin.query
        or origin.fragment
        or public_origin != f"{origin.scheme}://{origin.netloc}"
        or port == 0
    ):
        raise ValueError("public_origin must be an HTTP(S) origin without a path")
    if origin.scheme == "http" and origin.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("a public judge origin requires HTTPS")


def handler_factory(
    store: JudgeStoreProtocol,
    password_sha256: str,
    public_origin: str,
) -> type[BaseHTTPRequestHandler]:
    """Build an authenticated handler without binding a socket or reading env."""
    _check_config(password_sha256, public_origin)
    password_digest = password_sha256.lower()

    class JudgeHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "DocDrift"
        sys_version = ""

        def setup(self) -> None:
            self.request.settimeout(10)
            super().setup()

        def log_message(self, format: str, *args: Any) -> None:
            # Request paths and supplied headers must never enter access logs.
            return

        def _send(
            self, status: int, body: bytes, content_type: str,
            *, headers: dict[str, str] | None = None, artifact_html: bool = False,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            csp = (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
                if artifact_html else
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                "form-action 'self'; frame-ancestors 'none'"
            )
            self.send_header("Content-Security-Policy", csp)
            self.send_header("Connection", "close")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            self.close_connection = True

        def _json(self, status: int, value: dict[str, Any], **kwargs: Any) -> None:
            self._send(
                status, json.dumps(value, ensure_ascii=True, allow_nan=False).encode(),
                "application/json; charset=utf-8", **kwargs,
            )

        def _error(self, status: int, code: str, **kwargs: Any) -> None:
            self._json(status, {"error": code, "message": _MESSAGES.get(code, code.replace("_", " "))}, **kwargs)

        def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
            # BaseHTTPRequestHandler's HTML error reflects parser input; keep it fixed.
            self._error(code, "invalid_request")

        def _authenticated(self) -> bool:
            values = self.headers.get_all("Authorization", [])
            valid = False
            if len(values) == 1 and len(values[0]) <= 2048:
                try:
                    scheme, encoded = values[0].split(" ", 1)
                    if scheme.lower() != "basic":
                        raise ValueError("unsupported authentication")
                    decoded = base64.b64decode(encoded, validate=True)
                    username, separator, password = decoded.partition(b":")
                    if not separator:
                        raise ValueError("missing password")
                    username_ok = hmac.compare_digest(username, b"judge")
                    password_ok = hmac.compare_digest(hashlib.sha256(password).hexdigest(), password_digest)
                    valid = username_ok and password_ok
                except (ValueError, binascii.Error):
                    pass
            if not valid:
                self._error(401, "authentication_required", headers={"WWW-Authenticate": 'Basic realm="DocDrift judge", charset="UTF-8"'})
            return valid

        def _path(self) -> str | None:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                self._error(400, "invalid_path")
                return None
            return parsed.path

        def do_GET(self) -> None:
            try:
                self._get()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except Exception:
                self._error(500, "controller_unavailable")

        def _get(self) -> None:
            path = self._path()
            if path is None:
                return
            if path == "/healthz":
                self._json(200, {"ready": True})
                return
            if not self._authenticated():
                return
            assets = {"/": (HTML, "text/html; charset=utf-8"), "/app.js": (JS, "text/javascript; charset=utf-8"), "/style.css": (CSS, "text/css; charset=utf-8")}
            if path in assets:
                body, kind = assets[path]
                self._send(200, body.encode(), kind)
            elif path == "/api/status":
                self._json(200, {"summary": store.summary(), "jobs": [_public_job(job) for job in store.list_jobs()]})
            elif match := re.fullmatch(rf"/api/jobs/({_JOB_ID})", path):
                job = store.get(match.group(1))
                if job is None:
                    self._error(404, "job_not_found")
                else:
                    self._json(200, _public_job(job))
            elif match := re.fullmatch(rf"/jobs/({_JOB_ID})/(review\.html|evidence\.zip)", path):
                self._artifact(match.group(1), match.group(2))
            elif match := re.fullmatch(r"/saved/(review\.html|evidence\.zip)", path):
                self._serve_artifact(
                    SAVED_ROOT / match.group(1), match.group(1),
                    archive_filename="docdrift-saved-oct21-evidence.zip",
                )
            else:
                self._error(404, "not_found")

        def _artifact(self, job_id: str, name: str) -> None:
            job = store.get(job_id)
            if job is None or job.get("status") != "completed" or job.get("has_artifacts") is not True:
                self._error(404, "artifact_not_available")
                return
            path = store.job_artifact(job_id, name)
            if path is None:
                self._error(404, "artifact_not_available")
                return
            self._serve_artifact(path, name, archive_filename=f"docdrift-{job_id}-evidence.zip")

        def _serve_artifact(self, path: Path, name: str, *, archive_filename: str) -> None:
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream:
                    metadata = os.fstat(stream.fileno())
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ARTIFACT_BYTES:
                        raise ValueError("invalid artifact")
                    body = stream.read(MAX_ARTIFACT_BYTES + 1)
                    if len(body) > MAX_ARTIFACT_BYTES:
                        raise ValueError("oversized artifact")
            except (OSError, ValueError):
                self._error(404, "artifact_not_available")
                return
            if name == "review.html":
                from .review import refresh_review_navigation
                body = refresh_review_navigation(body.decode('utf-8')).encode('utf-8')
                self._send(200, body, "text/html; charset=utf-8", artifact_html=True)
            else:
                self._send(200, body, "application/zip", headers={"Content-Disposition": f'attachment; filename="{archive_filename}"'})

        def do_POST(self) -> None:
            try:
                self._post()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except Exception:
                self._error(500, "controller_unavailable")

        def _post(self) -> None:
            path = self._path()
            if path is None or not self._authenticated():
                return
            if path != "/api/jobs":
                self._error(404, "not_found")
                return
            if self.headers.get_all("Origin", []) != [public_origin] or self.headers.get_all("X-DocDrift-Request", []) != ["1"]:
                self._error(403, "same_origin_required")
                return
            if self.headers.get_all("Transfer-Encoding", []):
                self._error(400, "invalid_body")
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,5}", lengths[0]):
                self._error(400, "invalid_body")
                return
            length = int(lengths[0])
            if length > MAX_BODY_BYTES:
                self._error(413, "body_too_large")
                return
            types = self.headers.get_all("Content-Type", [])
            if len(types) != 1 or types[0].lower() not in {"application/json", "application/json; charset=utf-8"}:
                self._error(415, "json_required")
                return
            keys = self.headers.get_all("Idempotency-Key", [])
            if len(keys) != 1 or not _REQUEST_KEY.fullmatch(keys[0]):
                self._error(400, "idempotency_key_required")
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self._error(400, "invalid_body")
                return
            try:
                value = json.loads(body)
            except (ValueError, UnicodeError):
                self._error(400, "invalid_body")
                return
            if not isinstance(value, dict) or value:
                self._error(400, "fixed_fixture_only")
                return
            try:
                job = store.admit(UUID(keys[0]).hex)
            except ValueError as exc:
                code = str(exc)
                if code not in _MESSAGES:
                    code = "not_ready"
                if code in {"expired", "judging_expired"}:
                    status = 410
                elif code in {"allowance_exhausted", "budget_exhausted", "attempt_limit_reached", "queue_full"}:
                    status = 429
                elif code in {"idempotency_conflict", "request_key_conflict"}:
                    status = 409
                elif code == "invalid_request_key":
                    status = 400
                elif code == "unsupported_fixed_case":
                    status = 403
                else:
                    status = 503
                self._error(status, code)
                return
            self._json(202, _public_job(job))

        def _unsupported(self) -> None:
            if self._authenticated():
                self._error(405, "method_not_allowed", headers={"Allow": "GET, POST"})

        do_HEAD = _unsupported
        do_PUT = _unsupported
        do_DELETE = _unsupported
        do_PATCH = _unsupported
        do_OPTIONS = _unsupported

    return JudgeHandler


class _BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def serve(
    store: JudgeStoreProtocol, *, password_sha256: str, public_origin: str,
    host: str = "127.0.0.1", port: int = 8765,
) -> None:
    """Serve on loopback only; a separate HTTPS proxy supplies public access."""
    if host != "127.0.0.1":
        raise ValueError("judge controller must bind to 127.0.0.1")
    if not 1024 <= port <= 65535 or port == 8501:
        raise ValueError("judge controller requires an unreserved high port")
    handler = handler_factory(store, password_sha256, public_origin)
    with _BoundedHTTPServer((host, port), handler) as server:
        server.serve_forever(poll_interval=0.5)
