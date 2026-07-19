from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from .github_client import GitHubSearchError, get_rate_limit, search_repositories
from .state import RepoScoutState

load_dotenv()

LANGUAGES = {
    "python": "Python",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "java": "Java",
    "go": "Go",
    "rust": "Rust",
}

LICENSE_ALIASES = {
    "mit": "MIT",
    "apache": "Apache-2.0",
    "gpl": "GPL-3.0",
    "bsd": "BSD-3-Clause",
    "unlicense": "Unlicense",
    "mpl": "MPL-2.0",
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
    "license",
    "许可证",
}


class RepositoryRequirement(BaseModel):
    language: str | None = None
    minimum_stars: int = Field(0, ge=0)
    active_within_days: int | None = None
    keywords: list[str] = Field(default_factory=list)
    licenses: list[str] = Field(default_factory=list)
    hard_conditions: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: list[str] = Field(default_factory=list)
    sort_targets: list[str] = Field(default_factory=list)


def _openai_client() -> OpenAI:
    return OpenAI()


def _normalize_terms(raw: str) -> list[str]:
    ascii_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,30}", raw)
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", raw)
    terms: list[str] = []
    for term in [*ascii_terms, *chinese_terms]:
        normalized = term.lower()
        if normalized not in STOP_WORDS and normalized not in terms:
            terms.append(normalized)
    return terms[:6]


def _detect_licenses(raw: str) -> list[str]:
    found: list[str] = []
    lowered = raw.lower()
    for alias, name in LICENSE_ALIASES.items():
        if alias in lowered and name not in found:
            found.append(name)
    return found


def _detect_sort_targets(raw: str) -> list[str]:
    targets: list[str] = []
    lowered = raw.lower()
    mapping = {
        "活跃": "freshness",
        "热门": "popularity",
        "最新": "freshness",
        "最优": "quality",
        "最适合": "relevance",
        "轻量": "lightweight",
        "稳定": "stability",
    }
    for key, value in mapping.items():
        if key in lowered and value not in targets:
            targets.append(value)
    return targets


def _detect_soft_preferences(raw: str, keywords: list[str]) -> list[str]:
    preference_markers = ["最好", "prefer", "preferably", "希望", "建议", "ideal"]
    if any(marker in raw.lower() for marker in preference_markers):
        return keywords
    return []


def _validate_requirement(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        req = RepositoryRequirement.model_validate(payload)
        return req.model_dump()
    except ValidationError:
        return None


def llm_parse_requirement(state: RepoScoutState) -> dict[str, Any]:
    raw = state.get("raw_requirement", "").strip()
    if len(raw) < 4:
        return {"error": "请至少描述项目用途、技术方向或希望解决的问题。"}

    if not os.getenv("OPENAI_API_KEY"):
        fallback = parse_requirement(state)
        fallback["requirement_parser"] = "rules"
        return fallback

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个结构化需求解析器。将用户输入解析为 JSON。"
                " 返回字段：language, minimum_stars, active_within_days, keywords, licenses, hard_conditions, soft_preferences, sort_targets。"
                " 如果无法确定，请返回 null 或空列表，不要写解释文本。"
            ),
        },
        {"role": "user", "content": raw},
    ]

    try:
        response = _openai_client().responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=messages,
            text_format=RepositoryRequirement,
        )
        parsed = response.output_parsed
        if parsed:
            validated = parsed.model_dump()
            if not validated["keywords"]:
                validated["keywords"] = _normalize_terms(raw)
            return {"requirement": validated, "requirement_parser": "llm"}
        failure_reason = "LLM 未返回可校验的结构化需求"
    except Exception as exc:
        failure_reason = f"LLM 需求解析失败，已降级为规则解析：{type(exc).__name__}"

    fallback = parse_requirement(state)
    requirement = fallback.get("requirement", {})
    requirement.setdefault("licenses", [])
    requirement.setdefault("hard_conditions", {})
    requirement.setdefault("soft_preferences", [])
    requirement.setdefault("sort_targets", [])
    return {
        "requirement": requirement,
        "requirement_parser": "rules_fallback",
        "warnings": [failure_reason],
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
    licenses = _detect_licenses(raw)
    keywords = _normalize_terms(raw)
    sort_targets = _detect_sort_targets(raw)
    soft_preferences = _detect_soft_preferences(raw, keywords)

    hard_conditions: dict[str, Any] = {}
    if language:
        hard_conditions["language"] = language
    if minimum_stars:
        hard_conditions["minimum_stars"] = minimum_stars
    if active_days:
        hard_conditions["active_within_days"] = active_days
    if licenses:
        hard_conditions["licenses"] = licenses

    requirement = RepositoryRequirement(
        language=language,
        minimum_stars=minimum_stars,
        active_within_days=active_days,
        keywords=keywords[:6],
        licenses=licenses,
        hard_conditions=hard_conditions,
        soft_preferences=soft_preferences,
        sort_targets=sort_targets,
    ).model_dump()

    return {"requirement": requirement, "requirement_parser": "rules"}


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
        candidates = search_repositories(query)
    except GitHubSearchError as exc:
        return {"query": query, "candidates": [], "error": str(exc)}

    rate_limit: dict[str, Any] = {}
    try:
        rate_limit = get_rate_limit()
    except GitHubSearchError:
        rate_limit = {}

    return {"query": query, "candidates": candidates, "rate_limit": rate_limit}


def _parse_github_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hard_constraint_violations(
    candidate: dict[str, Any],
    requirement: dict[str, Any],
    now: datetime,
) -> list[str]:
    violations: list[str] = []
    language = requirement.get("language")
    if language and (candidate.get("language") or "").lower() != language.lower():
        violations.append(f"语言不是 {language}")

    minimum_stars = requirement.get("minimum_stars", 0)
    if candidate.get("stars", 0) < minimum_stars:
        violations.append(f"Star 少于 {minimum_stars}")

    licenses = requirement.get("licenses") or []
    if licenses and candidate.get("license") not in licenses:
        violations.append(f"License 不在允许范围：{', '.join(licenses)}")

    if candidate.get("archived"):
        violations.append("仓库已归档")

    active_days = requirement.get("active_within_days")
    if active_days:
        pushed_at = _parse_github_datetime(candidate.get("pushed_at", ""))
        if pushed_at is None:
            violations.append("缺少最近代码推送时间")
        elif (now - pushed_at).days > active_days:
            violations.append(f"最近 {active_days} 天没有代码推送")

    return violations


def rank_candidates(state: RepoScoutState) -> dict[str, Any]:
    requirement = state["requirement"]
    keywords = [item.lower() for item in requirement.get("keywords", [])]
    now = datetime.now(timezone.utc)
    ranked: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in state.get("candidates", []):
        violations = _hard_constraint_violations(candidate, requirement, now)
        if violations:
            rejected.append(
                {
                    "full_name": candidate.get("full_name", "unknown"),
                    "reasons": violations,
                }
            )
            continue

        searchable = " ".join(
            [
                candidate.get("full_name", ""),
                candidate.get("description", ""),
                " ".join(candidate.get("topics", [])),
            ]
        ).lower()
        matched = [keyword for keyword in keywords if keyword in searchable]
        relevance = min(50, 15 + 10 * len(matched))
        popularity = min(20, math.log10(candidate.get("stars", 0) + 1) * 6)
        pushed_at = _parse_github_datetime(candidate.get("pushed_at", ""))
        age_days = max(0, (now - pushed_at).days) if pushed_at else 3650
        freshness = max(0, 20 - age_days / 36)
        score = max(0, round(relevance + popularity + freshness + 10, 1))

        reasons = []
        if matched:
            reasons.append(f"匹配关键词：{', '.join(matched[:3])}")
        if age_days <= 180:
            reasons.append("最近半年仍有更新")
        if candidate.get("stars", 0) >= 100:
            reasons.append("具备一定社区基础")

        enriched = {
            **candidate,
            "score": score,
            "matched_keywords": matched,
            "reasons": reasons or ["与当前检索条件具有基础相关性"],
            "risks": [],
        }
        ranked.append(enriched)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"recommendations": ranked[:6], "rejected_candidates": rejected}


def generate_report(state: RepoScoutState) -> dict[str, Any]:
    if state.get("error"):
        result = {"report": state["error"]}
    elif not state.get("recommendations"):
        result = {"report": "没有找到满足当前条件的仓库，请减少限定条件后重试。"}
    else:
        result = {
            "report": (
                f"使用查询 `{state['query']}` 找到 {len(state['candidates'])} 个候选，"
                f"硬条件过滤 {len(state.get('rejected_candidates', []))} 个，"
                f"当前展示评分最高的 {len(state['recommendations'])} 个结果。"
            )
        }

    if "rate_limit" in state:
        result["rate_limit"] = state["rate_limit"]
    if state.get("warnings"):
        result["warnings"] = state["warnings"]

    return result
