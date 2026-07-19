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
    executed_queries: list[str]
    candidates: list[dict[str, Any]]
    ranked_candidates: list[dict[str, Any]]
    document_candidates: list[dict[str, Any]]
    analysis_candidates: list[dict[str, Any]]
    effective_retrieval_mode: str
    embedding_available: bool
    rejected_candidates: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    warnings: list[str]
    report: str
    error: str
    rate_limit: dict[str, Any]
