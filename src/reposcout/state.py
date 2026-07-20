from typing import Any, TypedDict


class RepoScoutState(TypedDict, total=False):
    raw_requirement: str
    conversation_id: str
    deep_code_search: bool
    allow_requirement_fallback: bool
    interactive: bool
    requirement_reviewed: bool
    interaction: dict[str, Any]
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
    node_timings: dict[str, float]
    rejected_candidates: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    component_candidates: list[dict[str, Any]]
    solutions: list[dict[str, Any]]
    evidence_matrix: dict[str, Any]
    code_understanding: list[dict[str, Any]]
    warnings: list[str]
    report: str
    error: str
    rate_limit: dict[str, Any]
