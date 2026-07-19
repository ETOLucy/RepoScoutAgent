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
    if not keywords:
        raise ValueError("没有可用于 GitHub 搜索的关键词")
    query = " ".join([*(_quote(item) for item in keywords[:4]), *_qualifiers(intent)])
    return SearchPlan(
        queries=[SearchQuery(query=query, keywords=keywords[:4], fingerprint=_fingerprint(query))]
    )


def relax_github_query(query: str) -> str | None:
    parts = re.findall(r'"[^"]+"|\S+', query)
    qualifiers = [item for item in parts if ":" in item and not item.startswith('"')]
    text = [item.strip('"').split()[0] for item in parts if item not in qualifiers]
    relaxed = " ".join([*text[:2], *qualifiers])
    return relaxed if relaxed.lower() != query.lower() else None
