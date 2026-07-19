from __future__ import annotations

import re
from typing import Any

from openai import OpenAI

from .models import SearchIntent

SEARCH_INTENT_PROMPT = (
    "将用户想在 GitHub 寻找项目的自然语言需求转换为 SearchIntent。"
    "requirements 保存可由仓库文档验证的原子需求，每项生成稳定短 id，并区分 required。"
    "keywords 生成 2 到 8 个适合 GitHub repository search 的简短英文关键词，"
    "只表达项目类别、核心能力和技术生态，不包含 stars/license/language 等 qualifier。"
    "不得添加用户未表达的产品、功能或数值限制。只有歧义会改变搜索方向时才追问一次。"
)


def parse_search_intent_with_llm(raw: str, client: OpenAI, model: str) -> SearchIntent:
    response: Any = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SEARCH_INTENT_PROMPT},
            {"role": "user", "content": raw},
        ],
        text_format=SearchIntent,
    )
    parsed = response.output_parsed
    if not isinstance(parsed, SearchIntent):
        raise ValueError("LLM 未返回 SearchIntent")
    return parsed


def parse_search_intent_with_rules(raw: str) -> SearchIntent:
    keywords = list(
        dict.fromkeys(re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,30}", raw.lower()))
    )[:8]
    return SearchIntent(goal=raw.strip(), keywords=keywords)
