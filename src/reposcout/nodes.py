from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from .github_client import GitHubSearchError, search_repositories
from .state import RepoScoutState

LANGUAGES = {
    "python": "Python",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "java": "Java",
    "go": "Go",
    "rust": "Rust",
}

STOP_WORDS = {
    "我想",
    "一个",
    "项目",
    "适合",
    "使用",
    "最好",
    "希望",
    "需要",
    "开发",
    "学习",
    "github",
}


def parse_requirement(state: RepoScoutState) -> dict[str, Any]:
    raw = state.get("raw_requirement", "").strip()
    if len(raw) < 4:
        return {"error": "请至少描述项目用途、技术方向或希望解决的问题。"}

    lowered = raw.lower()
    language = next((value for key, value in LANGUAGES.items() if key in lowered), None)
    star_match = re.search(r"(?:至少|最低|不少于|>=?)\s*(\d+)\s*(?:stars?|星)?", lowered)
    minimum_stars = int(star_match.group(1)) if star_match else 0
    active_days = 180 if any(word in raw for word in ("半年", "近期", "活跃", "维护")) else None

    ascii_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,30}", raw)
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", raw)
    terms: list[str] = []
    for term in [*ascii_terms, *chinese_terms]:
        normalized = term.lower()
        if normalized not in STOP_WORDS and normalized not in terms:
            terms.append(normalized)

    return {
        "requirement": {
            "language": language,
            "minimum_stars": minimum_stars,
            "active_within_days": active_days,
            "keywords": terms[:6],
        }
    }


def build_query(requirement: dict[str, Any]) -> str:
    keywords = requirement.get("keywords") or ["agent"]
    query_terms = keywords[:4]
    if requirement.get("language"):
        query_terms.append(f"language:{requirement['language']}")
    if requirement.get("minimum_stars"):
        query_terms.append(f"stars:>={requirement['minimum_stars']}")
    return " ".join(query_terms)


def search_github(state: RepoScoutState) -> dict[str, Any]:
    query = build_query(state["requirement"])
    try:
        return {"query": query, "candidates": search_repositories(query)}
    except GitHubSearchError as exc:
        return {"query": query, "candidates": [], "error": str(exc)}


def rank_candidates(state: RepoScoutState) -> dict[str, Any]:
    requirement = state["requirement"]
    keywords = [item.lower() for item in requirement.get("keywords", [])]
    now = datetime.now(timezone.utc)
    ranked: list[dict[str, Any]] = []

    for candidate in state.get("candidates", []):
        searchable = " ".join(
            [
                candidate["full_name"],
                candidate["description"],
                " ".join(candidate["topics"]),
            ]
        ).lower()
        matched = [keyword for keyword in keywords if keyword in searchable]
        relevance = min(50, 15 + 10 * len(matched))
        popularity = min(20, math.log10(candidate["stars"] + 1) * 6)
        updated = datetime.fromisoformat(candidate["updated_at"].replace("Z", "+00:00"))
        age_days = max(0, (now - updated).days)
        freshness = max(0, 20 - age_days / 36)
        risk_penalty = 35 if candidate["archived"] else 0
        score = max(0, round(relevance + popularity + freshness + 10 - risk_penalty, 1))

        reasons = []
        if matched:
            reasons.append(f"匹配关键词：{', '.join(matched[:3])}")
        if age_days <= 180:
            reasons.append("最近半年仍有更新")
        if candidate["stars"] >= 100:
            reasons.append("具备一定社区基础")

        enriched = {
            **candidate,
            "score": score,
            "matched_keywords": matched,
            "reasons": reasons or ["与当前检索条件具有基础相关性"],
            "risks": ["仓库已归档，不建议作为新项目基础"] if candidate["archived"] else [],
        }
        ranked.append(enriched)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"recommendations": ranked[:6]}


def generate_report(state: RepoScoutState) -> dict[str, Any]:
    if state.get("error"):
        return {"report": state["error"]}
    if not state.get("recommendations"):
        return {"report": "没有找到满足当前条件的仓库，请减少限定条件后重试。"}
    return {
        "report": (
            f"使用查询 `{state['query']}` 找到 {len(state['candidates'])} 个候选，"
            f"当前展示评分最高的 {len(state['recommendations'])} 个结果。"
        )
    }
