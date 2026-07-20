from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from .nodes import (
    deep_code_search,
    generate_report,
    inspect_documents,
    match_documents,
    plan_search,
    prepare_evidence,
    rank_candidates,
    request_clarification,
    review_requirement,
    search_github,
    understand_requirement,
    validate_request,
)
from .state import RepoScoutState
from .telemetry import timed_node


def _timed(name: str, node: Any) -> Any:
    # LangGraph's overloaded node protocol cannot represent this async decorator.
    return cast(Any, timed_node(name, node))


def _route_validation(state: RepoScoutState) -> str:
    return "invalid" if state.get("error") else "understand"


def _route_intent(state: RepoScoutState) -> str:
    if state.get("error"):
        return "invalid"
    if state.get("interactive") and not state.get("requirement_reviewed"):
        return "review"
    return "clarify" if state.get("clarification_questions") else "plan"


def _invalid_request(state: RepoScoutState) -> dict[str, str]:
    return {"report": state.get("error", "需求无效。")}


def _route_deep_code_search(state: RepoScoutState) -> str:
    return "deep" if state.get("deep_code_search") else "report"


def build_graph() -> Any:
    builder = StateGraph(RepoScoutState)
    builder.add_node("validate_request", _timed("validate_request", validate_request))
    builder.add_node("invalid_request", _invalid_request)
    builder.add_node(
        "understand_requirement",
        _timed("understand_requirement", understand_requirement),
    )
    builder.add_node("request_clarification", request_clarification)
    builder.add_node("review_requirement", review_requirement)
    builder.add_node("plan_search", _timed("plan_search", plan_search))
    builder.add_node("search_github", _timed("search_github", search_github))
    builder.add_node("rank_candidates", _timed("rank_candidates", rank_candidates))
    builder.add_node(
        "inspect_documents", _timed("inspect_documents", inspect_documents)
    )
    builder.add_node("prepare_evidence", _timed("prepare_evidence", prepare_evidence))
    builder.add_node("match_documents", _timed("match_documents", match_documents))
    builder.add_node(
        "deep_code_search", _timed("deep_code_search", deep_code_search)
    )
    builder.add_node("generate_report", _timed("generate_report", generate_report))

    builder.add_edge(START, "validate_request")
    builder.add_conditional_edges(
        "validate_request",
        _route_validation,
        {"invalid": "invalid_request", "understand": "understand_requirement"},
    )
    builder.add_conditional_edges(
        "understand_requirement",
        _route_intent,
        {
            "invalid": "invalid_request",
            "review": "review_requirement",
            "clarify": "request_clarification",
            "plan": "plan_search",
        },
    )
    builder.add_edge("invalid_request", END)
    builder.add_edge("request_clarification", END)
    builder.add_edge("review_requirement", END)
    builder.add_edge("plan_search", "search_github")
    builder.add_edge("search_github", "rank_candidates")
    builder.add_edge("rank_candidates", "inspect_documents")
    builder.add_edge("inspect_documents", "prepare_evidence")
    builder.add_edge("prepare_evidence", "match_documents")
    builder.add_conditional_edges(
        "match_documents",
        _route_deep_code_search,
        {"deep": "deep_code_search", "report": "generate_report"},
    )
    builder.add_edge("deep_code_search", "generate_report")
    builder.add_edge("generate_report", END)
    return builder.compile()
