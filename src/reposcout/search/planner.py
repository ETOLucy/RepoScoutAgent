from __future__ import annotations

import re
from typing import Any

from openai import AsyncOpenAI

from .models import SearchIntent

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
    "references requirement ids that the hypothesis can help verify. Every hypothesis must verify "
    "at least one criterion when criteria exist. Use known product names only when useful to this "
    "request; never force an alternatives angle. keywords contains 2 to 8 broad fallback terms and "
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
    return parsed


def parse_search_intent_with_rules(raw: str) -> SearchIntent:
    keywords = list(
        dict.fromkeys(re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,30}", raw.lower()))
    )[:8]
    return SearchIntent(goal=raw.strip(), keywords=keywords)
