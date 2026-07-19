from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from src.reposcout.graph import build_graph
from src.reposcout.search.models import RepositoryAssessment, SearchIntent

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "baseline_cases.json"
DEFAULT_OUTPUT = ROOT / "baseline_report.json"


@dataclass
class ReplayStats:
    github_search_calls: int = 0
    github_document_calls: int = 0
    model_calls: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    assessment_queue: list[RepositoryAssessment] = field(default_factory=list)


class ReplayResponses:
    def __init__(self, intent: SearchIntent, stats: ReplayStats) -> None:
        self.intent = intent
        self.stats = stats
        self.intent_returned = False

    async def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.stats.model_calls += 1
        serialized_input = json.dumps(kwargs.get("input", []), ensure_ascii=False)
        self.stats.estimated_input_tokens += max(1, len(serialized_input) // 4)
        if not self.intent_returned:
            self.intent_returned = True
            output: SearchIntent | RepositoryAssessment = self.intent
        else:
            output = self.stats.assessment_queue.pop(0)
        self.stats.estimated_output_tokens += max(1, len(output.model_dump_json()) // 4)
        return SimpleNamespace(output_parsed=output)


def _repository(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": f"https://github.com/{raw['full_name']}",
        "language": raw.get("language", "Python"),
        "forks": raw.get("forks", 10),
        "open_issues": raw.get("open_issues", 2),
        "license": raw.get("license", "MIT"),
        "topics": raw.get("topics", []),
        "archived": raw.get("archived", False),
        "disabled": raw.get("disabled", False),
        "fork": raw.get("fork", False),
        "size": raw.get("size", 100),
        "default_branch": raw.get("default_branch", "main"),
        "updated_at": "2099-01-01T00:00:00Z",
        "pushed_at": "2099-01-01T00:00:00Z",
        **raw,
    }


def _unknown_assessment(intent: SearchIntent) -> RepositoryAssessment:
    return RepositoryAssessment.model_validate(
        {
            "summary": "fixture contains no matching evidence",
            "criteria": [
                {"requirement_id": item.id, "status": "unknown"}
                for item in intent.requirements
            ],
        }
    )


async def replay_case(case: dict[str, Any]) -> tuple[dict[str, Any], ReplayStats, float]:
    intent = SearchIntent.model_validate(case["intent"])
    stats = ReplayStats()
    repositories = [_repository(item) for item in case["repositories"]]
    documents = case["documents"]
    assessments = case.get("assessments", {})
    for repository in repositories:
        if documents.get(repository["full_name"]):
            raw = assessments.get(repository["full_name"])
            stats.assessment_queue.append(
                RepositoryAssessment.model_validate(raw) if raw else _unknown_assessment(intent)
            )

    async def search_fixture(_query: str, limit: int = 20) -> list[dict[str, Any]]:
        stats.github_search_calls += 1
        return repositories[:limit]

    async def document_fixture(
        full_name: str, _branch: str, max_documents: int = 6
    ) -> list[dict[str, str]]:
        stats.github_document_calls += 1
        return [
            {
                "path": path,
                "url": f"https://github.com/{full_name}/blob/main/{path}",
                "content": content,
            }
            for path, content in list(documents.get(full_name, {}).items())[:max_documents]
        ]

    client = SimpleNamespace(responses=ReplayResponses(intent, stats))
    github = SimpleNamespace(
        search_repositories=search_fixture,
        fetch_repository_documents=document_fixture,
        get_rate_limit=lambda: _empty_rate_limit(),
    )
    started = time.perf_counter()
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "offline-eval"}),
        patch("src.reposcout.nodes._openai_client", return_value=client),
        patch("src.reposcout.nodes.get_github_client", return_value=github),
    ):
        result = await build_graph().ainvoke({"raw_requirement": case["query"]})
    return result, stats, (time.perf_counter() - started) * 1000


async def _empty_rate_limit() -> dict[str, Any]:
    return {}


def evaluate(
    cases_path: Path = DEFAULT_CASES,
    input_price_per_million: float | None = None,
    output_price_per_million: float | None = None,
) -> dict[str, Any]:
    dataset = json.loads(cases_path.read_text(encoding="utf-8"))
    case_results: list[dict[str, Any]] = []
    relevant_hits = 0
    returned = 0
    evidence_hits = 0
    evidence_expected = 0
    valid_citations = 0
    citations = 0
    total_latency = 0.0
    total_model_calls = 0
    total_github_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for case in dataset["cases"]:
        result, stats, latency = asyncio.run(replay_case(case))
        recommendations = result.get("recommendations", [])[:5]
        relevant = set(case["relevant_repositories"])
        recommended_names = {item["full_name"] for item in recommendations}
        relevant_hits += len(relevant & recommended_names)
        returned += len(recommendations)

        found_evidence: set[str] = set()
        documents = case["documents"]
        for repository in recommendations:
            for criterion in repository.get("criteria", []):
                if criterion["status"] == "unknown":
                    continue
                citations += 1
                path = criterion.get("source_path")
                evidence = criterion.get("evidence") or ""
                source = documents.get(repository["full_name"], {}).get(path, "")
                if evidence.lower() in source.lower():
                    valid_citations += 1
                if criterion["status"] == "satisfied":
                    found_evidence.add(f"{repository['full_name']}:{criterion['requirement_id']}")
        expected = set(case["expected_evidence"])
        evidence_hits += len(found_evidence & expected)
        evidence_expected += len(expected)
        total_latency += latency
        total_model_calls += stats.model_calls
        total_github_calls += stats.github_search_calls + stats.github_document_calls
        total_input_tokens += stats.estimated_input_tokens
        total_output_tokens += stats.estimated_output_tokens
        case_results.append(
            {
                "id": case["id"],
                "recommended": sorted(recommended_names),
                "precision_at_5": len(relevant & recommended_names) / max(1, len(recommendations)),
                "evidence_recall": len(found_evidence & expected) / max(1, len(expected)),
                "latency_ms": round(latency, 2),
                "known_failure": case.get("known_failure"),
            }
        )

    count = len(case_results)
    estimated_cost = None
    if input_price_per_million is not None and output_price_per_million is not None:
        estimated_cost = round(
            total_input_tokens * input_price_per_million / 1_000_000
            + total_output_tokens * output_price_per_million / 1_000_000,
            6,
        )
    return {
        "dataset_version": dataset["version"],
        "pipeline": "full_document_context",
        "case_count": count,
        "metrics": {
            "precision_at_5_micro": round(relevant_hits / max(1, returned), 4),
            "evidence_recall": round(evidence_hits / max(1, evidence_expected), 4),
            "citation_accuracy": round(valid_citations / max(1, citations), 4),
            "average_latency_ms": round(total_latency / max(1, count), 2),
            "model_calls": total_model_calls,
            "github_calls": total_github_calls,
            "estimated_input_tokens": total_input_tokens,
            "estimated_output_tokens": total_output_tokens,
            "estimated_cost_usd": estimated_cost,
            "cost_status": "calculated" if estimated_cost is not None else "price_not_configured",
        },
        "known_failure_count": sum(bool(item["known_failure"]) for item in case_results),
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline full-document baseline")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input-price-per-million", type=float)
    parser.add_argument("--output-price-per-million", type=float)
    args = parser.parse_args()
    report = evaluate(
        args.cases,
        input_price_per_million=args.input_price_per_million,
        output_price_per_million=args.output_price_per_million,
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
