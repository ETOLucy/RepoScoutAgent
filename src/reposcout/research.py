from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class ResearchStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_tasks (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    query TEXT NOT NULL,
                    solution_count INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    state TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(research_tasks)"
                ).fetchall()
            }
            if "status" not in columns:
                connection.execute(
                    "ALTER TABLE research_tasks "
                    "ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'"
                )
            if "state" not in columns:
                connection.execute("ALTER TABLE research_tasks ADD COLUMN state TEXT")
            connection.commit()

    def save(
        self, conversation_id: str, query: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        research_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        stored = {**payload, "research_id": research_id, "created_at": created_at}
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO research_tasks
                    (id, conversation_id, created_at, query, solution_count,
                     payload, status, state)
                VALUES (?, ?, ?, ?, ?, ?, 'completed', NULL)
                """,
                (
                    research_id,
                    conversation_id,
                    created_at,
                    query,
                    len(payload.get("solutions", [])),
                    json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.commit()
        return stored

    def save_checkpoint(
        self,
        conversation_id: str,
        query: str,
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        research_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        stored = {**payload, "research_id": research_id, "created_at": created_at}
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO research_tasks
                    (id, conversation_id, created_at, query, solution_count,
                     payload, status, state)
                VALUES (?, ?, ?, ?, 0, ?, 'pending', ?)
                """,
                (
                    research_id,
                    conversation_id,
                    created_at,
                    query,
                    json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(state, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.commit()
        return stored

    def resume_state(self, research_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT state FROM research_tasks
                WHERE id = ? AND status = 'pending'
                """,
                (research_id,),
            ).fetchone()
        return json.loads(row["state"]) if row and row["state"] else None

    def update_checkpoint(
        self,
        research_id: str,
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        stored = {
            **payload,
            "research_id": research_id,
            "created_at": payload.get("created_at", datetime.now(UTC).isoformat()),
        }
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE research_tasks SET payload = ?, state = ?
                WHERE id = ? AND status = 'pending'
                """,
                (
                    json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(state, ensure_ascii=False, separators=(",", ":")),
                    research_id,
                ),
            )
            connection.commit()
        if cursor.rowcount != 1:
            raise KeyError(research_id)
        return stored

    def complete(self, research_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        stored = {
            **payload,
            "research_id": research_id,
            "created_at": payload.get("created_at", created_at),
        }
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE research_tasks
                SET solution_count = ?, payload = ?, status = 'completed', state = NULL
                WHERE id = ? AND status = 'pending'
                """,
                (
                    len(payload.get("solutions", [])),
                    json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                    research_id,
                ),
            )
            connection.commit()
        if cursor.rowcount != 1:
            raise KeyError(research_id)
        return stored

    def get(self, research_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM research_tasks WHERE id = ?", (research_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, created_at, query, solution_count, status
                FROM research_tasks ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
