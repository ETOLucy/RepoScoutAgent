from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

ContextMode = Literal["auto", "new", "refine"]

_HARD_NEW_MARKERS = (
    "新需求",
    "新的需求",
    "另外找",
    "另一个",
    "重新找",
    "换一个",
    "再找一个",
    "new task",
    "different project",
    "start over",
)
_REFINEMENT_MARKERS = (
    "改成",
    "换成",
    "再加",
    "增加",
    "补充",
    "不要",
    "去掉",
    "还要",
    "也要",
    "优先",
    "更重视",
    "上一个",
    "刚才",
    "前面",
    "instead",
    "also",
    "add ",
    "remove ",
    "prefer ",
    "without ",
)
_STANDALONE_PREFIXES = (
    "找一个",
    "找个",
    "想找",
    "我想找",
    "帮我找",
    "推荐一个",
    "寻找",
    "find ",
    "looking for ",
    "recommend ",
)


class ConversationStore:
    """SQLite-backed conversation state and message history."""

    def __init__(self, database_path: Path, max_turns: int = 8) -> None:
        self._database_path = database_path
        self._max_turns = max_turns
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    active_turns TEXT NOT NULL,
                    clarification TEXT,
                    turn_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at DESC);
                """
            )
            connection.commit()

    @staticmethod
    def _should_refine(
        active_turns: list[str],
        clarification: str | None,
        message: str,
        mode: ContextMode,
    ) -> bool:
        if mode == "new":
            return False
        if mode == "refine":
            return bool(active_turns)
        lowered = message.casefold().strip()
        if any(marker in lowered for marker in _HARD_NEW_MARKERS):
            return False
        if clarification:
            return True
        if any(marker in lowered for marker in _REFINEMENT_MARKERS):
            return True
        if any(lowered.startswith(prefix) for prefix in _STANDALONE_PREFIXES):
            return False
        return False

    def begin_turn(
        self,
        conversation_id: str | None,
        message: str,
        mode: ContextMode = "auto",
    ) -> tuple[str, str, int]:
        session_id = conversation_id or str(uuid4())
        clean_message = message.strip()
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT active_turns, clarification, turn_count
                FROM conversations WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            active_turns = json.loads(row["active_turns"]) if row else []
            clarification = row["clarification"] if row else None
            turn_count = int(row["turn_count"]) + 1 if row else 1
            refine = self._should_refine(
                active_turns, clarification, clean_message, mode
            )
            if refine:
                active_turns.append(clean_message)
            else:
                active_turns = [clean_message]
                clarification = None
            active_turns = active_turns[-self._max_turns :]
            title = clean_message[:80]
            if row:
                connection.execute(
                    """
                    UPDATE conversations
                    SET active_turns = ?, clarification = NULL,
                        turn_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(active_turns, ensure_ascii=False),
                        turn_count,
                        now,
                        session_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO conversations
                        (id, title, active_turns, clarification, turn_count,
                         created_at, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        session_id,
                        title,
                        json.dumps(active_turns, ensure_ascii=False),
                        turn_count,
                        now,
                        now,
                    ),
                )
            self._insert_message(
                connection, session_id, "user", clean_message, None, now
            )
            connection.commit()

        if len(active_turns) == 1:
            context = active_turns[0]
        else:
            turns = "\n".join(
                f"User turn {index}: {value}"
                for index, value in enumerate(active_turns, start=1)
            )
            previous_question = (
                f"\nThe system previously asked: {clarification}"
                if clarification
                else ""
            )
            context = (
                "Interpret only these active turns as one evolving project-search request. "
                "The last turn refines or overrides earlier active constraints.\n"
                f"{turns}{previous_question}"
            )
        return session_id, context, turn_count

    @staticmethod
    def _insert_message(
        connection: sqlite3.Connection,
        conversation_id: str,
        role: str,
        content: str,
        payload: dict[str, Any] | None,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                conversation_id,
                role,
                content,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if payload is not None
                else None,
                created_at,
            ),
        )

    def record_assistant(
        self, conversation_id: str, content: str, payload: dict[str, Any]
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            self._insert_message(
                connection, conversation_id, "assistant", content, payload, now
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            connection.commit()

    def record_user_event(self, conversation_id: str, content: str) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            self._insert_message(
                connection, conversation_id, "user", content.strip(), None, now
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            connection.commit()

    def record_clarification(self, conversation_id: str, question: str | None) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE conversations SET clarification = ? WHERE id = ?",
                (question, conversation_id),
            )
            connection.commit()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, title, turn_count, created_at, updated_at
                FROM conversations ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            conversation = connection.execute(
                """
                SELECT id, title, turn_count, created_at, updated_at
                FROM conversations WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                return None
            rows = connection.execute(
                """
                SELECT id, role, content, payload, created_at
                FROM messages WHERE conversation_id = ?
                ORDER BY created_at, rowid
                """,
                (conversation_id,),
            ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"]) if item["payload"] else None
            messages.append(item)
        return {**dict(conversation), "messages": messages}

    def reset(self, conversation_id: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            connection.commit()
