from typing import Any, TypedDict


class RepoScoutState(TypedDict, total=False):
    raw_requirement: str
    requirement: dict[str, Any]
    requirement_parser: str
    search_intent: dict[str, Any]
    clarification_questions: list[str]
    search_plan: dict[str, Any]
    queries: list[dict[str, Any]]
    query: str
    candidates: list[dict[str, Any]]
    document_candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    warnings: list[str]
    report: str
    error: str
    rate_limit: dict[str, Any]
