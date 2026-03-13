"""SQLite persistence for the MVP."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import as_json
from .models import ModelState, RoundResult, Task


SCHEMA = """
CREATE TABLE IF NOT EXISTS model_states (
    model_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS round_results (
    round_id TEXT PRIMARY KEY,
    cycle_number INTEGER NOT NULL,
    executor_model_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class SQLiteRepository:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_model_state(self, state: ModelState) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO model_states(model_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(model_id)
                DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (state.model_id, as_json(state.to_dict()), state.updated_at.isoformat()),
            )

    def list_model_states(self) -> list[ModelState]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM model_states ORDER BY model_id").fetchall()
        return [ModelState.from_dict(json.loads(row["payload"])) for row in rows]

    def get_model_state(self, model_id: str) -> ModelState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM model_states WHERE model_id = ?",
                (model_id,),
            ).fetchone()
        if row is None:
            return None
        return ModelState.from_dict(json.loads(row["payload"]))

    def queue_task(self, task: Task) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO tasks(task_id, status, source, prompt_hash, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.status,
                    task.source,
                    task.prompt_hash,
                    task.created_at.isoformat(),
                    as_json(task.to_dict()),
                ),
            )

    def list_tasks(self, limit: int = 50) -> list[Task]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Task.from_dict(json.loads(row["payload"])) for row in rows]

    def task_exists_by_hash(self, value: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM tasks WHERE prompt_hash = ? LIMIT 1",
                (value,),
            ).fetchone()
        return row is not None

    def reserve_next_task(self) -> Task | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT task_id, payload FROM tasks WHERE status = 'QUEUED' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload"])
            payload["status"] = "ALLOCATED"
            connection.execute(
                "UPDATE tasks SET status = 'ALLOCATED', payload = ? WHERE task_id = ?",
                (as_json(payload), row["task_id"]),
            )
        return Task.from_dict(payload)

    def update_task(self, task: Task) -> None:
        self.queue_task(task)

    def latest_cycle_number(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT MAX(cycle_number) AS max_cycle FROM round_results").fetchone()
        return int(row["max_cycle"] or 0)

    def save_round_result(self, result: RoundResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO round_results(round_id, cycle_number, executor_model_id, task_id, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.round_id,
                    result.cycle_number,
                    result.executor_model_id,
                    result.task["task_id"],
                    result.created_at.isoformat(),
                    as_json(result.to_dict()),
                ),
            )

    def list_recent_rounds(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM round_results ORDER BY cycle_number DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_market_snapshot(self, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO market_snapshots(created_at, payload) VALUES (?, ?)",
                (payload["created_at"], as_json(payload)),
            )

    def latest_market_snapshot(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM market_snapshots ORDER BY snapshot_id DESC LIMIT 1"
            ).fetchone()
        return None if row is None else json.loads(row["payload"])
