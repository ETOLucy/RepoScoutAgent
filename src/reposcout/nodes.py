from __future__ import annotations

import asyncio
import math
import os
import re
from contextlib import suppress
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .architecture import infer_component_roles
from .candidate_selection import select_analysis_candidates
from .code_understanding import (
    CODE_EXPLANATION_PROMPT,
    CodeExplanation,
    build_repo_map,
    choose_code_inspection_budget,
    code_understanding_result,
    deterministic_code_explanation,
    validate_code_explanation,
)
from .compatibility import extract_compatibility_evidence
from .evidence import (
    ASSESSMENT_PROMPT,
    rule_assessment,
    validate_evidence,
    validate_implementation_evidence,
)
from .github_client import (
    GitHubSearchError,
    get_github_client,
)
from .reranking import (
    close_embedding_circuit,
    embedding_circuit_open,
    open_embedding_circuit,
    rerank_repositories,
)
from .retrieval import (
    format_requirement_context,
    prewarm_retrieval_embeddings,
    retrieve_for_requirements,
    retrieve_for_requirements_lexical,
    unique_retrieved_chunks,
)
from .search import (
    RepositoryAssessment,
    SearchIntent,
    compile_search_plan,
    parse_search_intent_with_llm,
    parse_search_intent_with_rules,
    relax_github_query,
)
from .search.models import CriterionMatch
from .solutions import build_evidence_matrix, build_solutions
from .state import RepoScoutState
from .web_search import WebSearchError, get_web_search_client

load_dotenv()

_requirement_timeout_seconds = 15.0


def set_requirement_timeout(seconds: float) -> None:
    global _requirement_timeout_seconds
    _requirement_timeout_seconds = seconds

LANGUAGES = {
    "python": "Python",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "java": "Java",
    "golang": "Go",
    " go ": "Go",
    "rust": "Rust",
    "c++": "C++",
    "c#": "C#",
    "ruby": "Ruby",
    "kotlin": "Kotlin",
    "swift": "Swift",
}
LICENSES = {
    "mit": "MIT",
    "apache": "Apache-2.0",
    "gpl": "GPL-3.0",
    "bsd": "BSD-3-Clause",
    "mpl": "MPL-2.0",
}

def _openai_client() -> AsyncOpenAI:
    return AsyncOpenAI()


def validate_request(state: RepoScoutState) -> dict[str, Any]:
    raw = state.get("raw_requirement", "").strip()
    if len(raw) < 4:
        return {"error": "请至少描述想找的项目、用途或功能需求。"}
    return {}


def _explicit_constraints(raw: str) -> dict[str, Any]:
    lowered = f" {raw.lower()} "
    language = next((value for marker, value in LANGUAGES.items() if marker in lowered), None)
    star_match = re.search(
        r"(?:至少|最低|不少于|at\s+least|minimum|min\.?|>=?)\s*(\d+)\s*(?:stars?|星)?",
        lowered,
    )
    licenses = [value for marker, value in LICENSES.items() if marker in lowered]
    active_days = 180 if any(item in lowered for item in ("半年", "近期", "活跃", "维护")) else None
    return {
        "language": language,
        "minimum_stars": int(star_match.group(1)) if star_match else 0,
        "licenses": licenses,
        "active_within_days": active_days,
    }


async def understand_requirement(state: RepoScoutState) -> dict[str, Any]:
    raw = state["raw_requirement"].strip()
    warnings = list(state.get("warnings", []))
    parser = "rules"
    if os.getenv("OPENAI_API_KEY"):
        try:
            async with asyncio.timeout(_requirement_timeout_seconds):
                intent = await parse_search_intent_with_llm(
                    raw, _openai_client(), os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
                )
            parser = "llm"
        except Exception as exc:
            intent = parse_search_intent_with_rules(raw)
            parser = "rules_fallback"
            reason = "超时" if isinstance(exc, TimeoutError) else "失败"
            warnings.append(
                f"LLM 需求解析{reason}，已降级为规则关键词：{type(exc).__name__}"
            )
    else:
        intent = parse_search_intent_with_rules(raw)

    constraints = _explicit_constraints(raw)
    inferred_roles = infer_component_roles(intent)
    existing_roles = {item.role for item in intent.component_roles}
    intent.component_roles.extend(
        item for item in inferred_roles if item.role not in existing_roles
    )
    intent.language = constraints["language"]
    intent.minimum_stars = constraints["minimum_stars"]
    intent.licenses = constraints["licenses"]
    intent.active_within_days = constraints["active_within_days"]
    if not intent.keywords and not intent.search_strategies:
        return {
            "search_intent": intent.model_dump(),
            "error": "无法从需求中得到可靠的 GitHub 关键词，请补充项目类型或启用 LLM。",
            "warnings": warnings,
        }
    return {
        "search_intent": intent.model_dump(),
        "requirement": constraints,
        "requirement_parser": parser,
        "clarification_questions": intent.clarification_questions,
        "warnings": warnings,
    }


def request_clarification(state: RepoScoutState) -> dict[str, Any]:
    return {"report": state["clarification_questions"][0]}


def plan_search(state: RepoScoutState) -> dict[str, Any]:
    plan = compile_search_plan(SearchIntent.model_validate(state["search_intent"]))
    return {
        "search_plan": plan.model_dump(),
        "queries": [item.model_dump() for item in plan.queries],
    }


async def search_github(state: RepoScoutState) -> dict[str, Any]:
    queries = [str(item["query"]) for item in state["queries"]]
    query = queries[0]
    warnings = list(state.get("warnings", []))
    per_query_limit = 15

    async def run_search(
        search_query: str,
    ) -> tuple[str, str, list[dict[str, Any]] | Exception]:
        try:
            found = await get_github_client().search_repositories(
                search_query, limit=per_query_limit
            )
            if not found:
                relaxed = relax_github_query(search_query)
                if relaxed:
                    found = await get_github_client().search_repositories(
                        relaxed, limit=per_query_limit
                    )
                    if found:
                        return search_query, relaxed, found
            return search_query, search_query, found
        except GitHubSearchError as exc:
            return search_query, search_query, exc

    candidates_by_name: dict[str, dict[str, Any]] = {}
    successful_queries: list[str] = []
    failures = 0
    query_metadata = {str(item["query"]): item for item in state.get("queries", [])}
    github_future = asyncio.gather(*(run_search(item) for item in queries))
    web_client = get_web_search_client()
    web_hits = []
    if web_client:
        web_queries = [
            " ".join(str(term) for term in item.get("keywords", []))
            for item in state.get("queries", [])
        ]
        try:
            web_hits = await web_client.search_repositories(web_queries)
        except WebSearchError as exc:
            warnings.append(f"网页召回已降级，仅使用 GitHub 搜索：{exc}")

    async def hydrate_web_hit(hit: Any) -> tuple[Any, dict[str, Any] | Exception]:
        try:
            return hit, await get_github_client().get_repository(hit.full_name)
        except GitHubSearchError as exc:
            return hit, exc

    web_hydration_future = asyncio.gather(
        *(hydrate_web_hit(hit) for hit in web_hits[:8])
    )
    for query_rank, (original_query, executed_query, outcome) in enumerate(
        await github_future, start=1
    ):
        if isinstance(outcome, Exception):
            failures += 1
            warnings.append(f"GitHub 查询失败：{executed_query}：{outcome}")
            continue
        successful_queries.append(executed_query)
        if executed_query != original_query:
            warnings.append(f"查询无结果后已自动放宽：{executed_query}")
        for candidate in outcome:
            full_name = str(candidate.get("full_name", "")).casefold()
            if full_name:
                stored = candidates_by_name.setdefault(
                    full_name,
                    {
                        **candidate,
                        "discovery": {
                            "query_fingerprints": [],
                            "strategy_types": [],
                            "component_roles": [],
                            "best_query_rank": query_rank,
                            "sources": ["github_search"],
                        },
                    },
                )
                metadata = query_metadata.get(original_query, {})
                fingerprint = str(metadata.get("fingerprint", ""))
                strategy_type = str(metadata.get("strategy_type", ""))
                component_role = metadata.get("component_role")
                if fingerprint and fingerprint not in stored["discovery"]["query_fingerprints"]:
                    stored["discovery"]["query_fingerprints"].append(fingerprint)
                if strategy_type and strategy_type not in stored["discovery"]["strategy_types"]:
                    stored["discovery"]["strategy_types"].append(strategy_type)
                if (
                    component_role
                    and component_role not in stored["discovery"]["component_roles"]
                ):
                    stored["discovery"]["component_roles"].append(component_role)
                stored["discovery"]["best_query_rank"] = min(
                    stored["discovery"]["best_query_rank"], query_rank
                )
    for hit, web_outcome in await web_hydration_future:
        if isinstance(web_outcome, Exception):
            continue
        full_name = str(web_outcome.get("full_name", "")).casefold()
        if not full_name:
            continue
        web_metadata = next(
            (
                item
                for item in state.get("queries", [])
                if " ".join(str(term) for term in item.get("keywords", []))
                == hit.query
            ),
            {},
        )
        web_component_role = web_metadata.get("component_role")
        stored = candidates_by_name.setdefault(
            full_name,
            {
                **web_outcome,
                "discovery": {
                    "query_fingerprints": [],
                    "strategy_types": ["web_discovery"],
                    "component_roles": (
                        [web_component_role] if web_component_role else []
                    ),
                    "best_query_rank": len(queries) + 1,
                    "sources": [hit.source],
                    "web_hits": [],
                },
            },
        )
        sources = stored["discovery"].setdefault("sources", ["github_search"])
        if hit.source not in sources:
            sources.append(hit.source)
        component_roles = stored["discovery"].setdefault("component_roles", [])
        if web_component_role and web_component_role not in component_roles:
            component_roles.append(web_component_role)
        stored["discovery"].setdefault("web_hits", []).append(
            {
                "title": hit.title,
                "url": hit.url,
                "description": hit.description,
                "query": hit.query,
                "source": hit.source,
            }
        )
    if failures == len(queries) and not candidates_by_name:
        return {
            "query": query,
            "candidates": [],
            "error": "所有 GitHub 查询均失败",
            "warnings": warnings,
        }
    max_results = int(state.get("search_plan", {}).get("max_results", 60))
    candidates = list(candidates_by_name.values())[:max_results]

    rejected: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for candidate in candidates:
        reasons = []
        if candidate.get("archived"):
            reasons.append("仓库已归档")
        if candidate.get("disabled"):
            reasons.append("仓库已禁用")
        if candidate.get("size") == 0:
            reasons.append("仓库为空")
        if not candidate.get("default_branch"):
            reasons.append("缺少默认分支")
        if reasons:
            rejected.append({"full_name": candidate.get("full_name"), "reasons": reasons})
        else:
            valid.append(candidate)
    return {
        "query": query,
        "executed_queries": successful_queries,
        "candidates": valid,
        "rejected_candidates": rejected,
        "warnings": warnings,
    }


async def rank_candidates(state: RepoScoutState) -> dict[str, Any]:
    intent = SearchIntent.model_validate(state["search_intent"])
    candidates = list(state.get("candidates", []))
    warnings = list(state.get("warnings", []))
    client = _openai_client() if os.getenv("OPENAI_API_KEY") else None
    embedding_available = client is not None
    if client and embedding_circuit_open():
        ranked = await rerank_repositories(intent, candidates)
        warnings.append("Embedding circuit is open; used deterministic repository ranking")
        return {
            "ranked_candidates": ranked,
            "embedding_available": False,
            "warnings": warnings,
        }
    try:
        ranked = await rerank_repositories(
            intent,
            candidates,
            client=client,
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
        if client:
            close_embedding_circuit()
    except Exception as exc:
        warnings.append(
            "Repository semantic reranking failed; used deterministic ranking: "
            f"{type(exc).__name__}"
        )
        ranked = await rerank_repositories(intent, candidates)
        embedding_available = False
        open_embedding_circuit(
            float(os.getenv("EMBEDDING_CIRCUIT_TTL_SECONDS", "600"))
        )
    return {
        "ranked_candidates": ranked,
        "embedding_available": embedding_available,
        "warnings": warnings,
    }


async def inspect_documents(state: RepoScoutState) -> dict[str, Any]:
    rejected = list(state.get("rejected_candidates", []))
    warnings = list(state.get("warnings", []))
    max_repositories = int(state.get("search_plan", {}).get("max_repositories_to_analyze", 24))
    max_documents = int(state.get("search_plan", {}).get("max_documents_per_repository", 6))
    candidates = state.get("ranked_candidates", state.get("candidates", []))[:max_repositories]
    intent = SearchIntent.model_validate(state["search_intent"])
    implementation_terms = list(intent.keywords)
    for strategy in intent.search_strategies:
        implementation_terms.extend(strategy.terms)
    for requirement in intent.requirements:
        implementation_terms.extend(requirement.retrieval_terms)

    async def inspect(candidate: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        try:
            documents = await get_github_client().fetch_repository_documents(
                candidate["full_name"],
                candidate["default_branch"],
                max_documents=max_documents,
                implementation_terms=implementation_terms,
            )
        except GitHubSearchError as exc:
            return candidate, exc
        return candidate, documents

    inspected: list[dict[str, Any]] = []
    for candidate, outcome in await asyncio.gather(*(inspect(item) for item in candidates)):
        if isinstance(outcome, GitHubSearchError):
            warnings.append(f"{candidate['full_name']}：文档读取失败：{outcome}")
            rejected.append({"full_name": candidate["full_name"], "reasons": ["仓库文档读取失败"]})
            continue
        documents = outcome
        has_repository_document = any(
            item.get("source_type") in ("readme", "documentation")
            or item.get("path", "")
            .lower()
            .startswith(("readme", "docs/", "doc/", "documentation/"))
            for item in documents
        )
        if not documents or not has_repository_document:
            rejected.append(
                {
                    "full_name": candidate["full_name"],
                    "reasons": ["没有可分析的 README 或 docs 文档"],
                }
            )
            continue
        inspected.append({**candidate, "documents": documents})
    return {"document_candidates": inspected, "rejected_candidates": rejected, "warnings": warnings}


def _all_evidence(
    intent: SearchIntent,
    documentation: list[dict[str, str]],
    implementation_documents: list[dict[str, str]],
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
    return (
        {requirement.id: documentation for requirement in intent.requirements},
        {
            requirement.id: implementation_documents
            for requirement in intent.requirements
        },
    )


def _assessment_context(
    intent: SearchIntent,
    documentation: dict[str, list[dict[str, str]]],
    implementation: dict[str, list[dict[str, str]]],
) -> str:
    return (
        "DOCUMENTATION EVIDENCE:\n"
        + format_requirement_context(intent, documentation)
        + "\n\nSTATIC IMPLEMENTATION EVIDENCE:\n"
        + format_requirement_context(intent, implementation)
    )


async def _match_document_batch(
    state: RepoScoutState, client: AsyncOpenAI | None
) -> dict[str, Any]:
    intent = SearchIntent.model_validate(state["search_intent"])
    recommendations: list[dict[str, Any]] = []
    rejected = list(state.get("rejected_candidates", []))
    warnings = list(state.get("warnings", []))
    for candidate in state.get("document_candidates", []):
        documents = candidate["documents"]
        documentation = [
            item
            for item in documents
            if item.get("source_type") not in {"manifest", "implementation"}
        ]
        implementation_documents = [
            item for item in documents if item.get("source_type") in {"manifest", "implementation"}
        ]
        retrieval_mode = state.get(
            "effective_retrieval_mode",
            os.getenv("REPOSCOUT_RETRIEVAL_MODE", "hybrid").lower(),
        )
        if retrieval_mode == "full":
            retrieved, implementation_retrieved = _all_evidence(
                intent, documentation, implementation_documents
            )
        elif retrieval_mode == "lexical":
            retrieved = retrieve_for_requirements_lexical(
                intent, documentation, top_k=3
            )
            implementation_retrieved = retrieve_for_requirements_lexical(
                intent, implementation_documents, top_k=3
            )
        elif retrieval_mode in {"hybrid", "semantic"} and client:
            try:
                retrieved = await retrieve_for_requirements(
                    intent,
                    documentation,
                    client,
                    embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                    top_k=3,
                    use_lexical=retrieval_mode == "hybrid",
                )
                implementation_retrieved = await retrieve_for_requirements(
                    intent,
                    implementation_documents,
                    client,
                    embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                    top_k=3,
                    use_lexical=retrieval_mode == "hybrid",
                )
            except Exception as exc:
                warnings.append(
                    f"{candidate['full_name']}：检索失败，已降级为完整文档：{type(exc).__name__}"
                )
                retrieved, implementation_retrieved = _all_evidence(
                    intent, documentation, implementation_documents
                )
        else:
            if retrieval_mode in {"hybrid", "semantic"} and not client:
                warnings.append("未配置 OPENAI_API_KEY，检索已降级为完整文档")
            retrieved, implementation_retrieved = _all_evidence(
                intent, documentation, implementation_documents
            )
        analyst_context = _assessment_context(
            intent, retrieved, implementation_retrieved
        )
        analyst_documents = unique_retrieved_chunks(retrieved.values())
        try:
            if client:
                timeout_seconds = float(os.getenv("OPENAI_ANALYSIS_TIMEOUT", "60"))
                async with asyncio.timeout(timeout_seconds):
                    response: Any = await client.responses.parse(
                        model=os.getenv(
                            "OPENAI_ASSESSMENT_MODEL",
                            os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                        ),
                        input=[
                            {"role": "system", "content": ASSESSMENT_PROMPT},
                            {
                                "role": "user",
                                "content": (
                                    f"需求：{intent.model_dump_json()}\n"
                                    + analyst_context
                                ),
                            },
                        ],
                        text_format=RepositoryAssessment,
                    )
                assessment = response.output_parsed
                if not isinstance(assessment, RepositoryAssessment):
                    raise ValueError("LLM 未返回 RepositoryAssessment")
            else:
                assessment = rule_assessment(intent, analyst_documents)
        except Exception as exc:
            warnings.append(f"{candidate['full_name']}：文档匹配降级：{type(exc).__name__}")
            assessment = rule_assessment(intent, analyst_documents)
        assessment = validate_evidence(assessment, documents)
        assessment = validate_implementation_evidence(
            assessment,
            unique_retrieved_chunks(implementation_retrieved.values()),
        )
        criteria_by_id = {item.requirement_id: item for item in assessment.criteria}
        assessment.criteria = [
            criteria_by_id.get(
                requirement.id,
                CriterionMatch(requirement_id=requirement.id, status="unknown"),
            )
            for requirement in intent.requirements
        ]
        required_ids = {item.id for item in intent.requirements if item.required}
        violated = [
            item.requirement_id
            for item in assessment.criteria
            if item.status == "violated" and item.requirement_id in required_ids
        ]
        satisfied = sum(
            item.status == "satisfied" and item.requirement_id in required_ids
            for item in assessment.criteria
        )
        implemented = sum(
            item.implementation_status == "implemented" and item.requirement_id in required_ids
            for item in assessment.criteria
        )
        coverage = satisfied / len(required_ids) if required_ids else 0.5
        implementation_coverage = implemented / len(required_ids) if required_ids else 0.0
        popularity = min(10.0, math.log10(candidate.get("stars", 0) + 1) * 2)
        core_status = assessment.core_purpose.status
        core_factor = {"matched": 1.0, "unknown": 0.55, "mismatched": 0.0}[core_status]
        score = round(
            (coverage * 80 + implementation_coverage * 10) * core_factor + popularity,
            1,
        )
        compatibility = extract_compatibility_evidence(documents)
        recommendations.append(
            {
                **{key: value for key, value in candidate.items() if key != "documents"},
                "score": score,
                "summary": assessment.summary,
                "core_purpose": assessment.core_purpose.model_dump(),
                "criteria": [item.model_dump() for item in assessment.criteria],
                "component_roles": candidate.get("discovery", {}).get(
                    "component_roles", []
                ),
                "compatibility": compatibility,
                "document_paths": list(dict.fromkeys(item["path"] for item in documents)),
                "retrieval": {
                    requirement_id: [
                        {
                            "path": item.get("path"),
                            "heading": item.get("heading"),
                            "commit_sha": item.get("commit_sha"),
                            "url": item.get("url"),
                        }
                        for item in chunks
                    ]
                    for requirement_id, chunks in retrieved.items()
                },
                "implementation_retrieval": {
                    requirement_id: [
                        {
                            "path": item.get("path"),
                            "heading": item.get("heading"),
                            "commit_sha": item.get("commit_sha"),
                            "source_type": item.get("source_type"),
                            "url": item.get("url"),
                        }
                        for item in chunks
                    ]
                    for requirement_id, chunks in implementation_retrieved.items()
                },
                "retrieved_chunk_count": len(analyst_documents),
                "retrieved_context_chars": sum(
                    len(item.get("content", "")) for item in analyst_documents
                ),
                "reasons": [
                    f"核心用途匹配：{core_status}",
                    f"必需需求文档匹配 {satisfied}/{len(required_ids)}",
                    f"必需需求静态实现迹象 {implemented}/{len(required_ids)}",
                ],
                "_required_violations": violated,
                "_core_purpose_mismatch": core_status == "mismatched",
                "risks": [
                    f"{requirement_id} 与必需需求明确冲突"
                    for requirement_id in violated
                ]
                + [
                    "仓库核心用途与用户目标不属于同一产品类别"
                    for _ in range(core_status == "mismatched")
                ]
                + [
                    "仓库核心用途缺少可验证证据"
                    for _ in range(core_status == "unknown")
                ]
                + [
                    f"{item.requirement_id} 缺少文档证据"
                    for item in assessment.criteria
                    if item.status == "unknown"
                ]
                + [
                    f"{item.requirement_id} 仅有文档声称或静态实现证据不足"
                    for item in assessment.criteria
                    if item.implementation_status in {"documented_only", "uncertain"}
                ],
            }
        )
    recommendations.sort(
        key=lambda item: (
            item.get("core_purpose", {}).get("status") == "matched",
            item["score"],
        ),
        reverse=True,
    )
    return {
        "recommendations": recommendations,
        "rejected_candidates": rejected,
        "warnings": warnings,
    }


async def match_documents(state: RepoScoutState) -> dict[str, Any]:
    candidates = list(
        state.get("analysis_candidates", state.get("document_candidates", []))
    )
    if not candidates:
        return {
            "recommendations": [],
            "solutions": [],
            "evidence_matrix": {},
            "rejected_candidates": list(state.get("rejected_candidates", [])),
            "warnings": list(state.get("warnings", [])),
        }

    configured = int(os.getenv("ANALYSIS_MAX_CONCURRENCY", "8"))
    concurrency = max(1, min(configured, 8, len(candidates)))
    client = _openai_client() if os.getenv("OPENAI_API_KEY") else None
    semaphore = asyncio.Semaphore(concurrency)

    async def run_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        batch_state: RepoScoutState = {
            **state,
            "document_candidates": [candidate],
            "rejected_candidates": [],
            "warnings": [],
        }
        async with semaphore:
            return await _match_document_batch(batch_state, client)

    outcomes = await asyncio.gather(*(run_candidate(item) for item in candidates))
    recommendations = [
        item for outcome in outcomes for item in outcome["recommendations"]
    ]
    recommendations.sort(
        key=lambda item: (
            item.get("core_purpose", {}).get("status") == "matched",
            item["score"],
        ),
        reverse=True,
    )
    for item in recommendations:
        item["match_kind"] = (
            "near_miss"
            if item["_required_violations"] or item["_core_purpose_mismatch"]
            else "eligible"
        )
    assessed_components = [
        {
            key: value
            for key, value in item.items()
            if key not in {"_required_violations", "_core_purpose_mismatch"}
        }
        for item in recommendations
    ]
    rejected = list(state.get("rejected_candidates", []))
    rejected.extend(item for outcome in outcomes for item in outcome["rejected_candidates"])
    warnings = list(state.get("warnings", []))
    warnings.extend(item for outcome in outcomes for item in outcome["warnings"])
    core_matches = [
        item for item in recommendations if not item["_core_purpose_mismatch"]
    ]
    for item in recommendations:
        if item["_core_purpose_mismatch"]:
            rejected.append(
                {
                    "full_name": item["full_name"],
                    "reasons": ["核心用途与用户目标不属于同一产品类别"],
                }
            )
    recommendations = core_matches
    eligible = [item for item in recommendations if not item["_required_violations"]]
    if eligible:
        for item in recommendations:
            if item["_required_violations"]:
                rejected.append(
                    {
                        "full_name": item["full_name"],
                        "reasons": [
                            "必需需求明确冲突："
                            + ", ".join(item["_required_violations"])
                        ],
                    }
                )
        recommendations = eligible
    elif recommendations:
        warnings.append("没有发现满足全部硬条件的仓库，以下结果为最接近的候选")
    recommendations = [
        {
            key: value
            for key, value in item.items()
            if key not in {"_required_violations", "_core_purpose_mismatch"}
        }
        for item in recommendations
    ]
    primary_recommendations = [
        item
        for item in recommendations
        if not item.get("component_roles")
        or any(
            strategy not in {"component_role", "web_discovery"}
            for strategy in item.get("discovery", {}).get("strategy_types", [])
        )
    ]
    if primary_recommendations:
        recommendations = primary_recommendations
    solutions = build_solutions(
        SearchIntent.model_validate(state["search_intent"]),
        recommendations,
        assessed_components,
    )
    evidence_matrix = build_evidence_matrix(
        SearchIntent.model_validate(state["search_intent"]),
        solutions,
        assessed_components,
    )
    return {
        "recommendations": recommendations,
        "solutions": solutions,
        "component_candidates": assessed_components,
        "evidence_matrix": evidence_matrix,
        "rejected_candidates": rejected,
        "warnings": list(dict.fromkeys(warnings)),
    }


async def prepare_evidence(state: RepoScoutState) -> dict[str, Any]:
    candidates = list(state.get("document_candidates", []))
    intent = SearchIntent.model_validate(state["search_intent"])
    warnings = list(state.get("warnings", []))
    configured_limit = int(os.getenv("ANALYSIS_CANDIDATE_LIMIT", "8"))
    limit = max(1, min(configured_limit, 24))
    selected = select_analysis_candidates(
        intent, candidates, limit=limit, exploration_slots=min(3, limit // 3)
    )

    retrieval_mode = os.getenv("REPOSCOUT_RETRIEVAL_MODE", "hybrid").lower()
    effective_retrieval_mode = retrieval_mode
    if retrieval_mode in {"hybrid", "semantic"} and not state.get(
        "embedding_available", True
    ):
        effective_retrieval_mode = "lexical"
    elif retrieval_mode in {"hybrid", "semantic"} and os.getenv("OPENAI_API_KEY"):
        chunks = [
            document
            for candidate in selected
            for document in candidate.get("documents", [])
        ]
        try:
            await prewarm_retrieval_embeddings(
                intent,
                chunks,
                _openai_client(),
                embedding_model=os.getenv(
                    "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
                ),
            )
        except Exception as exc:
            warnings.append(
                "Embedding is unavailable; this run uses BM25 evidence retrieval: "
                f"{type(exc).__name__}"
            )
            effective_retrieval_mode = "lexical"
    return {
        "analysis_candidates": selected,
        "effective_retrieval_mode": effective_retrieval_mode,
        "warnings": warnings,
    }


async def inspect_repository_code(
    repository: dict[str, Any], requirement: str = ""
) -> dict[str, Any]:
    budget = choose_code_inspection_budget(repository)
    snapshot = await get_github_client().fetch_code_snapshot(
        str(repository["full_name"]),
        str(repository.get("default_branch") or "main"),
        max_files=budget.max_files,
        max_total_chars=budget.max_chars,
    )
    explanation = deterministic_code_explanation(snapshot)
    method = "deterministic_repo_map"
    if os.getenv("OPENAI_API_KEY") and snapshot.get("files"):
        repo_map = build_repo_map(snapshot)
        remaining = 100_000
        sections = []
        for item in snapshot["files"]:
            if remaining <= 0:
                break
            content = str(item.get("content", ""))[:remaining]
            sections.append(f"FILE: {item.get('path')}\n{content}")
            remaining -= len(content)
        try:
            async with asyncio.timeout(35):
                response: Any = await _openai_client().responses.parse(
                    model=os.getenv(
                        "OPENAI_ASSESSMENT_MODEL",
                        os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    ),
                    input=[
                        {"role": "system", "content": CODE_EXPLANATION_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"User context: {requirement}\n\nREPO MAP:\n{repo_map}\n\n"
                                + "\n\n".join(sections)
                            ),
                        },
                    ],
                    text_format=CodeExplanation,
                )
            parsed = response.output_parsed
            if isinstance(parsed, CodeExplanation):
                explanation = validate_code_explanation(parsed, snapshot)
                method = "llm_with_validated_code_quotes"
        except Exception as exc:
            explanation.limitations.append(
                f"代码解释模型不可用，已降级为符号地图：{type(exc).__name__}"
            )
    if snapshot.get("tree_truncated"):
        explanation.limitations.append("GitHub 返回的递归文件树已截断")
    if int(snapshot.get("total_code_files", 0)) > budget.max_files:
        explanation.limitations.append(
            f"按 {budget.mode} 预算从 {snapshot.get('total_code_files')} 个代码文件中读取 "
            f"{len(snapshot.get('files', []))} 个"
        )
    return code_understanding_result(
        repository, budget, snapshot, explanation, analysis_method=method
    )


async def deep_code_search(state: RepoScoutState) -> dict[str, Any]:
    if not state.get("deep_code_search"):
        return {"code_understanding": []}
    candidates = list(state.get("recommendations", []))[:3]
    if not candidates:
        return {"code_understanding": []}
    semaphore = asyncio.Semaphore(2)

    async def inspect(candidate: dict[str, Any]) -> dict[str, Any] | Exception:
        try:
            async with semaphore:
                return await inspect_repository_code(
                    candidate, str(state.get("raw_requirement", ""))
                )
        except (GitHubSearchError, KeyError, ValueError) as exc:
            return exc

    outcomes = await asyncio.gather(*(inspect(item) for item in candidates))
    results = [item for item in outcomes if isinstance(item, dict)]
    failures = sum(isinstance(item, Exception) for item in outcomes)
    warnings = list(state.get("warnings", []))
    if failures:
        warnings.append(f"{failures} 个候选的深度代码理解失败，其他结果继续返回")
    return {"code_understanding": results, "warnings": warnings}


async def generate_report(state: RepoScoutState) -> dict[str, Any]:
    if state.get("error"):
        return {"report": state["error"]}
    solutions = state.get("solutions", [])
    if not solutions:
        report = "没有找到具备可分析 README/docs 的候选仓库。"
    else:
        report = (
            f"使用关键词查询 `{state['query']}`，读取候选仓库 README/docs 后，"
            f"形成 {len(solutions)} 套有证据支持的候选方案。"
        )
    result: dict[str, Any] = {"report": report}
    with suppress(GitHubSearchError):
        result["rate_limit"] = await get_github_client().get_rate_limit()
    return result
