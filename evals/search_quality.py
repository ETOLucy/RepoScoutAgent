from __future__ import annotations

import math
from typing import Any


def recall_at_k(ranked_names: list[str], relevant_names: set[str], k: int) -> float:
    if not relevant_names:
        return 1.0
    return len(set(ranked_names[:k]) & relevant_names) / len(relevant_names)


def ndcg_at_k(ranked_names: list[str], relevance: dict[str, int], k: int) -> float:
    gains = [relevance.get(name, 0) for name in ranked_names[:k]]
    dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / idcg if idcg else 1.0


def evaluate_search_stages(
    discovered_names: list[str],
    ranked_names: list[str],
    relevance: dict[str, int],
    inspect_k: int = 24,
    inspected_names: list[str] | None = None,
    analyzed_names: list[str] | None = None,
) -> dict[str, Any]:
    """Expose which search stage lost relevant repositories."""
    relevant = {name for name, grade in relevance.items() if grade > 0}
    result = {
        "candidate_recall": recall_at_k(discovered_names, relevant, len(discovered_names)),
        "recall_at_inspection_cutoff": recall_at_k(ranked_names, relevant, inspect_k),
        "ndcg_at_inspection_cutoff": ndcg_at_k(ranked_names, relevance, inspect_k),
        "relevant_not_discovered": sorted(relevant - set(discovered_names)),
        "relevant_dropped_before_inspection": sorted(
            (relevant & set(discovered_names)) - set(ranked_names[:inspect_k])
        ),
    }
    if analyzed_names is not None:
        eligible = relevant & set(inspected_names or ranked_names[:inspect_k])
        result["recall_at_analysis_cutoff"] = recall_at_k(
            analyzed_names, eligible, len(analyzed_names)
        )
        result["relevant_dropped_before_analysis"] = sorted(
            eligible - set(analyzed_names)
        )
    return result
