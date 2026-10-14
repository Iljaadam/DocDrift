"""Durable receipts for one remote submission per frozen run phase.

This ledger does not submit, retry, or cancel work. Its write-before-submit
boundary survives ambiguous HTTP outcomes without authorizing another POST.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4


MAX_RESULT_METADATA_BYTES = 16_384
MAX_RESOURCE_METRICS = 128
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\Z")
_REASON = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MACHINE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_METRIC_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_UUID_FIELDS = {"operation_id", "image_id", "result_image_id"}
_BOOLEAN_FIELDS = {
    "timed_out", "observation_timed_out", "stdout_truncated", "stderr_truncated",
    "evidence_complete",
}
_INTEGER_FIELDS = {"exit_code", "signal"}
_TOKEN_FIELDS = {"state", "service_state", "error_code"}
_KNOWN_STATES = {
    "state": {"pending", "completed", "failed", "cancelled", "timed_out", "incomplete"},
    "service_state": {"PENDING", "ASSIGNED", "EXECUTING", "SUCCESS", "FAILED", "CANCELLED"},
}


class SubmissionError(ValueError):
    """A remote receipt or transition violates the submission contract."""


class SubmissionConflict(SubmissionError):
    """A phase or operation already has an immutable submission identity."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise SubmissionError(f"{name} must be a bounded machine identifier")


def _uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise SubmissionError(f"{name} must be a canonical lowercase UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise SubmissionError(f"{name} must be a canonical lowercase UUID") from exc
    if str(parsed) != value or parsed.int == 0:
        raise SubmissionError(f"{name} must be a canonical nonzero lowercase UUID")
    return value


def _reason(value: str) -> None:
    if not isinstance(value, str) or _REASON.fullmatch(value) is None:
        raise SubmissionError("reason_code must be a lowercase code, not prose or a response body")


def _safe_metadata(value: dict[str, Any]) -> str:
    """Persist only result facts; omit logs, prompts, requests, and credentials."""
    if not isinstance(value, dict):
        raise SubmissionError("result_metadata must be an object")
    safe: dict[str, Any] = {}
    for key in _UUID_FIELDS:
        if key in value:
            safe[key] = None if value[key] is None else _uuid(value[key], key)
    for key in _BOOLEAN_FIELDS:
        if key in value:
            if not isinstance(value[key], bool):
                raise SubmissionError(f"{key} must be boolean")
            safe[key] = value[key]
    for key in _INTEGER_FIELDS:
        if key in value:
            item = value[key]
            if item is not None and (type(item) is not int or not -(2**31) <= item < 2**31):
                raise SubmissionError(f"{key} must be a bounded integer or null")
            safe[key] = item
    for key in _TOKEN_FIELDS:
        if key in value:
            item = value[key]
            if item is not None and (not isinstance(item, str) or _MACHINE_TOKEN.fullmatch(item) is None):
                raise SubmissionError(f"{key} must be a bounded machine token or null")
            if item is not None and key in _KNOWN_STATES and item not in _KNOWN_STATES[key]:
                raise SubmissionError(f"{key} is not a recognized result state")
            safe[key] = item
    if "elapsed_seconds" in value:
        item = value["elapsed_seconds"]
        if item is not None and (type(item) not in (int, float) or not 0 <= item <= 1e100 or not math.isfinite(item)):
            raise SubmissionError("elapsed_seconds must be finite and nonnegative or null")
        safe["elapsed_seconds"] = item
    if "resources" in value:
        metrics = value["resources"]
        if not isinstance(metrics, dict) or len(metrics) > MAX_RESOURCE_METRICS:
            raise SubmissionError("resources must be a bounded object of numeric metrics")
        safe_metrics: dict[str, int | float] = {}
        for key, item in metrics.items():
            if not isinstance(key, str) or _METRIC_NAME.fullmatch(key) is None:
                raise SubmissionError("resource metric names must be bounded machine identifiers")
            if type(item) not in (int, float) or abs(item) > 1e100 or not math.isfinite(item):
                raise SubmissionError("resource metrics must be finite bounded numbers")
            if any(marker in key.lower() for marker in ("authorization", "credential", "password", "secret", "token", "api_key")):
                continue
            safe_metrics[key] = item
        safe["resources"] = safe_metrics
    encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_RESULT_METADATA_BYTES:
        raise SubmissionError("safe result metadata exceeds its size limit")
    return encoded


class SubmissionJournal:
    """Use separate tables in the same database as ``StateStore``.

    ``lookup`` is a resume operation: it atomically marks a no-ID submission
    uncertain. ``get`` and ``for_run`` are read-only, so an active adapter can
    inspect its receipt without triggering crash recovery.
    """

    def __init__(self, state_root: Path):
        self.root = Path(state_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "state.sqlite3"
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS remote_submissions (
                    attempt_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN
                        ('submitting', 'accepted', 'uncertain', 'rejected', 'completed')),
                    operation_id TEXT UNIQUE,
                    reason_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    accepted_at TEXT,
                    completed_at TEXT,
                    result_metadata_json TEXT,
                    UNIQUE (run_id, phase)
                );
                CREATE INDEX IF NOT EXISTS remote_submissions_run
                    ON remote_submissions(run_id, created_at, attempt_id);
                """
            )
        self.path.chmod(0o600)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _receipt(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        encoded = data.pop("result_metadata_json")
        data["result_metadata"] = json.loads(encoded) if encoded is not None else None
        return data

    @staticmethod
    def _row(connection: sqlite3.Connection, attempt_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM remote_submissions WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown remote attempt: {attempt_id}")
        return row

    def begin(self, run_id: str, phase: str, request_digest: str) -> dict[str, Any]:
        """Commit one budget-consuming receipt before a remote POST.

        Duplicate phases always fail, including rejected or uncertain phases.
        A different digest does not create permission to retry changed inputs.
        """
        _identifier(run_id, "run_id")
        _identifier(phase, "phase")
        if not isinstance(request_digest, str) or _DIGEST.fullmatch(request_digest) is None:
            raise SubmissionError("request_digest must be a lowercase SHA-256 digest")
        attempt_id = str(uuid4())
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """INSERT INTO remote_submissions
                       (attempt_id, run_id, phase, request_digest, state, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'submitting', ?, ?)""",
                    (attempt_id, run_id, phase, request_digest, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise SubmissionConflict("This run phase already has a submission receipt; automatic retry is forbidden") from exc
            receipt = self._receipt(self._row(connection, attempt_id))
        return receipt

    def accepted(self, attempt_id: str, operation_id: str) -> dict[str, Any]:
        """Persist the returned ID before callbacks; never replace or share it."""
        error: SubmissionError | None = None
        receipt: dict[str, Any] | None = None
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, attempt_id)
            try:
                _uuid(operation_id, "operation_id")
            except SubmissionError as exc:
                error = exc
                if row["operation_id"] is None and row["state"] in {"submitting", "uncertain"}:
                    connection.execute(
                        """UPDATE remote_submissions SET state = 'uncertain', reason_code =
                           'invalid_operation_id', updated_at = ? WHERE attempt_id = ?""",
                        (_now(), attempt_id),
                    )
            else:
                if row["operation_id"] is not None and row["operation_id"] != operation_id:
                    error = SubmissionConflict("An accepted operation ID is immutable")
                elif row["state"] == "rejected":
                    error = SubmissionError("A rejected submission cannot become accepted")
                elif row["state"] == "completed":
                    receipt = self._receipt(row)
                else:
                    owner = connection.execute(
                        "SELECT attempt_id FROM remote_submissions WHERE operation_id = ?", (operation_id,)
                    ).fetchone()
                    if owner is not None and owner["attempt_id"] != attempt_id:
                        error = SubmissionConflict("An operation ID already belongs to another submission")
                        connection.execute(
                            """UPDATE remote_submissions SET state = 'uncertain', reason_code =
                               'operation_id_conflict', updated_at = ? WHERE attempt_id = ?""",
                            (_now(), attempt_id),
                        )
                    else:
                        now = _now()
                        connection.execute(
                            """UPDATE remote_submissions SET state = 'accepted', operation_id = ?,
                               accepted_at = COALESCE(accepted_at, ?), updated_at = ?, reason_code = NULL
                               WHERE attempt_id = ?""",
                            (operation_id, now, now, attempt_id),
                        )
                        receipt = self._receipt(self._row(connection, attempt_id))
        # The uncertain receipt must be committed even when ID validation fails.
        if error is not None:
            raise error
        assert receipt is not None
        return receipt

    def uncertain(self, attempt_id: str, reason_code: str) -> dict[str, Any]:
        """Record uncertainty without losing any already accepted operation ID."""
        _reason(reason_code)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, attempt_id)
            if row["state"] in {"completed", "rejected"}:
                raise SubmissionError("A terminal receipt cannot become uncertain")
            connection.execute(
                "UPDATE remote_submissions SET state = 'uncertain', reason_code = ?, updated_at = ? WHERE attempt_id = ?",
                (reason_code, _now(), attempt_id),
            )
            receipt = self._receipt(self._row(connection, attempt_id))
        return receipt

    def rejected(self, attempt_id: str, reason_code: str) -> dict[str, Any]:
        """Record a definitive rejection while retaining the no-retry receipt."""
        _reason(reason_code)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, attempt_id)
            if row["operation_id"] is not None or row["state"] == "completed":
                raise SubmissionError("An accepted operation cannot be rejected as an unsubmitted request")
            if row["state"] == "rejected":
                if row["reason_code"] != reason_code:
                    raise SubmissionConflict("A definitive rejection reason is immutable")
                return self._receipt(row)
            connection.execute(
                "UPDATE remote_submissions SET state = 'rejected', reason_code = ?, updated_at = ? WHERE attempt_id = ?",
                (reason_code, _now(), attempt_id),
            )
            receipt = self._receipt(self._row(connection, attempt_id))
        return receipt

    def completed(self, attempt_id: str, result_metadata: dict[str, Any]) -> dict[str, Any]:
        encoded = _safe_metadata(result_metadata)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, attempt_id)
            if row["operation_id"] is None or row["state"] not in {"accepted", "completed"}:
                raise SubmissionError("Completion requires an accepted operation receipt")
            metadata_operation = json.loads(encoded).get("operation_id")
            if metadata_operation is not None and metadata_operation != row["operation_id"]:
                raise SubmissionConflict("Result operation ID does not match its receipt")
            if row["state"] == "completed":
                if row["result_metadata_json"] != encoded:
                    raise SubmissionConflict("Completed result metadata is immutable")
                return self._receipt(row)
            now = _now()
            connection.execute(
                """UPDATE remote_submissions SET state = 'completed', completed_at = ?,
                   updated_at = ?, result_metadata_json = ?, reason_code = NULL WHERE attempt_id = ?""",
                (now, now, encoded, attempt_id),
            )
            receipt = self._receipt(self._row(connection, attempt_id))
        return receipt

    def lookup(self, run_id: str, phase: str) -> dict[str, Any] | None:
        """Resume lookup: an interrupted no-ID POST remains uncertain, not new."""
        _identifier(run_id, "run_id")
        _identifier(phase, "phase")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM remote_submissions WHERE run_id = ? AND phase = ?", (run_id, phase)
            ).fetchone()
            if row is None:
                return None
            if row["state"] == "submitting" and row["operation_id"] is None:
                connection.execute(
                    """UPDATE remote_submissions SET state = 'uncertain', reason_code =
                       'submission_interrupted', updated_at = ? WHERE attempt_id = ?""",
                    (_now(), row["attempt_id"]),
                )
                row = self._row(connection, row["attempt_id"])
            receipt = self._receipt(row)
        return receipt

    def get(self, attempt_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            return self._receipt(self._row(connection, attempt_id))

    def for_run(self, run_id: str) -> list[dict[str, Any]]:
        _identifier(run_id, "run_id")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM remote_submissions WHERE run_id = ? ORDER BY created_at, attempt_id", (run_id,)
            ).fetchall()
            return [self._receipt(row) for row in rows]
