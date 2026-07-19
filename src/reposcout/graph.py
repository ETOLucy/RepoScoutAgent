from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import (
    generate_report,
    inspect_documents,
    match_documents,
    plan_search,
    prepare_evidence,
    rank_candidates,
    request_clarification,
    search_github,
    understand_requirement,
    validate_request,
)
from .state import RepoScoutState


def _route_validation(state: RepoScoutState) -> str:
    return "invalid" if state.get("error") else "understand"


def _route_intent(state: RepoScoutState) -> str:
    if state.get("error"):
        return "invalid"
    return "clarify" if state.get("clarification_questions") else "plan"


def _invalid_request(state: RepoScoutState) -> dict[str, str]:
    return {"report": state.get("error", "需求无效。")}


def build_graph() -> Any:
    builder = StateGraph(RepoScoutState)
    builder.add_node("validate_request", validate_request)
    builder.add_node("invalid_request", _invalid_request)
    builder.add_node("understand_requirement", understand_requirement)
    builder.add_node("request_clarification", request_clarification)
    builder.add_node("plan_search", plan_search)
    builder.add_node("search_github", search_github)
    builder.add_node("rank_candidates", rank_candidates)
    builder.add_node("inspect_documents", inspect_documents)
    builder.add_node("prepare_evidence", prepare_evidence)
    builder.add_node("match_documents", match_documents)
    builder.add_node("generate_report", generate_report)

    builder.add_edge(START, "validate_request")
    builder.add_conditional_edges(
        "validate_request",
        _route_validation,
        {"invalid": "invalid_request", "understand": "understand_requirement"},
    )
    builder.add_conditional_edges(
        "understand_requirement",
        _route_intent,
        {"invalid": "invalid_request", "clarify": "request_clarification", "plan": "plan_search"},
    )
    builder.add_edge("invalid_request", END)
    builder.add_edge("request_clarification", END)
    builder.add_edge("plan_search", "search_github")
    builder.add_edge("search_github", "rank_candidates")
    builder.add_edge("rank_candidates", "inspect_documents")
    builder.add_edge("inspect_documents", "prepare_evidence")
    builder.add_edge("prepare_evidence", "match_documents")
    builder.add_edge("match_documents", "generate_report")
    builder.add_edge("generate_report", END)
    return builder.compile()
