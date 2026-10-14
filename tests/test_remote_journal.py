import hashlib
import multiprocessing
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from docdrift.remote_journal import SubmissionConflict, SubmissionError, SubmissionJournal
from docdrift.store import StateStore


DIGEST = hashlib.sha256(b"frozen request without credentials").hexdigest()
OTHER_DIGEST = hashlib.sha256(b"changed request").hexdigest()


def _competing_begin(state_root, ready, start, results):
    journal = SubmissionJournal(Path(state_root))
    ready.put(True)
    start.wait(10)
    try:
        receipt = journal.begin("run", "original", DIGEST)
    except SubmissionConflict:
        results.put(("conflict", None))
    else:
        results.put(("created", receipt["attempt_id"]))


@pytest.fixture
def journal(tmp_path):
    return SubmissionJournal(tmp_path / "state")


def test_begin_commits_receipt_before_any_remote_call(journal):
    receipt = journal.begin("run", "original", DIGEST)
    assert receipt["state"] == "submitting"
    assert receipt["operation_id"] is None
    assert receipt["request_digest"] == DIGEST
    # A second process/connection can see the durable budget receipt immediately.
    reopened = SubmissionJournal(journal.root)
    assert reopened.get(receipt["attempt_id"]) == receipt
    assert reopened.for_run("run") == [receipt]
    assert receipt["accepted_at"] is None
    assert receipt["result_metadata"] is None


def test_submission_tables_interoperate_with_state_store_in_either_order(tmp_path):
    root = tmp_path / "state"
    journal = SubmissionJournal(root)
    receipt = journal.begin("run", "original", DIGEST)
    store = StateStore(root)
    store.create_run("run", {"scope": "offline_contract_test"})
    operation_id = str(uuid4())
    journal.accepted(receipt["attempt_id"], operation_id)
    store.save_operation("run", "original", operation_id)
    assert store.run("run")["operations"][0]["operation_id"] == operation_id
    assert journal.get(receipt["attempt_id"])["operation_id"] == operation_id
    second_root = tmp_path / "other-state"
    StateStore(second_root).create_run("other", {})
    assert SubmissionJournal(second_root).begin("other", "original", DIGEST)["state"] == "submitting"


def test_concurrent_processes_can_create_only_one_phase_receipt(journal):
    context = multiprocessing.get_context("spawn")
    ready, results = context.Queue(), context.Queue()
    start = context.Event()
    processes = [
        context.Process(target=_competing_begin, args=(str(journal.root), ready, start, results))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=10)
        start.set()
        outcomes = [results.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert sorted(outcome[0] for outcome in outcomes) == ["conflict", "created"]
        assert len(journal.for_run("run")) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        ready.close()
        results.close()


@pytest.mark.parametrize("outcome", ["submitting", "uncertain", "rejected", "accepted", "completed"])
def test_same_phase_is_never_automatically_retried_even_with_changed_inputs(journal, outcome):
    receipt = journal.begin("run", "original", DIGEST)
    attempt_id = receipt["attempt_id"]
    if outcome == "uncertain":
        journal.uncertain(attempt_id, "transport_timeout")
    elif outcome == "rejected":
        journal.rejected(attempt_id, "http_400")
    elif outcome in {"accepted", "completed"}:
        journal.accepted(attempt_id, str(uuid4()))
        if outcome == "completed":
            journal.completed(attempt_id, {"state": "completed", "service_state": "SUCCESS"})
    for digest in (DIGEST, OTHER_DIGEST):
        with pytest.raises(SubmissionConflict, match="retry"):
            journal.begin("run", "original", digest)
    assert len(journal.for_run("run")) == 1
    assert journal.get(attempt_id)["request_digest"] == DIGEST
    # A separately authorized phase has a new receipt rather than erasing history.
    assert journal.begin("run", "candidate_1", OTHER_DIGEST)["attempt_id"] != attempt_id


def test_rejected_and_uncertain_receipts_still_count_toward_submission_budget(journal):
    rejected = journal.begin("run", "original", DIGEST)
    journal.rejected(rejected["attempt_id"], "http_400")
    uncertain = journal.begin("run", "candidate_1", DIGEST)
    journal.uncertain(uncertain["attempt_id"], "transport_timeout")
    accepted = journal.begin("run", "candidate_2", DIGEST)
    journal.accepted(accepted["attempt_id"], str(uuid4()))
    assert len(SubmissionJournal(journal.root).for_run("run")) == 3


def test_resume_lookup_recovers_no_id_crash_without_mutating_active_get(journal):
    receipt = journal.begin("run", "original", DIGEST)
    reopened = SubmissionJournal(journal.root)
    assert reopened.get(receipt["attempt_id"])["state"] == "submitting"
    assert reopened.for_run("run")[0]["state"] == "submitting"
    recovered = reopened.lookup("run", "original")
    assert recovered["state"] == "uncertain"
    assert recovered["reason_code"] == "submission_interrupted"
    assert recovered["operation_id"] is None
    assert reopened.get(receipt["attempt_id"]) == recovered
    assert journal.lookup("run", "original") == recovered
    assert journal.lookup("missing", "original") is None
    with pytest.raises(SubmissionConflict):
        journal.begin("run", "original", DIGEST)


def test_accepted_id_is_immediately_durable_before_failed_external_callback(journal):
    receipt = journal.begin("run", "original", DIGEST)
    operation_id = str(uuid4())

    def callback(_operation_id):
        # Simulate an engine/evidence callback failing after the remote acceptance.
        assert SubmissionJournal(journal.root).get(receipt["attempt_id"])["operation_id"] == operation_id
        raise RuntimeError("offline callback failure")

    with pytest.raises(RuntimeError):
        journal.accepted(receipt["attempt_id"], operation_id)
        callback(operation_id)
    recovered = SubmissionJournal(journal.root).lookup("run", "original")
    assert recovered["state"] == "accepted"
    assert recovered["operation_id"] == operation_id
    with pytest.raises(SubmissionConflict):
        journal.begin("run", "original", DIGEST)


def test_operation_identity_is_immutable_and_globally_unique(journal):
    first = journal.begin("run", "original", DIGEST)
    operation_id = str(uuid4())
    accepted = journal.accepted(first["attempt_id"], operation_id)
    assert journal.accepted(first["attempt_id"], operation_id)["accepted_at"] == accepted["accepted_at"]
    with pytest.raises(SubmissionConflict, match="immutable"):
        journal.accepted(first["attempt_id"], str(uuid4()))
    assert journal.get(first["attempt_id"])["operation_id"] == operation_id
    second = journal.begin("another_run", "original", DIGEST)
    with pytest.raises(SubmissionConflict, match="belongs"):
        journal.accepted(second["attempt_id"], operation_id)
    conflict = journal.get(second["attempt_id"])
    assert conflict["state"] == "uncertain"
    assert conflict["reason_code"] == "operation_id_conflict"
    assert conflict["operation_id"] is None
    assert journal.get(first["attempt_id"])["state"] == "accepted"


@pytest.mark.parametrize("operation_id", ["not-a-uuid", "0" * 32, "00000000-0000-0000-0000-000000000000", None])
def test_malformed_returned_id_commits_uncertainty_not_an_untracked_retry(journal, operation_id):
    receipt = journal.begin("run", "original", DIGEST)
    with pytest.raises(SubmissionError, match="UUID"):
        journal.accepted(receipt["attempt_id"], operation_id)
    reopened = SubmissionJournal(journal.root)
    uncertain = reopened.get(receipt["attempt_id"])
    assert uncertain["state"] == "uncertain"
    assert uncertain["reason_code"] == "invalid_operation_id"
    assert uncertain["operation_id"] is None
    with pytest.raises(SubmissionConflict):
        reopened.begin("run", "original", DIGEST)


def test_uuid_aliases_cannot_create_a_second_identity(journal):
    first = journal.begin("run", "original", DIGEST)
    operation_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    journal.accepted(first["attempt_id"], operation_id)
    for index, alias in enumerate((operation_id.upper(), operation_id.replace("-", ""))):
        other = journal.begin("run", f"candidate_{index}", DIGEST)
        with pytest.raises(SubmissionError):
            journal.accepted(other["attempt_id"], alias)
        assert journal.get(other["attempt_id"])["state"] == "uncertain"
    assert journal.get(first["attempt_id"])["operation_id"] == operation_id


def test_unknown_remote_operation_retains_receipt_until_reconciled(journal):
    receipt = journal.begin("run", "original", DIGEST)
    operation_id = str(uuid4())
    original = journal.accepted(receipt["attempt_id"], operation_id)
    unknown = journal.uncertain(receipt["attempt_id"], "http_404")
    assert unknown["operation_id"] == operation_id
    assert journal.lookup("run", "original")["operation_id"] == operation_id
    with pytest.raises(SubmissionError, match="accepted"):
        journal.completed(receipt["attempt_id"], {"state": "completed"})
    reconciled = journal.accepted(receipt["attempt_id"], operation_id)
    assert reconciled["accepted_at"] == original["accepted_at"]
    completed = journal.completed(receipt["attempt_id"], {"operation_id": operation_id, "state": "completed"})
    assert completed["state"] == "completed"


def test_completion_requires_matching_accepted_id_and_is_immutable(journal):
    receipt = journal.begin("run", "original", DIGEST)
    with pytest.raises(SubmissionError, match="accepted"):
        journal.completed(receipt["attempt_id"], {"state": "completed"})
    operation_id = str(uuid4())
    journal.accepted(receipt["attempt_id"], operation_id)
    with pytest.raises(SubmissionConflict, match="match"):
        journal.completed(receipt["attempt_id"], {"operation_id": str(uuid4())})
    metadata = {"operation_id": operation_id, "state": "completed", "exit_code": 0}
    completed = journal.completed(receipt["attempt_id"], metadata)
    assert completed["result_metadata"] == metadata
    assert journal.completed(receipt["attempt_id"], metadata) == completed
    assert journal.accepted(receipt["attempt_id"], operation_id) == completed
    with pytest.raises(SubmissionConflict, match="immutable"):
        journal.completed(receipt["attempt_id"], {"exit_code": 1})
    with pytest.raises(SubmissionError):
        journal.uncertain(receipt["attempt_id"], "observation_timeout")
    with pytest.raises(SubmissionError):
        journal.rejected(receipt["attempt_id"], "http_400")


def test_missing_duration_remains_unknown_in_terminal_result(journal):
    receipt = journal.begin("run", "original", DIGEST)
    journal.accepted(receipt["attempt_id"], str(uuid4()))
    completed = journal.completed(receipt["attempt_id"], {
        "state": "failed", "service_state": "FAILED", "elapsed_seconds": None,
    })
    assert completed["result_metadata"]["elapsed_seconds"] is None


def test_result_whitelist_omits_credentials_request_bodies_prompts_and_logs(journal):
    receipt = journal.begin("run", "original", DIGEST)
    operation_id, image_id = str(uuid4()), str(uuid4())
    journal.accepted(receipt["attempt_id"], operation_id)
    result = journal.completed(receipt["attempt_id"], {
        "operation_id": operation_id,
        "image_id": image_id,
        "result_image_id": None,
        "state": "completed",
        "service_state": "SUCCESS",
        "exit_code": 0,
        "signal": None,
        "timed_out": False,
        "observation_timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": True,
        "evidence_complete": True,
        "elapsed_seconds": 0.25,
        "resources": {"cpu_ms": 25, "raw_cost": 1.2, "authorization_token": 123},
        "authorization": "Bearer must-never-be-stored",
        "environment": {"API_KEY": "must-never-be-stored"},
        "request_body": "must-never-be-stored",
        "source": "must-never-be-stored",
        "prompts": ["must-never-be-stored"],
        "stdout": "must-never-be-stored",
        "stderr": "must-never-be-stored",
    })
    metadata = result["result_metadata"]
    assert metadata["resources"] == {"cpu_ms": 25, "raw_cost": 1.2}
    assert metadata["image_id"] == image_id
    assert "authorization" not in metadata
    with sqlite3.connect(journal.path) as connection:
        saved = connection.execute("SELECT result_metadata_json FROM remote_submissions").fetchone()[0]
    assert "must-never-be-stored" not in saved
    assert "authorization_token" not in saved


@pytest.mark.parametrize("metadata", [
    {"resources": {"cpu_ms": float("nan")}},
    {"resources": {"cpu_ms": True}},
    {"resources": {"cpu_ms": 10**10000}},
    {"resources": {"nested": {"secret": "value"}}},
    {"elapsed_seconds": float("inf")},
    {"elapsed_seconds": -1},
    {"elapsed_seconds": 10**10000},
    {"exit_code": True},
    {"timed_out": "false"},
    {"state": "arbitrary_secret_string"},
    {"service_state": "unrecognized_status"},
    {"error_code": "Authorization: Bearer response content"},
    {"image_id": "not-an-image-uuid"},
    {"resources": {f"metric_{i}": i for i in range(129)}},
    {"resources": {f"metric_{i:03d}_" + "x" * 53: 10**99 for i in range(128)}},
])
def test_invalid_or_oversized_safe_metadata_does_not_complete_receipt(journal, metadata):
    receipt = journal.begin("run", "original", DIGEST)
    journal.accepted(receipt["attempt_id"], str(uuid4()))
    with pytest.raises(SubmissionError):
        journal.completed(receipt["attempt_id"], metadata)
    assert journal.get(receipt["attempt_id"])["state"] == "accepted"


def test_definitive_rejection_is_terminal_without_erasing_receipt(journal):
    receipt = journal.begin("run", "original", DIGEST)
    rejected = journal.rejected(receipt["attempt_id"], "http_400")
    assert journal.rejected(receipt["attempt_id"], "http_400") == rejected
    with pytest.raises(SubmissionConflict):
        journal.rejected(receipt["attempt_id"], "http_401")
    with pytest.raises(SubmissionError):
        journal.accepted(receipt["attempt_id"], str(uuid4()))
    with pytest.raises(SubmissionError):
        journal.uncertain(receipt["attempt_id"], "transport_timeout")
    assert journal.get(receipt["attempt_id"])["state"] == "rejected"


@pytest.mark.parametrize("digest", ["", "not-a-digest", DIGEST.upper(), "f" * 63, "g" * 64])
def test_invalid_request_digest_cannot_create_a_receipt(journal, digest):
    with pytest.raises(SubmissionError, match="SHA-256"):
        journal.begin("run", "original", digest)
    assert journal.for_run("run") == []


def test_reason_codes_are_bounded_and_do_not_accept_response_prose(journal):
    receipt = journal.begin("run", "original", DIGEST)
    with pytest.raises(SubmissionError, match="reason_code"):
        journal.uncertain(receipt["attempt_id"], "Authorization: Bearer sensitive-token")
    assert journal.get(receipt["attempt_id"])["state"] == "submitting"


def test_unknown_attempts_are_not_synthesized(journal):
    attempt_id = str(uuid4())
    with pytest.raises(KeyError):
        journal.get(attempt_id)
    with pytest.raises(KeyError):
        journal.accepted(attempt_id, str(uuid4()))
    with pytest.raises(KeyError):
        journal.uncertain(attempt_id, "transport_timeout")
    with pytest.raises(KeyError):
        journal.rejected(attempt_id, "http_400")
    with pytest.raises(KeyError):
        journal.completed(attempt_id, {})
