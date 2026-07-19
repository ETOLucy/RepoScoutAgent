from langgraph.graph import END, START, StateGraph

from .nodes import generate_report, parse_requirement, rank_candidates, search_github
from .state import RepoScoutState


def route_requirement(state: RepoScoutState) -> str:
    return "invalid" if state.get("error") else "search"


def invalid_request(state: RepoScoutState) -> dict[str, str]:
    return {"report": state.get("error", "需求无效。")}


def build_graph():
    builder = StateGraph(RepoScoutState)
    builder.add_node("parse_requirement", parse_requirement)
    builder.add_node("invalid_request", invalid_request)
    builder.add_node("search_github", search_github)
    builder.add_node("rank_candidates", rank_candidates)
    builder.add_node("generate_report", generate_report)

    builder.add_edge(START, "parse_requirement")
    builder.add_conditional_edges(
        "parse_requirement",
        route_requirement,
        {"invalid": "invalid_request", "search": "search_github"},
    )
    builder.add_edge("invalid_request", END)
    builder.add_edge("search_github", "rank_candidates")
    builder.add_edge("rank_candidates", "generate_report")
    builder.add_edge("generate_report", END)
    return builder.compile()
