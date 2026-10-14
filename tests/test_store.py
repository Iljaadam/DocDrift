import sqlite3

import pytest

from docdrift.store import MAX_JSON_BYTES, StateStore


def test_operation_id_survives_a_new_store_before_result(tmp_path):
    store = StateStore(tmp_path)
    store.create_run("run-1", {"commit": "a" * 40})
    store.event("run-1", "frozen", {"profile_sha256": "b" * 64})
    store.save_operation("run-1", "baseline:target:0", "c" * 64)
    recovered = StateStore(tmp_path)
    operation = recovered.operations("run-1")[0]
    assert operation["operation_id"] == "c" * 64
    assert operation["state"] == "accepted"
    assert operation["result"] is None
    recovered.complete_operation("run-1", "c" * 64, {"exit_code": 1, "stderr": "missing method"})
    assert store.operations("run-1")[0]["result"]["exit_code"] == 1


def test_events_preserve_history_and_latest_phase_payload(tmp_path):
    store = StateStore(tmp_path)
    store.create_run("one", {"origin": "owned fixture"})
    first = store.event("one", "baseline", {"completed": 1})
    second = store.event("one", "baseline", {"completed": 2})
    run = store.run("one")
    assert [event["sequence"] for event in run["events"]] == [first, second]
    assert run["phases"] == {"baseline": {"completed": 2}}
    assert run["metadata"] == {"origin": "owned fixture"}
    assert store.runs()[0]["run_id"] == "one"


def test_structured_credentials_are_excluded_without_removing_usage(tmp_path):
    store = StateStore(tmp_path)
    store.create_run("one", {
        "api_key": "DO-NOT-SAVE", "nested": {"Authorization": "Bearer DO-NOT-SAVE"},
        "input_tokens": 100, "nebius_access_token": "DO-NOT-SAVE",
    })
    metadata = store.run("one")["metadata"]
    assert metadata["api_key"] == "[REDACTED]"
    assert metadata["nested"]["Authorization"] == "[REDACTED]"
    assert metadata["nebius_access_token"] == "[REDACTED]"
    assert metadata["input_tokens"] == 100
    assert b"DO-NOT-SAVE" not in store.path.read_bytes()


def test_invalid_writes_leave_previously_accepted_state_intact(tmp_path):
    store = StateStore(tmp_path)
    store.create_run("one", {})
    store.save_operation("one", "original", "op-1")
    store.save_operation("one", "original", "op-1")
    with pytest.raises(ValueError):
        store.save_operation("one", "verification", "op-1")
    with pytest.raises(ValueError):
        store.complete_operation("one", "op-1", {"stdout": "x" * MAX_JSON_BYTES})
    operation = store.operations("one")[0]
    assert operation["phase"] == "original"
    assert operation["state"] == "accepted"
    with pytest.raises(KeyError):
        store.complete_operation("one", "unknown", {"exit_code": 0})
    with pytest.raises(sqlite3.IntegrityError):
        store.event("unknown", "baseline", {})
    with pytest.raises(sqlite3.IntegrityError):
        store.create_run("one", {})
    assert len(store.runs()) == 1
