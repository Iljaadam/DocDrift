"""Small transactional run ledger; large artifacts remain outside SQLite."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


MAX_JSON_BYTES = 1_048_576
_SECRET_KEYS = {
    "api_key", "apikey", "access_token", "refresh_token", "authorization",
    "password", "passwd", "secret", "credential", "credentials", "token",
}


def _redact(value: Any) -> Any:
    """Exclude recognizable credential fields, including nested metadata.

    Callers must never put credentials in free-form strings, logs, or source.
    Arbitrary prose cannot be reliably identified as a secret by a ledger.
    """
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower().replace("-", "_") in _SECRET_KEYS
                or str(key).lower().endswith(("_api_key", "_password", "_secret", "_access_token"))
                else _redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _json(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        raise TypeError("Ledger metadata must be a JSON object")
    encoded = json.dumps(_redact(value), sort_keys=True, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Ledger metadata exceeds the 1 MiB limit; save an artifact instead")
    return encoded


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """Persist accepted operation IDs before execution, without a remote queue."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "state.sqlite3"
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    phase TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    operation_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    state TEXT NOT NULL,
                    accepted_at TEXT NOT NULL,
                    completed_at TEXT,
                    result_json TEXT,
                    PRIMARY KEY (run_id, operation_id)
                );
                CREATE INDEX IF NOT EXISTS events_run ON events(run_id, sequence);
                """
            )
        self.path.chmod(0o600)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _identifier(value: str, name: str) -> None:
        if not isinstance(value, str) or not value or len(value) > 256 or "\x00" in value:
            raise ValueError(f"{name} must be a nonempty identifier of at most 256 characters")

    def create_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        self._identifier(run_id, "run_id")
        encoded = _json(metadata)
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO runs (run_id, created_at, metadata_json) VALUES (?, ?, ?)",
                (run_id, _now(), encoded),
            )

    def event(self, run_id: str, phase: str, payload: dict[str, Any]) -> int:
        self._identifier(phase, "phase")
        encoded = _json(payload)
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO events (run_id, phase, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (run_id, phase, _now(), encoded),
            )
            return int(cursor.lastrowid)

    def save_operation(self, run_id: str, phase: str, operation_id: str) -> None:
        self._identifier(operation_id, "operation_id")
        self._identifier(phase, "phase")
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT phase FROM operations WHERE run_id = ? AND operation_id = ?",
                (run_id, operation_id),
            ).fetchone()
            if existing is not None:
                if existing["phase"] != phase:
                    raise ValueError("An accepted operation cannot be reassigned to another phase")
                return
            connection.execute(
                """INSERT INTO operations
                   (run_id, operation_id, phase, state, accepted_at)
                   VALUES (?, ?, ?, 'accepted', ?)""",
                (run_id, operation_id, phase, _now()),
            )

    def complete_operation(self, run_id: str, operation_id: str, result: dict[str, Any]) -> None:
        encoded = _json(result)
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE operations SET state = 'completed', completed_at = ?, result_json = ?
                   WHERE run_id = ? AND operation_id = ?""",
                (_now(), encoded, run_id, operation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown accepted operation: {operation_id}")

    @staticmethod
    def _operation(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["result"] = json.loads(data.pop("result_json")) if row["result_json"] is not None else None
        return data

    def operations(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM operations WHERE run_id = ? ORDER BY accepted_at, operation_id",
                (run_id,),
            ).fetchall()
        return [self._operation(row) for row in rows]

    def run(self, run_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown run: {run_id}")
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
            operations = connection.execute(
                "SELECT * FROM operations WHERE run_id = ? ORDER BY accepted_at, operation_id",
                (run_id,),
            ).fetchall()
        events = []
        phases = {}
        for event_row in rows:
            event = dict(event_row)
            event["payload"] = json.loads(event.pop("payload_json"))
            phases[event["phase"]] = event["payload"]
            events.append(event)
        return {
            "run_id": row["run_id"], "created_at": row["created_at"],
            "metadata": json.loads(row["metadata_json"]), "events": events,
            "phases": phases, "operations": [self._operation(item) for item in operations],
        }

    def runs(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM runs ORDER BY created_at, run_id").fetchall()
        return [
            {"run_id": row["run_id"], "created_at": row["created_at"],
             "metadata": json.loads(row["metadata_json"])}
            for row in rows
        ]
