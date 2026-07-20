from __future__ import annotations

import re
from typing import Any

from openai import AsyncOpenAI

from .models import RequirementItem, SearchIntent

SEARCH_INTENT_PROMPT = (
    "Convert the user's natural-language GitHub project request into a task contract. "
    "Do not classify it into a fixed intent taxonomy. Infer what success means for this request. "
    "requirements are atomic, repository-verifiable success criteria. Never add a hard requirement "
    "the user did not express; set required=false for inferred preferences. evidence_sources names "
    "the evidence needed, such as repository_metadata, documentation, source_code, manifest, "
    "release_history, or citations. retrieval_terms contains 1 to 8 English evidence terms. "
    "Generate 3 to 6 genuinely complementary search_strategies as independent hypotheses, not "
    "fixed categories or mechanical keyword combinations. strategy_type is a short, freely chosen "
    "label. hypothesis explains why its results could satisfy the task. terms contains 1 to 3 "
    "English GitHub search phrases. expected_signals lists observable repository signals. verifies "
    "references requirement ids that the hypothesis can help verify. Treat a project named only "
    "as a similarity reference as context, never as a search term; search for its product category "
    "and capabilities instead. Every hypothesis must verify "
    "at least one criterion when criteria exist. Use known product names only when useful to this "
    "request; never force an alternatives angle. keywords contains 2 to 8 broad fallback terms and "
    "component_roles describes independently discoverable companion roles only when a "
    "multi-component solution is useful, such as mobile_sync, object_storage, or reverse_proxy. "
    "Each role includes "
    "search_terms, compatibility_interfaces, and the requirement ids it fulfills. "
    "no GitHub qualifiers. Ask one clarification question only when ambiguity would materially "
    "change the search direction."
)


async def parse_search_intent_with_llm(
    raw: str, client: AsyncOpenAI, model: str
) -> SearchIntent:
    response: Any = await client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SEARCH_INTENT_PROMPT},
            {"role": "user", "content": raw},
        ],
        text_format=SearchIntent,
    )
    parsed = response.output_parsed
    if not isinstance(parsed, SearchIntent):
        raise ValueError("LLM did not return SearchIntent")
    return remove_reference_project_names(parsed, raw)


_FALLBACK_CONCEPTS = (
    (
        r"(?:发现|寻找|推荐).{0,12}(?:仓库|repo)|"
        r"(?:仓库|repo).{0,8}(?:推荐|发现)|repository discovery",
        "repository discovery",
    ),
    (r"自然语言|natural language", "natural language search"),
    (r"开源软件|open.?source software", "open source software discovery"),
    (r"多源|multi.?source", "multi source search"),
    (r"项目比较|方案比较|project comparison", "project comparison"),
    (r"可验证引用|证据|verifiable citation|citation", "verifiable citations"),
    (r"研究报告|research report", "research report"),
    (r"本地部署|自托管|self.?host", "self hosted"),
    (r"docker|容器", "docker"),
    (r"照片|相册|photo", "photo management"),
    (r"人脸识别|face recognition", "face recognition"),
    (r"自动备份|automatic backup", "automatic backup"),
)


def _reference_project_names(raw: str) -> set[str]:
    patterns = (
        r"(?:与|和)\s*([A-Za-z][A-Za-z0-9_.-]{1,60})\s*(?:类似|同类)",
        r"(?:similar\s+to|like)\s+([A-Za-z][A-Za-z0-9_.-]{1,60})",
    )
    return {
        match.group(1).casefold()
        for pattern in patterns
        for match in re.finditer(pattern, raw, re.I)
    }


def remove_reference_project_names(intent: SearchIntent, raw: str) -> SearchIntent:
    references = _reference_project_names(raw)
    if not references:
        return intent

    def is_reference_term(term: str) -> bool:
        tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_.-]*", term.casefold()))
        return bool(tokens) and tokens <= references | {"alternative", "alternatives"}

    intent.keywords = [
        term for term in intent.keywords if not is_reference_term(term)
    ]
    for strategy in intent.search_strategies:
        strategy.terms = [
            term for term in strategy.terms if not is_reference_term(term)
        ]
    intent.search_strategies = [
        strategy for strategy in intent.search_strategies if strategy.terms
    ]
    return intent


def parse_search_intent_with_rules(raw: str) -> SearchIntent:
    lowered = raw.casefold()
    concepts = [
        english
        for pattern, english in _FALLBACK_CONCEPTS
        if re.search(pattern, lowered, re.I | re.S)
    ]
    english_tokens = list(
        dict.fromkeys(re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,30}", raw.lower()))
    )
    generic = {
        "find",
        "github",
        "repo",
        "repository",
        "project",
        "reposcout",
        "reposcoutagent",
        "tool",
    }
    keywords = list(
        dict.fromkeys([*concepts, *(item for item in english_tokens if item not in generic)])
    )[:8]
    requirements = [
        RequirementItem(
            id=f"fallback_{index}",
            description=concept,
            retrieval_terms=[concept],
            evidence_sources=["documentation"],
        )
        for index, concept in enumerate(concepts[1:], start=1)
    ][:8]
    intent = SearchIntent(
        goal=raw.strip(),
        requirements=requirements,
        keywords=keywords,
    )
    return remove_reference_project_names(intent, raw)
