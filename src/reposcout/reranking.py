from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI

from .search.models import SearchIntent


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,}", text.casefold()))


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return (
        sum(x * y for x, y in zip(left, right, strict=False)) / denominator if denominator else 0.0
    )


def task_contract_text(intent: SearchIntent) -> str:
    criteria = "\n".join(
        f"- {item.description}; evidence: {', '.join(item.evidence_sources)}"
        for item in intent.requirements
    )
    hypotheses = "\n".join(
        f"- {item.hypothesis or item.rationale}; expected: {', '.join(item.expected_signals)}"
        for item in intent.search_strategies
    )
    return f"Goal: {intent.goal}\nSuccess criteria:\n{criteria}\nSearch hypotheses:\n{hypotheses}"


def repository_text(repository: dict[str, Any]) -> str:
    return " ".join(
        [
            str(repository.get("full_name", "")),
            str(repository.get("description", "")),
            " ".join(str(item) for item in repository.get("topics", [])),
            str(repository.get("language", "")),
        ]
    )


def _freshness(repository: dict[str, Any]) -> float:
    raw = str(repository.get("pushed_at") or repository.get("updated_at") or "")
    try:
        updated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    days = max(0, (datetime.now(UTC) - updated).days)
    return max(0.0, 1.0 - days / 1460)


def _deterministic_score(
    contract: str, repository: dict[str, Any], max_query_hits: int
) -> tuple[float, dict[str, float]]:
    contract_tokens = _tokens(contract)
    repository_tokens = _tokens(repository_text(repository))
    lexical = len(contract_tokens & repository_tokens) / max(1, len(contract_tokens))
    query_hits = len(repository.get("discovery", {}).get("query_fingerprints", []))
    hypothesis_coverage = query_hits / max(1, max_query_hits)
    metadata = (
        sum(bool(repository.get(key)) for key in ("description", "topics", "language", "pushed_at"))
        / 4
    )
    prior = (
        0.55 * lexical
        + 0.30 * hypothesis_coverage
        + 0.10 * metadata
        + 0.05 * _freshness(repository)
    )
    return prior, {
        "lexical_contract_match": round(lexical, 6),
        "hypothesis_coverage": round(hypothesis_coverage, 6),
        "metadata_quality": round(metadata, 6),
        "freshness": round(_freshness(repository), 6),
    }


async def rerank_repositories(
    intent: SearchIntent,
    repositories: list[dict[str, Any]],
    client: AsyncOpenAI | None = None,
    embedding_model: str = "text-embedding-3-small",
) -> list[dict[str, Any]]:
    """Rank cheap repository metadata against the task contract before document fetches."""
    if not repositories:
        return []
    contract = task_contract_text(intent)
    max_query_hits = max(
        (len(item.get("discovery", {}).get("query_fingerprints", [])) for item in repositories),
        default=1,
    )
    semantic_scores = [0.0] * len(repositories)
    mode = "deterministic"
    if client:
        response = await client.embeddings.create(
            model=embedding_model,
            input=[contract, *(repository_text(item) for item in repositories)],
        )
        vectors = [item.embedding for item in response.data]
        semantic_scores = [_cosine(vectors[0], vector) for vector in vectors[1:]]
        mode = "semantic"

    ranked = []
    for repository, semantic in zip(repositories, semantic_scores, strict=True):
        prior, features = _deterministic_score(contract, repository, max_query_hits)
        score = 0.75 * max(0.0, semantic) + 0.25 * prior if client else prior
        ranked.append(
            {
                **repository,
                "repository_ranking": {
                    "score": round(score, 6),
                    "semantic_similarity": round(semantic, 6) if client else None,
                    "mode": mode,
                    **features,
                },
            }
        )
    return sorted(
        ranked,
        key=lambda item: item["repository_ranking"]["score"],
        reverse=True,
    )
