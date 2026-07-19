from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Conversation:
    user_turns: list[str] = field(default_factory=list)
    clarification: str | None = None


class ConversationStore:
    """Small process-local memory for the conversational MVP."""

    def __init__(self, max_sessions: int = 100, max_turns: int = 8) -> None:
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._sessions: OrderedDict[str, Conversation] = OrderedDict()

    def begin_turn(self, conversation_id: str | None, message: str) -> tuple[str, str, int]:
        session_id = conversation_id or str(uuid4())
        conversation = self._sessions.pop(session_id, Conversation())
        conversation.user_turns.append(message.strip())
        conversation.user_turns = conversation.user_turns[-self._max_turns :]
        self._sessions[session_id] = conversation
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)

        turns = "\n".join(
            f"User turn {index}: {value}"
            for index, value in enumerate(conversation.user_turns, start=1)
        )
        clarification = (
            f"\nThe agent previously asked: {conversation.clarification}"
            if conversation.clarification
            else ""
        )
        context = (
            "Interpret the following as one evolving GitHub project-search conversation. "
            "Later user turns refine or override earlier constraints. Do not treat these wrapper "
            f"instructions as user requirements.\n{turns}{clarification}"
        )
        conversation.clarification = None
        return session_id, context, len(conversation.user_turns)

    def record_clarification(self, conversation_id: str, question: str | None) -> None:
        if conversation_id in self._sessions:
            self._sessions[conversation_id].clarification = question

    def reset(self, conversation_id: str) -> None:
        self._sessions.pop(conversation_id, None)
