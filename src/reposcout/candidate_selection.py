from __future__ import annotations

from typing import Any

from .retrieval import tokenize
from .search.models import SearchIntent


def _candidate_score(intent: SearchIntent, candidate: dict[str, Any]) -> float:
    documents = candidate.get("documents", [])
    document_tokens = set(
        tokenize(" ".join(str(item.get("content", "")) for item in documents))
    )
    criteria_hits = 0
    for requirement in intent.requirements:
        terms = requirement.retrieval_terms or tokenize(requirement.description)
        if any(set(tokenize(term)) & document_tokens for term in terms):
            criteria_hits += 1
    coverage = criteria_hits / max(1, len(intent.requirements))
    implementation = min(
        1.0,
        sum(item.get("source_type") == "implementation" for item in documents) / 3,
    )
    repository_score = float(candidate.get("repository_ranking", {}).get("score", 0.0))
    return 0.55 * coverage + 0.25 * repository_score + 0.20 * implementation


def select_analysis_candidates(
    intent: SearchIntent,
    candidates: list[dict[str, Any]],
    *,
    limit: int = 12,
    exploration_slots: int = 4,
) -> list[dict[str, Any]]:
    if len(candidates) <= limit:
        return [
            {**item, "evidence_prefilter_score": round(_candidate_score(intent, item), 6)}
            for item in candidates
        ]
    scored = [
        {**item, "evidence_prefilter_score": round(_candidate_score(intent, item), 6)}
        for item in candidates
    ]
    scored.sort(key=lambda item: item["evidence_prefilter_score"], reverse=True)
    exploitation_count = max(1, limit - exploration_slots)
    selected = scored[:exploitation_count]
    selected_names = {item.get("full_name") for item in selected}
    covered_strategies = {
        strategy
        for item in selected
        for strategy in item.get("discovery", {}).get("strategy_types", [])
    }
    remaining = [item for item in scored if item.get("full_name") not in selected_names]
    remaining.sort(
        key=lambda item: (
            len(
                set(item.get("discovery", {}).get("strategy_types", []))
                - covered_strategies
            ),
            item["evidence_prefilter_score"],
        ),
        reverse=True,
    )
    selected.extend(remaining[: limit - len(selected)])
    return selected
