"""Exercise complete HTTP requests without binding sockets or calling providers."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from docdrift.judge_ui import HTML, JS
from docdrift.judge_web import MAX_ARTIFACT_BYTES, handler_factory, serve


ORIGIN = "https://judge.example.test"
PASSWORD_HASH = hashlib.sha256(b"private-test-password").hexdigest()
JOB_ID = "a" * 32
REQUEST_KEY = "01234567-89ab-cdef-0123-456789abcdef"


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.admitted: list[str] = []
        self.jobs: dict[str, dict] = {}
        self.artifacts: dict[tuple[str, str], Path] = {}
        self.admission_error: str | None = None

    def summary(self) -> dict:
        self.calls.append("summary")
        return {"live_ready": False, "attempts_limit": 20, "attempts_remaining": 20}

    def list_jobs(self) -> list[dict]:
        self.calls.append("list_jobs")
        return list(self.jobs.values())

    def get(self, job_id: str) -> dict | None:
        self.calls.append("get")
        return self.jobs.get(job_id)

    def admit(self, request_key: str) -> dict:
        if self.admission_error:
            raise ValueError(self.admission_error)
        self.admitted.append(request_key)
        return self.jobs.setdefault(JOB_ID, {"id": JOB_ID, "status": "queued", "private_internal": "not public"})

    def job_artifact(self, job_id: str, name: str) -> Path | None:
        self.calls.append("job_artifact")
        return self.artifacts.get((job_id, name))


class FakeSocket:
    def __init__(self, request: bytes) -> None:
        self.input = io.BytesIO(request)
        self.output = bytearray()
        self.timeout: float | None = None

    def makefile(self, *args, **kwargs):
        return self.input

    def sendall(self, data: bytes) -> None:
        self.output.extend(data)

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout


def auth(value: bytes = b"judge:private-test-password") -> str:
    return "Basic " + base64.b64encode(value).decode()


def request(
    store: FakeStore, path: str = "/", *, method: str = "GET",
    authenticated: bool = True, body: bytes = b"{}", headers: list[tuple[str, str]] | None = None,
    auto_headers: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    supplied = list(headers or [])
    if authenticated and not any(key.lower() == "authorization" for key, _ in supplied):
        supplied.append(("Authorization", auth()))
    if method == "POST" and auto_headers:
        default = {
            "Origin": ORIGIN, "X-DocDrift-Request": "1", "Content-Length": str(len(body)),
            "Content-Type": "application/json", "Idempotency-Key": REQUEST_KEY,
        }
        present = {key.lower() for key, _ in supplied}
        supplied.extend((key, value) for key, value in default.items() if key.lower() not in present)
    raw = f"{method} {path} HTTP/1.1\r\nHost: judge.example.test\r\n".encode()
    raw += "".join(f"{key}: {value}\r\n" for key, value in supplied).encode()
    sock = FakeSocket(raw + b"\r\n" + (body if method == "POST" else b""))
    handler_factory(store, PASSWORD_HASH, ORIGIN)(sock, ("127.0.0.1", 1234), SimpleNamespace())
    assert sock.timeout == 10
    head, result = bytes(sock.output).split(b"\r\n\r\n", 1)
    lines = head.decode().split("\r\n")
    status = int(lines[0].split()[1])
    response_headers = dict(line.split(": ", 1) for line in lines[1:])
    return status, response_headers, result


def test_health_is_generic_unauthenticated_and_not_store_readiness():
    store = FakeStore()
    status, headers, body = request(store, "/healthz", authenticated=False)
    assert status == 200
    assert json.loads(body) == {"ready": True}
    assert store.calls == []
    assert headers["Cache-Control"] == "no-store"
    assert "X-Powered-By" not in headers


@pytest.mark.parametrize("path", ["/", "/api/status", "/app.js", "/style.css", f"/api/jobs/{JOB_ID}", f"/jobs/{JOB_ID}/review.html", "/saved/review.html", "/saved/evidence.zip", "/missing"])
def test_private_routes_require_authentication(path):
    store = FakeStore()
    status, headers, body = request(store, path, authenticated=False)
    assert status == 401
    assert headers["WWW-Authenticate"].startswith("Basic ")
    assert json.loads(body)["error"] == "authentication_required"
    assert store.calls == []


@pytest.mark.parametrize("value", ["", "Bearer something", "Basic !!!", "Basic amVkZ2U=", auth(b"judge:wrong"), auth(b"other:private-test-password"), auth(b"judge:private-test-password:extra")])
def test_malformed_or_incorrect_auth_is_denied(value):
    store = FakeStore()
    assert request(store, headers=[("Authorization", value)])[0] == 401
    assert store.calls == []


def test_duplicate_authorization_is_denied():
    assert request(FakeStore(), headers=[("Authorization", auth()), ("Authorization", auth())])[0] == 401


def test_ui_assets_and_security_headers():
    store = FakeStore()
    for path in ("/", "/app.js", "/style.css"):
        status, headers, body = request(store, path)
        assert status == 200 and body
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in headers["Content-Security-Policy"]
        assert not any(key.lower().startswith("access-control-") for key in headers)
    assert "innerHTML" not in JS
    assert "textContent" in JS
    assert "crypto.randomUUID()" in JS
    assert "disabled" in HTML
    assert "owned development fixture" in HTML
    assert "Saved demonstration · Oct 21" in HTML
    assert 'href="/saved/review.html"' in HTML
    assert 'href="/saved/evidence.zip"' in HTML


def test_status_and_job_filter_internal_details():
    store = FakeStore()
    store.jobs[JOB_ID] = {"id": JOB_ID, "status": "queued", "private_internal": "hidden"}
    status, _, body = request(store, "/api/status")
    assert status == 200
    assert json.loads(body) == {"summary": {"live_ready": False, "attempts_limit": 20, "attempts_remaining": 20}, "jobs": [{"id": JOB_ID, "status": "queued"}]}
    assert json.loads(request(store, f"/api/jobs/{JOB_ID}")[2]) == {"id": JOB_ID, "status": "queued"}
    assert request(store, f"/api/jobs/{'b' * 32}")[0] == 404


def test_fixed_admission_canonicalizes_request_key_and_filters_response():
    store = FakeStore()
    status, _, body = request(store, "/api/jobs", method="POST")
    assert status == 202
    assert store.admitted == [REQUEST_KEY.replace("-", "")]
    assert json.loads(body) == {"id": JOB_ID, "status": "queued"}


@pytest.mark.parametrize("headers", [
    [("Origin", "https://different.example.test")], [("Origin", "null")],
    [("Origin", ORIGIN + "/")], [("Origin", ORIGIN), ("Origin", ORIGIN)],
    [("X-DocDrift-Request", "0")], [("X-DocDrift-Request", "1"), ("X-DocDrift-Request", "1")],
])
def test_mutations_require_exact_single_origin_and_custom_header(headers):
    store = FakeStore()
    assert request(store, "/api/jobs", method="POST", headers=headers)[0] == 403
    assert store.admitted == []


def test_post_missing_origin_is_denied_even_with_password():
    store = FakeStore()
    assert request(store, "/api/jobs", method="POST", auto_headers=False)[0] == 403
    assert store.admitted == []


@pytest.mark.parametrize(("headers", "status"), [
    ([("Content-Length", "1025")], 413), ([("Content-Length", "-1")], 400),
    ([("Content-Length", "2"), ("Content-Length", "2")], 400),
    ([("Transfer-Encoding", "chunked")], 400),
    ([("Content-Type", "text/plain")], 415),
    ([("Content-Type", "application/json"), ("Content-Type", "application/json")], 415),
    ([("Idempotency-Key", "../bad")], 400), ([("Idempotency-Key", "a" * 33)], 400),
    ([("Idempotency-Key", REQUEST_KEY), ("Idempotency-Key", REQUEST_KEY)], 400),
    ([("Content-Length", "3")], 400),
])
def test_invalid_body_metadata_never_admits(headers, status):
    store = FakeStore()
    assert request(store, "/api/jobs", method="POST", headers=headers)[0] == status
    assert store.admitted == []


@pytest.mark.parametrize("body", [b"", b"[ ]", b"null", b"{\"prompt\":\"do something\"}", b"{\"repository\":\"https://example.test\"}", b"{", b"\xff"])
def test_only_empty_json_object_is_accepted(body):
    store = FakeStore()
    assert request(store, "/api/jobs", method="POST", body=body)[0] == 400
    assert store.admitted == []


@pytest.mark.parametrize(("code", "status"), [
    ("paused", 503), ("expired", 410), ("allowance_exhausted", 429),
    ("budget_exhausted", 429), ("queue_full", 429), ("funding_unconfirmed", 503),
    ("idempotency_conflict", 409), ("invalid_request_key", 400),
    ("request_key_conflict", 409), ("judging_expired", 410),
    ("admission_paused", 503), ("activation_required", 503),
    ("worker_unavailable", 503), ("attempt_limit_reached", 429),
    ("unsupported_fixed_case", 403), ("judge_authorization_changed", 503),
])
def test_admission_errors_are_bounded_public_codes(code, status):
    store = FakeStore()
    store.admission_error = code
    actual, _, body = request(store, "/api/jobs", method="POST")
    assert actual == status
    assert json.loads(body)["error"] == code


def test_unknown_store_error_does_not_leak_exception():
    store = FakeStore()
    store.admission_error = "private path or credential text"
    _, _, body = request(store, "/api/jobs", method="POST")
    assert b"private path" not in body
    assert json.loads(body)["error"] == "not_ready"


@pytest.mark.parametrize("path", ["/?password=sensitive", "/api/status?key=secret", "/healthz?credential=secret", "https://judge.example.test/api/status", f"/jobs/{JOB_ID}/../evidence.zip", f"/jobs/{JOB_ID}/%2e%2e/evidence.zip"])
def test_query_credentials_absolute_urls_and_traversal_are_never_routed(path):
    store = FakeStore()
    assert request(store, path)[0] in {400, 404}
    assert store.calls == []


def test_artifacts_only_expose_completed_public_results(tmp_path):
    store = FakeStore()
    review = tmp_path / "review.html"
    review.write_text("<!doctype html><p>Sanitized review</p>")
    archive = tmp_path / "evidence.zip"
    archive.write_bytes(b"synthetic test archive")
    store.artifacts[(JOB_ID, "review.html")] = review
    store.artifacts[(JOB_ID, "evidence.zip")] = archive
    store.jobs[JOB_ID] = {"id": JOB_ID, "status": "running", "has_artifacts": True}
    assert request(store, f"/jobs/{JOB_ID}/review.html")[0] == 404
    store.jobs[JOB_ID]["status"] = "completed"
    status, headers, body = request(store, f"/jobs/{JOB_ID}/review.html")
    assert status == 200 and body == review.read_bytes()
    assert "script-src" not in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    status, headers, body = request(store, f"/jobs/{JOB_ID}/evidence.zip")
    assert status == 200 and body == archive.read_bytes()
    assert headers["Content-Disposition"].startswith("attachment;")
    assert request(store, f"/jobs/{JOB_ID}/other.json")[0] == 404


def test_symlink_missing_and_oversized_artifacts_are_rejected(tmp_path):
    store = FakeStore()
    store.jobs[JOB_ID] = {"id": JOB_ID, "status": "completed", "has_artifacts": True}
    real = tmp_path / "real.html"
    real.write_text("not served through symlink")
    link = tmp_path / "review.html"
    link.symlink_to(real)
    store.artifacts[(JOB_ID, "review.html")] = link
    assert request(store, f"/jobs/{JOB_ID}/review.html")[0] == 404
    store.artifacts[(JOB_ID, "review.html")] = tmp_path / "missing"
    assert request(store, f"/jobs/{JOB_ID}/review.html")[0] == 404
    large = tmp_path / "large.zip"
    with large.open("wb") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES + 1)
    store.artifacts[(JOB_ID, "evidence.zip")] = large
    assert request(store, f"/jobs/{JOB_ID}/evidence.zip")[0] == 404


def test_fixed_saved_artifacts_work_without_active_worker_or_admission(tmp_path, monkeypatch):
    import docdrift.judge_web as web

    monkeypatch.setattr(web, "SAVED_ROOT", tmp_path)
    (tmp_path / "review.html").write_text("<p>Constructed recorded review.</p>")
    (tmp_path / "evidence.zip").write_bytes(b"constructed recorded archive")
    store = FakeStore()
    store.admission_error = "judging_expired"
    assert request(store, "/api/jobs", method="POST")[0] == 410
    for name in ("review.html", "evidence.zip"):
        status, headers, body = request(store, "/saved/" + name)
        assert status == 200 and body == (tmp_path / name).read_bytes()
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        if name == "evidence.zip":
            assert headers["Content-Disposition"] == 'attachment; filename="docdrift-saved-oct21-evidence.zip"'
    assert store.calls == []
    assert store.admitted == []


@pytest.mark.parametrize("path", [
    "/saved/", "/saved/report.json", "/saved/manifest.json", "/saved/index.html",
    "/saved/../review.html", "/saved/%2e%2e/evidence.zip", "/saved/sub/review.html",
    "/saved/review.html?password=secret", "/saved//review.html",
])
def test_saved_routes_never_allow_other_files_or_traversal(path):
    store = FakeStore()
    assert request(store, path)[0] in {400, 404}
    assert store.calls == []


def test_saved_artifact_missing_and_symlink_fail_closed(tmp_path, monkeypatch):
    import docdrift.judge_web as web

    monkeypatch.setattr(web, "SAVED_ROOT", tmp_path)
    store = FakeStore()
    assert request(store, "/saved/review.html")[0] == 404
    target = tmp_path / "private.html"
    target.write_text("must not expose symlink target")
    (tmp_path / "review.html").symlink_to(target)
    assert request(store, "/saved/review.html")[0] == 404
    assert store.calls == []


@pytest.mark.parametrize("method", ["HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_other_http_methods_are_unavailable(method):
    store = FakeStore()
    assert request(store, method=method)[0] == 405
    assert store.admitted == []


@pytest.mark.parametrize("origin", ["https://judge.example.test/", "http://public.example.test", "ftp://example.test", "https://user:pass@example.test", "https://example.test?q=1", "https://example.test/#x", "https://example.test:bad", "https://example.test:0"])
def test_configuration_requires_clean_secure_origin(origin):
    with pytest.raises(ValueError):
        handler_factory(FakeStore(), PASSWORD_HASH, origin)


@pytest.mark.parametrize("digest", ["", "secret-password", "g" * 64, "a" * 63])
def test_raw_or_invalid_password_configuration_is_rejected(digest):
    with pytest.raises(ValueError):
        handler_factory(FakeStore(), digest, ORIGIN)


@pytest.mark.parametrize(("host", "port"), [("0.0.0.0", 8765), ("127.0.0.1", 80), ("127.0.0.1", 443), ("127.0.0.1", 8501)])
def test_serve_rejects_exposed_binding_and_protected_ports(host, port):
    with pytest.raises(ValueError):
        serve(FakeStore(), password_sha256=PASSWORD_HASH, public_origin=ORIGIN, host=host, port=port)


def test_access_logging_is_disabled(capsys):
    request(FakeStore(), "/?password=must-not-log", headers=[("Authorization", "Bearer must-not-log")])
    assert capsys.readouterr() == ("", "")


def test_http_lifecycle_with_durable_store_and_synthetic_artifacts(tmp_path):
    from docdrift.judge_store import IMAGE_ID, LIMITS, MODEL, PROJECT_ID, JudgeStore

    state_root = tmp_path / "judge"
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps({
        "kind": "docdrift_judge_authorization", "project_id": PROJECT_ID,
        "image_id": IMAGE_ID, "model": MODEL, "limits": LIMITS,
        "user_authorized_bounded_runs": True, "funding_intent": "granted_credits_only",
        "billing_coverage": "unverified", "state_root": str(state_root.resolve()),
        "expires_at_utc": "2026-12-16T00:00:00+00:00",
    }))
    authorization.chmod(0o600)
    clock = [datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp()]
    store = JudgeStore(state_root, authorization, clock=lambda: clock[0])
    status, _, body = request(store, "/api/jobs", method="POST")
    assert status == 503 and json.loads(body)["error"] == "activation_required"

    # Manufactured provider-shaped metadata activates only this temporary store;
    # its synthetic=False field is a fixture value, not a live execution claim.
    store.reserve_capability()
    store.record_capability({
        "kind": "docdrift_judge_sandbox_capability", "status": "verified",
        "project_id": PROJECT_ID, "image_id": IMAGE_ID,
        "operation_id": "12345678-1234-1234-1234-123456789abc",
        "python": [3, 12], "euid": 65534, "interfaces": ["lo"], "synthetic": False,
    })
    store.heartbeat()
    status, _, body = request(store, "/api/jobs", method="POST")
    job = json.loads(body)
    assert status == 202 and job["status"] == "queued"
    assert json.loads(request(store, "/api/jobs", method="POST")[2])["id"] == job["id"]
    assert store.summary()["attempts_used"] == 1
    assert json.loads(request(store, "/api/status")[2])["summary"]["attempts_remaining"] == 15

    claim = store.claim()
    directory = state_root / "jobs" / job["id"] / "public"
    directory.mkdir(parents=True)
    (directory / "review.html").write_text("<p>Constructed test review, no provider execution.</p>")
    store.finish(job["id"], claim["worker_token"], result={"outcome": "constructed_test_result", "has_artifacts": True})
    assert request(store, f"/jobs/{job['id']}/review.html")[0] == 200

    clock[0] = store.expires
    status, _, body = request(store, "/api/jobs", method="POST", headers=[("Idempotency-Key", "b" * 32)])
    assert status == 410 and json.loads(body)["error"] == "judging_expired"
    assert request(store, f"/jobs/{job['id']}/review.html")[0] == 200
    assert json.loads(request(store, "/api/jobs", method="POST")[2])["id"] == job["id"]
    assert store.summary()["attempts_used"] == 1
