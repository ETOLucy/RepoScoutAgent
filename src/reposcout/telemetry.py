from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from time import perf_counter
from typing import Any

from .state import RepoScoutState

Node = Callable[[RepoScoutState], Any]


def timed_node(
    name: str, node: Node
) -> Callable[[RepoScoutState], Coroutine[Any, Any, dict[str, Any]]]:
    async def run(state: RepoScoutState) -> dict[str, Any]:
        started = perf_counter()
        outcome = node(state)
        result = await outcome if inspect.isawaitable(outcome) else outcome
        timings = dict(state.get("node_timings", {}))
        timings[name] = round((perf_counter() - started) * 1000, 2)
        return {**result, "node_timings": timings}

    return run
