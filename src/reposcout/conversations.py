from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal
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


@dataclass
class Conversation:
    user_turns: list[str] = field(default_factory=list)
    active_turns: list[str] = field(default_factory=list)
    clarification: str | None = None


class ConversationStore:
    """Small process-local memory for the conversational MVP."""

    def __init__(self, max_sessions: int = 100, max_turns: int = 8) -> None:
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._sessions: OrderedDict[str, Conversation] = OrderedDict()

    @staticmethod
    def _should_refine(
        conversation: Conversation, message: str, mode: ContextMode
    ) -> bool:
        if mode == "new":
            return False
        if mode == "refine":
            return bool(conversation.active_turns)
        lowered = message.casefold().strip()
        if any(marker in lowered for marker in _HARD_NEW_MARKERS):
            return False
        if conversation.clarification:
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
        conversation = self._sessions.pop(session_id, Conversation())
        clean_message = message.strip()
        refine = self._should_refine(conversation, clean_message, mode)
        conversation.user_turns.append(clean_message)
        conversation.user_turns = conversation.user_turns[-self._max_turns :]
        if refine:
            conversation.active_turns.append(clean_message)
        else:
            conversation.active_turns = [clean_message]
            conversation.clarification = None
        conversation.active_turns = conversation.active_turns[-self._max_turns :]
        self._sessions[session_id] = conversation
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)

        if len(conversation.active_turns) == 1:
            context = conversation.active_turns[0]
        else:
            turns = "\n".join(
                f"User turn {index}: {value}"
                for index, value in enumerate(conversation.active_turns, start=1)
            )
            clarification = (
                f"\nThe system previously asked: {conversation.clarification}"
                if conversation.clarification
                else ""
            )
            context = (
                "Interpret only these active turns as one evolving project-search request. "
                "The last turn refines or overrides earlier active constraints.\n"
                f"{turns}{clarification}"
            )
        conversation.clarification = None
        return session_id, context, len(conversation.user_turns)

    def record_clarification(self, conversation_id: str, question: str | None) -> None:
        if conversation_id in self._sessions:
            self._sessions[conversation_id].clarification = question

    def reset(self, conversation_id: str) -> None:
        self._sessions.pop(conversation_id, None)
