from typing import Any, TypedDict


class RepoScoutState(TypedDict, total=False):
    raw_requirement: str
    requirement: dict[str, Any]
    query: str
    candidates: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    report: str
    error: str
