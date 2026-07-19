from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from .models import SearchIntent, SearchPlan, SearchQuery


def _fingerprint(query: str) -> str:
    return hashlib.sha256(" ".join(query.lower().split()).encode()).hexdigest()[:16]


def _quote(term: str) -> str:
    clean = " ".join(term.replace('"', "").split())
    return f'"{clean}"' if " " in clean else clean


def _qualifiers(intent: SearchIntent) -> list[str]:
    result = ["archived:false"]
    if intent.language:
        result.append(f"language:{intent.language}")
    if intent.minimum_stars:
        result.append(f"stars:>={intent.minimum_stars}")
    result.extend(f"license:{item.lower()}" for item in intent.licenses[:2])
    if intent.active_within_days:
        pushed_after = datetime.now(UTC).date() - timedelta(days=intent.active_within_days)
        result.append(f"pushed:>={pushed_after.isoformat()}")
    return result


def compile_search_plan(intent: SearchIntent) -> SearchPlan:
    keywords = list(dict.fromkeys(item.strip() for item in intent.keywords if item.strip()))[:8]
    if not keywords and not intent.search_strategies:
        raise ValueError("没有可用于 GitHub 搜索的关键词")
    qualifiers = _qualifiers(intent)
    strategies: list[tuple[list[str], str, str, str, list[str], list[str]]] = [
        (
            strategy.terms,
            strategy.strategy_type,
            strategy.rationale,
            strategy.hypothesis,
            strategy.expected_signals,
            strategy.verifies,
        )
        for strategy in intent.search_strategies
    ]
    if not strategies:
        term_sets: list[list[str]] = [keywords[:2]]
        term_sets.extend([[keywords[0], keyword] for keyword in keywords[2:5]])
        term_sets.extend([[keyword] for keyword in keywords[1:4]])
        for requirement in intent.requirements:
            if requirement.retrieval_terms:
                term_sets.append([keywords[0], requirement.retrieval_terms[0]])
        strategies = [
            (
                terms,
                "rules_fallback",
                "Deterministic query because LLM strategy is unavailable",
                "",
                [],
                [],
            )
            for terms in term_sets
        ]

    queries: list[SearchQuery] = []
    seen: set[str] = set()
    for terms, strategy_type, rationale, hypothesis, expected_signals, verifies in strategies:
        unique_terms = list(dict.fromkeys(item.strip() for item in terms if item.strip()))[:3]
        if not unique_terms:
            continue
        query = " ".join([*(_quote(item) for item in unique_terms), *qualifiers])
        fingerprint = _fingerprint(query)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        queries.append(
            SearchQuery(
                query=query,
                keywords=unique_terms,
                fingerprint=fingerprint,
                strategy_type=strategy_type,
                rationale=rationale,
                hypothesis=hypothesis,
                expected_signals=expected_signals,
                verifies=verifies,
            )
        )
        if len(queries) == 6:
            break
    return SearchPlan(
        queries=queries,
        max_results=60,
        max_documents_per_repository=6,
        max_repositories_to_analyze=24,
    )


def relax_github_query(query: str) -> str | None:
    parts = re.findall(r'"[^"]+"|\S+', query)
    qualifiers = [item for item in parts if ":" in item and not item.startswith('"')]
    text = [item.strip('"').split()[0] for item in parts if item not in qualifiers]
    relaxed = " ".join([*text[:2], *qualifiers])
    return relaxed if relaxed.lower() != query.lower() else None
