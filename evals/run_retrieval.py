from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.reposcout.retrieval import requirement_query_views, retrieve_for_requirements
from src.reposcout.search.models import RequirementItem, SearchIntent

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "retrieval_report.json"


CASES: list[dict[str, Any]] = [
    {
        "id": "exact_config_key",
        "intent": SearchIntent(
            goal="configure a broker",
            requirements=[
                RequirementItem(
                    id="config",
                    description="security.protocol=SASL_SSL",
                )
            ],
            keywords=["broker configuration"],
        ),
        "chunks": [
            {"path": "config.yml", "content": "security.protocol=SASL_SSL"},
            {"path": "docs/deploy.md", "content": "Production deployment instructions"},
            {"path": "docs/auth.md", "content": "Authentication overview"},
        ],
        "chunk_vectors": [[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]],
        "query_vector": [1.0, 0.0],
        "relevant": "config.yml",
    },
    {
        "id": "semantic_paraphrase",
        "intent": SearchIntent(
            goal="enterprise access control",
            requirements=[
                RequirementItem(
                    id="identity",
                    description="enterprise identity federation",
                )
            ],
            keywords=["identity management"],
        ),
        "chunks": [
            {"path": "docs/theme.md", "content": "Choose custom interface colors"},
            {"path": "src/auth/saml.ts", "content": "SAML SSO callback for Okta"},
            {"path": "docs/users.md", "content": "Create local user accounts"},
        ],
        "chunk_vectors": [[0.0, 1.0], [1.0, 0.0], [0.4, 0.6]],
        "query_vector": [1.0, 0.0],
        "relevant": "src/auth/saml.ts",
    },
]


class FixtureEmbeddings:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        if len(kwargs["input"]) != len(self.vectors):
            raise ValueError("fixture vector count does not match retrieval inputs")
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=vector) for vector in self.vectors]
        )


async def _evaluate_mode(mode: str) -> dict[str, float]:
    reciprocal_ranks: list[float] = []
    for case in CASES:
        intent: SearchIntent = case["intent"]
        view_count = len(requirement_query_views(intent.requirements[0], intent))
        vectors = case["chunk_vectors"] + [case["query_vector"]] * view_count
        retrieved = await retrieve_for_requirements(
            intent,
            case["chunks"],
            SimpleNamespace(embeddings=FixtureEmbeddings(vectors)),
            embedding_model="fixture",
            top_k=3,
            use_lexical=mode != "dense_only",
            lexical_weight=0.0 if mode == "dense_only" else 1.0,
            dense_weight=0.0 if mode == "lexical_only" else 1.0,
            mmr_diversity=0.0,
        )
        ranked = retrieved[intent.requirements[0].id]
        rank = next(
            (
                index
                for index, chunk in enumerate(ranked, start=1)
                if chunk["path"] == case["relevant"]
            ),
            0,
        )
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return {
        "recall_at_1": round(
            sum(value == 1.0 for value in reciprocal_ranks) / len(reciprocal_ranks), 4
        ),
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4),
    }


async def evaluate() -> dict[str, Any]:
    return {
        "case_count": len(CASES),
        "metrics": {
            mode: await _evaluate_mode(mode)
            for mode in ("lexical_only", "dense_only", "hybrid")
        },
    }


def main() -> None:
    report = asyncio.run(evaluate())
    DEFAULT_OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
