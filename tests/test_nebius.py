"""Synthetic documented-shape responses; these are not live provider recordings."""

import base64
import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from docdrift.nebius import (
    BASE_URL, MAX_ARTIFACT_BYTES, MAX_RESPONSE_BYTES, NebiusSandboxAdapter,
    RemoteAdapterError, RemoteExecutionRequest, RemoteMutationsDisabled, UncertainSubmission,
)
from docdrift.remote_journal import SubmissionConflict, SubmissionJournal


FIXTURES = Path(__file__).parent / "fixtures" / "nebius"
IMAGE = "11111111-1111-4111-8111-111111111111"
OPERATION = "22222222-2222-4222-8222-222222222222"
RESULT_IMAGE = "33333333-3333-4333-8333-333333333333"
FILE = "66666666-6666-4666-8666-666666666666"
FAKE_SECRET = "synthetic-not-a-real-api-key"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def request(**changes):
    arguments = {"image_id": IMAGE, "executable": "/usr/local/bin/python",
                 "args": ("-B", "/work/docdrift/example.py"), "environment": {"DOCDRIFT_INPUT": "[]"},
                 "files": {"/work/docdrift/example.py": FILE}, "disposable": True}
    arguments.update(changes)
    return RemoteExecutionRequest(**arguments)


def adapter(tmp_path, handler, *, offline=True):
    return NebiusSandboxAdapter(FAKE_SECRET, "synthetic-project", transport=httpx.MockTransport(handler),
                                offline_simulation=offline, journal=SubmissionJournal(tmp_path))


def test_response_manifest_is_explicitly_synthetic_and_frozen():
    manifest = fixture("manifest.json")
    assert manifest["provenance"] == "synthetic_documented_shape_not_a_live_recording"
    assert set(manifest["files"]) == {path.name for path in FIXTURES.glob("*.json") if path.name != "manifest.json"}
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("method", ["submit", "prepare", "cancel"])
def test_default_mode_blocks_every_mutation_before_transport(tmp_path, method):
    calls = []
    with adapter(tmp_path, lambda req: calls.append(req), offline=False) as client:
        with pytest.raises(RemoteMutationsDisabled):
            if method == "submit":
                client.submit(request(), lambda operation: None, run_id="run", phase="baseline")
            elif method == "prepare":
                client.prepare({"/work/docdrift/example.py": b"print('ok')"})
            else:
                client.cancel(OPERATION)
    assert calls == []
    assert SubmissionJournal(tmp_path).for_run("run") == []


def test_simulation_requires_explicit_mock_transport():
    with pytest.raises(ValueError, match="MockTransport"):
        NebiusSandboxAdapter(FAKE_SECRET, "project", offline_simulation=True)


def test_read_only_preflight_does_not_execute_probe_or_export_credentials(tmp_path):
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        assert req.headers["Authorization"] == f"Bearer {FAKE_SECRET}"
        assert req.headers["Project"] == "synthetic-project"
        assert req.headers["Accept-Encoding"] == "identity"
        return httpx.Response(200, json=fixture("whoami.json" if req.url.path.endswith("whoami") else "image.json"))

    with adapter(tmp_path, handler) as client:
        information = client.preflight(IMAGE)
    assert calls == [("GET", "/sandboxes/v1/whoami"), ("GET", f"/sandboxes/v1/inspect/{IMAGE}/")]
    assert information["synthetic"] and not information["live_mutations_enabled"]
    assert not information["credit_coverage_confirmed"] and not information["network_isolation_tested"]
    assert information["personal_spend_limit"] == 0
    assert FAKE_SECRET not in repr(information)
    assert "token_uuid" not in information


def test_journal_is_committed_before_post_and_id_before_callback(tmp_path):
    journal = SubmissionJournal(tmp_path)
    calls = []

    def handler(req):
        calls.append(req)
        assert journal.for_run("run")[0]["state"] == "submitting"
        payload = json.loads(req.content)
        assert payload["image"] == IMAGE and payload["command"] == "/usr/local/bin/python"
        assert payload["shell"] is False and payload["preserve_env"] is False
        assert payload["networking"] == {"enabled": False} and payload["disposable"] is True
        assert payload["timeout"] == 30 and payload["truncate_output_at"] == 262144
        assert payload["stdin"]["close"] is True
        assert payload["uid"] == payload["gid"] == 65534
        assert payload["resources_limits"]["max_layer_bytes"] == MAX_ARTIFACT_BYTES
        assert payload["cwd"].startswith("/work/docdrift/operations/")
        assert set(payload["env"]) == {"DOCDRIFT_INPUT", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE"}
        assert payload["files"]["/work/docdrift/example.py"] == {"uuid": FILE, "uid": 65534, "gid": 65534, "mode": "0644"}
        assert FAKE_SECRET not in req.content.decode()
        return httpx.Response(201, json={**payload, "uuid": OPERATION})

    def callback(operation_id):
        assert operation_id == OPERATION
        receipt = journal.for_run("run")[0]
        assert receipt["state"] == "accepted" and receipt["operation_id"] == OPERATION

    with adapter(tmp_path, handler) as client:
        assert client.submit(request(), callback, run_id="run", phase="baseline") == OPERATION
    assert len(calls) == 1
    assert calls[0].url == BASE_URL + "instances"


def test_callback_failure_recovery_observes_existing_id_without_second_post(tmp_path):
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        return httpx.Response(201, json=fixture("accepted.json")) if req.method == "POST" else httpx.Response(200, json=fixture("success.json"))

    def callback(operation):
        raise RuntimeError(FAKE_SECRET)

    with adapter(tmp_path, handler) as client:
        with pytest.raises(RemoteAdapterError) as raised:
            client.submit(request(), callback, run_id="run", phase="baseline")
        assert raised.value.operation_id == OPERATION
        assert str(raised.value) == "acceptance_callback_failed" and FAKE_SECRET not in str(raised.value)
        assert raised.value.__context__ is None
    with adapter(tmp_path, handler) as recovered:
        receipt = recovered.recover("run", "baseline", expected_image_id=IMAGE, expected_disposable=True)
        assert receipt["state"] == "accepted"
        result = recovered.observe(receipt["operation_id"])
        assert result.execution_passed and result.synthetic
    assert len([call for call in calls if call[0] == "POST"]) == 1
    persisted = SubmissionJournal(tmp_path).for_run("run")[0]
    assert persisted["state"] == "completed"
    assert "stdout" not in persisted["result_metadata"] and "env" not in persisted["result_metadata"]
    assert FAKE_SECRET not in repr(persisted)


@pytest.mark.parametrize("status, expected", [(400, "rejected"), (401, "rejected"), (403, "rejected"), (408, "uncertain"), (429, "uncertain"), (500, "uncertain"), (503, "uncertain")])
def test_http_failures_never_retry_post_even_after_new_adapter(tmp_path, status, expected):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": FAKE_SECRET})

    with adapter(tmp_path, handler) as client:
        with pytest.raises(RemoteAdapterError) as raised:
            client.submit(request(), lambda op: None, run_id="run", phase="baseline")
        assert str(raised.value) == f"http_{status}"
    assert SubmissionJournal(tmp_path).for_run("run")[0]["state"] == expected
    with adapter(tmp_path, handler) as recovered:
        with pytest.raises(SubmissionConflict):
            recovered.submit(request(), lambda op: None, run_id="run", phase="baseline")
    assert len(calls) == 1


def test_ambiguous_timeout_without_id_is_durable_and_permanently_blocks_retry(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout(FAKE_SECRET, request=req)

    with adapter(tmp_path, handler) as client:
        with pytest.raises(UncertainSubmission) as raised:
            client.submit(request(), lambda op: None, run_id="run", phase="baseline")
        assert str(raised.value) == "transport_timeout"
        assert raised.value.__context__.__context__ is None
    journal = SubmissionJournal(tmp_path)
    assert journal.lookup("run", "baseline")["operation_id"] is None
    assert journal.lookup("run", "baseline")["state"] == "uncertain"
    with adapter(tmp_path, handler) as recovered:
        with pytest.raises(SubmissionConflict):
            recovered.submit(request(), lambda op: None, run_id="run", phase="baseline")
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b'{}', b'{"uuid":"invalid"}', b'{"uuid":null}', b'{"uuid":"22222222-2222-4222-8222-222222222222","uuid":null}', b'{"cost":NaN}', b'{"cost":1e999}', b'[]'])
def test_malformed_submission_response_becomes_uncertain(tmp_path, body):
    with adapter(tmp_path, lambda req: httpx.Response(201, content=body)) as client:
        with pytest.raises(UncertainSubmission):
            client.submit(request(), lambda op: None, run_id="run", phase="baseline")
    assert SubmissionJournal(tmp_path).lookup("run", "baseline")["state"] == "uncertain"


def test_unexpected_success_http_status_keeps_returned_operation_id(tmp_path):
    accepted = []
    with adapter(tmp_path, lambda req: httpx.Response(202, json={"uuid": OPERATION})) as client:
        with pytest.raises(RemoteAdapterError) as raised:
            client.submit(request(), accepted.append, run_id="run", phase="baseline")
    assert raised.value.operation_id == OPERATION and accepted == [OPERATION]
    assert SubmissionJournal(tmp_path).lookup("run", "baseline")["operation_id"] == OPERATION


@pytest.mark.parametrize("response, state, passed", [("success.json", "completed", True), ("nonzero.json", "completed", False), ("timed_out.json", "timed_out", False), ("service_failure.json", "failed", False), ("cancelled.json", "cancelled", False)])
def test_service_success_and_process_success_remain_distinct(tmp_path, response, state, passed):
    with adapter(tmp_path, lambda req: httpx.Response(200, json=fixture(response))) as client:
        result = client.observe(OPERATION)
    assert result.state == state and result.execution_passed is passed
    assert result.resources.get("cost") in {None, 123}
    assert not hasattr(result, "cost_dollars") and not hasattr(result, "behavior_verified")


@pytest.mark.parametrize("encoding", ["utf-8", "utf8"])
def test_documented_utf8_text_streams_preserve_unicode(tmp_path, encoding):
    data = fixture("success.json")
    stdout = '{"city": "Zürich", "mascot": "🐾"}\n'
    stderr = "診断: succès\n"
    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        data["metadata"]["result"][stream] = {
            "value": text, "encoding": encoding, "truncated": False,
        }
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert result.stdout == stdout and result.stderr == stderr
    assert result.execution_passed and result.evidence_complete


@pytest.mark.parametrize("exit_code", [0, 1])
def test_documented_no_signal_sentinel_preserves_exit_code_and_journal(tmp_path, exit_code):
    data = fixture("success.json")
    data["metadata"]["result"]["state"].update(exit_code=exit_code, signal=-1)

    def handler(req):
        return httpx.Response(201, json={"uuid": OPERATION}) if req.method == "POST" else httpx.Response(200, json=data)

    with adapter(tmp_path, handler) as client:
        client.submit(request(), lambda operation: None, run_id="run", phase="baseline")
        result = client.observe(OPERATION)
    assert result.signal is None and result.exit_code == exit_code
    assert result.evidence_complete and result.execution_passed is (exit_code == 0)
    recorded = SubmissionJournal(tmp_path).lookup("run", "baseline")["result_metadata"]
    assert recorded["signal"] is None and recorded["exit_code"] == exit_code


def test_real_positive_signal_cannot_pass_even_with_exit_zero(tmp_path):
    data = fixture("success.json")
    data["metadata"]["result"]["state"]["signal"] = 9
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert result.signal == 9 and result.exit_code == 0
    assert result.evidence_complete and not result.execution_passed


@pytest.mark.parametrize("signal", [-2, -(2**31), False])
def test_undocumented_negative_or_boolean_signal_fails_closed(tmp_path, signal):
    data = fixture("success.json")
    data["metadata"]["result"]["state"]["signal"] = signal
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert result.state == "incomplete"
    assert not result.evidence_complete and not result.execution_passed


def test_utf8_capture_limit_counts_bytes_and_records_truncation(tmp_path):
    data = fixture("success.json")
    data["metadata"]["truncate_output_at"] = 4
    data["metadata"]["result"]["stdout"] = {
        "value": "雪雪", "encoding": "utf-8", "truncated": False,
    }
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert result.stdout == "雪\ufffd" and result.stdout_truncated
    assert not result.execution_passed


def test_observation_timeout_is_not_execution_timeout_or_cancellation(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.method)
        return httpx.Response(200, json=fixture("queued.json"))

    with adapter(tmp_path, handler) as client:
        result = client.observe(OPERATION, timeout_seconds=0)
    assert result.state == "pending" and result.observation_timed_out and not result.timed_out
    assert not result.execution_passed and calls == ["GET"]


@pytest.mark.parametrize("change", ["missing_result", "missing_image", "unknown_encoding", "bad_base64", "missing_timed_out", "bool_exit", "wrong_network", "wrong_shell", "preserved_env", "missing_disposable", "false_disposable_image"])
def test_missing_or_contradictory_evidence_cannot_pass(tmp_path, change):
    data = fixture("success.json")
    if change == "missing_result":
        data["metadata"]["result"] = None
    elif change == "missing_image":
        data["image_uuid"] = None
    elif change == "unknown_encoding":
        data["metadata"]["result"]["stdout"]["encoding"] = "unknown"
    elif change == "bad_base64":
        data["metadata"]["result"]["stdout"]["value"] = "!!!"
    elif change == "missing_timed_out":
        del data["metadata"]["result"]["state"]["timed_out"]
    elif change == "bool_exit":
        data["metadata"]["result"]["state"]["exit_code"] = False
    elif change == "wrong_network":
        data["metadata"]["networking"]["enabled"] = True
    elif change == "wrong_shell":
        data["metadata"]["shell"] = True
    elif change == "preserved_env":
        data["metadata"]["preserve_env"] = True
    elif change == "missing_disposable":
        del data["metadata"]["disposable"]
    else:
        data["result_image_uuid"] = RESULT_IMAGE
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert not result.execution_passed and not result.evidence_complete
    assert result.state == "incomplete"


def test_known_image_and_retention_mismatch_are_rejected_after_submission(tmp_path):
    data = fixture("success.json")
    data["image_uuid"] = RESULT_IMAGE
    data["metadata"]["image"] = RESULT_IMAGE
    data["metadata"]["disposable"] = False

    def handler(req):
        return httpx.Response(201, json={"uuid": OPERATION}) if req.method == "POST" else httpx.Response(200, json=data)

    with adapter(tmp_path, handler) as client:
        client.submit(request(), lambda op: None, run_id="run", phase="baseline")
        result = client.observe(OPERATION)
    assert result.state == "incomplete" and not result.execution_passed
    assert result.error_code == "execution_image_unconfirmed"


def test_per_stream_capture_bounds_and_provider_truncation_are_honest(tmp_path):
    data = fixture("success.json")
    data["metadata"]["truncate_output_at"] = 4
    data["metadata"]["result"]["stdout"] = {"value": base64.b64encode(b"abcdef").decode(), "encoding": "base64", "truncated": False}
    data["metadata"]["result"]["stderr"]["truncated"] = True
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert result.stdout == "abcd" and result.stdout_truncated and result.stderr_truncated
    assert not result.execution_passed


def test_upload_identity_is_checked_and_frozen_content_reused(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["content-type"] == "application/octet-stream"
        return httpx.Response(201, json={"uuid": FILE, "sha256": hashlib.sha256(req.content).hexdigest(), "size": len(req.content)})

    with adapter(tmp_path, handler) as client:
        first = client.prepare({"/work/docdrift/a.py": b"print('ok')"})
        second = client.prepare({"/work/docdrift/b.py": b"print('ok')"})
    assert first["/work/docdrift/a.py"] == second["/work/docdrift/b.py"]
    assert len(calls) == 1 and calls[0].url.path == "/sandboxes/v1/files"


def test_upload_failure_cannot_blindly_retry_same_content(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(201, json={"uuid": FILE, "sha256": "0" * 64, "size": 3})

    with adapter(tmp_path, handler) as client:
        with pytest.raises(RemoteAdapterError, match="invalid_upload_response"):
            client.prepare({"/work/docdrift/a.py": b"abc"})
        with pytest.raises(RemoteAdapterError, match="upload_uncertain_no_retry"):
            client.prepare({"/work/docdrift/a.py": b"abc"})
    assert len(calls) == 1


def test_cancel_only_owned_operation_and_acceptance_is_not_terminal_evidence(tmp_path):
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        return httpx.Response(201, json={"uuid": OPERATION}) if req.method == "POST" else httpx.Response(202)

    with adapter(tmp_path, handler) as client:
        with pytest.raises(RemoteAdapterError, match="operation_not_owned"):
            client.cancel(OPERATION)
        client.submit(request(), lambda op: None, run_id="run", phase="baseline")
        client.cancel(OPERATION)
    assert calls == [("POST", "/sandboxes/v1/instances"), ("DELETE", f"/sandboxes/v1/operations/{OPERATION}")]
    assert SubmissionJournal(tmp_path).lookup("run", "baseline")["state"] == "accepted"


def test_download_uses_retained_result_image_and_safe_encoded_path(tmp_path):
    calls = []
    path = "/work/docdrift/results/report.json"

    def handler(req):
        calls.append(req)
        if req.url.path.endswith("download"):
            assert req.url.path == f"/sandboxes/v1/inspect/{RESULT_IMAGE}/download"
            assert req.url.params["path"] == path
            return httpx.Response(200, content=b'{"result":2}')
        return httpx.Response(200, json=fixture("retained.json"))

    with adapter(tmp_path, handler) as client:
        assert client.download(OPERATION, (path,)) == {path: b'{"result":2}'}
    assert [req.method for req in calls] == ["GET", "GET"]


def test_disposable_operations_have_no_artifact_continuation_image(tmp_path):
    with adapter(tmp_path, lambda req: httpx.Response(200, json=fixture("success.json"))) as client:
        with pytest.raises(RemoteAdapterError, match="artifact_image_unavailable"):
            client.download(OPERATION, ("/work/docdrift/output.txt",))


def test_artifact_stream_cannot_exceed_aggregate_limit(tmp_path):
    def handler(req):
        if req.url.path.endswith("download"):
            return httpx.Response(200, content=b"x" * (MAX_ARTIFACT_BYTES + 1))
        return httpx.Response(200, json=fixture("retained.json"))

    with adapter(tmp_path, handler) as client:
        with pytest.raises(RemoteAdapterError, match="response_limit_exceeded"):
            client.download(OPERATION, ("/work/docdrift/output.txt",))


def test_oversized_acceptance_response_is_uncertain_not_retried(tmp_path):
    with adapter(tmp_path, lambda req: httpx.Response(201, content=b"x" * (MAX_RESPONSE_BYTES + 1))) as client:
        with pytest.raises(UncertainSubmission, match="response_limit_exceeded"):
            client.submit(request(), lambda op: None, run_id="run", phase="baseline")
    assert SubmissionJournal(tmp_path).lookup("run", "baseline")["state"] == "uncertain"


class NeverReadStream(httpx.SyncByteStream):
    def __iter__(self):
        raise AssertionError("Response body must not be consumed")
        yield b""


@pytest.mark.parametrize("headers, code", [
    ({"content-encoding": "gzip"}, "compressed_response_forbidden"),
    ({"content-encoding": "br"}, "compressed_response_forbidden"),
    ({"content-length": str(MAX_RESPONSE_BYTES + 1)}, "response_limit_exceeded"),
    ({"content-length": "1,99999999"}, "invalid_content_length"),
])
def test_compressed_or_declared_oversized_responses_are_rejected_before_reading(tmp_path, headers, code):
    with adapter(tmp_path, lambda req: httpx.Response(200, headers=headers, stream=NeverReadStream())) as client:
        with pytest.raises(RemoteAdapterError, match=code):
            client.preflight()


def test_numeric_overflow_is_omitted_without_losing_execution_identity(tmp_path):
    data = fixture("success.json")
    data["duration"] = 10**1000
    data["metadata"]["result"]["resources"]["cost"] = 10**1000
    with adapter(tmp_path, lambda req: httpx.Response(200, json=data)) as client:
        result = client.observe(OPERATION)
    assert result.operation_id == OPERATION and result.elapsed_seconds is None
    assert "cost" not in result.resources


@pytest.mark.parametrize("changes", [{"image_id": "tag:python:3.12"}, {"executable": "python -c print(1)"}, {"environment": {"NEBIUS_API_KEY": FAKE_SECRET}}, {"disposable": 1}, {"timeout_seconds": 31}, {"log_limit_bytes": 262145}, {"files": {"/work/docdrift/../secret.py": FILE}}, {"files": {"/work/docdrift/.aws/credentials": FILE}}])
def test_invalid_guest_contract_never_reaches_transport_or_journal(tmp_path, changes):
    calls = []
    with adapter(tmp_path, lambda req: calls.append(req)) as client:
        with pytest.raises(ValueError):
            client.submit(request(**changes), lambda op: None, run_id="run", phase="baseline")
    assert calls == [] and SubmissionJournal(tmp_path).for_run("run") == []
