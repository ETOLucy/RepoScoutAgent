import asyncio
import unittest
from types import SimpleNamespace

from src.reposcout.retrieval import (
    format_requirement_context,
    retrieve_for_requirements,
    retrieve_for_requirements_lexical,
    tokenize,
)
from src.reposcout.search.models import RequirementItem, SearchIntent

CHUNKS = [
    {
        "path": "docs/deploy.md",
        "heading": "Docker",
        "commit_sha": "abc",
        "url": "https://example.test/deploy",
        "content": "Deploy the application with Docker Compose.",
    },
    {
        "path": "docs/auth.md",
        "heading": "Authentication",
        "commit_sha": "abc",
        "url": "https://example.test/auth",
        "content": "Configure SAML single sign-on for your team.",
    },
    {
        "path": "docs/theme.md",
        "heading": "Colors",
        "commit_sha": "abc",
        "url": "https://example.test/theme",
        "content": "Choose a light or dark color theme.",
    },
]


class RetrievalTest(unittest.TestCase):
    def test_semantic_retrieval_finds_semantic_match(self):
        class Embeddings:
            async def create(self, **_: object) -> SimpleNamespace:
                inputs = _["input"]
                vectors = [[0.0, 1.0], [1.0, 0.0], [0.2, 0.8]]
                vectors.extend([[1.0, 0.0] for _item in inputs[3:]])
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=vector) for vector in vectors]
                )

        intent = SearchIntent(
            goal="identity",
            requirements=[
                RequirementItem(id="identity", description="enterprise identity federation")
            ],
            keywords=["identity"],
        )
        result = asyncio.run(
            retrieve_for_requirements(
                intent,
                CHUNKS,
                SimpleNamespace(embeddings=Embeddings()),
                embedding_model="test-mmr",
                top_k=1,
                use_lexical=False,
            )
        )

        self.assertEqual(result["identity"][0]["path"], "docs/auth.md")
        context = format_requirement_context(intent, result)
        self.assertIn("COMMIT: abc", context)

    def test_tokenizer_preserves_exact_terms_and_chinese_bigrams(self):
        tokens = tokenize("运行 docker-compose，支持全文搜索")

        self.assertIn("docker-compose", tokens)
        self.assertIn("docker", tokens)
        self.assertIn("全文", tokens)

    def test_lexical_fallback_returns_bounded_evidence(self):
        intent = SearchIntent(
            goal="deployment",
            requirements=[RequirementItem(id="deploy", description="Docker deployment")],
            keywords=["deployment"],
        )

        result = retrieve_for_requirements_lexical(intent, CHUNKS, top_k=1)

        self.assertEqual(result["deploy"][0]["path"], "docs/deploy.md")

    def test_mmr_diversifies_redundant_dense_results(self):
        class Embeddings:
            async def create(self, **kwargs: object) -> SimpleNamespace:
                inputs = kwargs["input"]
                vectors = [[1.0, 0.0], [0.99, 0.01], [0.7, 0.7]]
                vectors.extend([[1.0, 0.0] for _item in inputs[3:]])
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=vector) for vector in vectors]
                )

        intent = SearchIntent(
            goal="deployment",
            requirements=[RequirementItem(id="deploy", description="deployment")],
            keywords=["deployment"],
        )
        result = asyncio.run(
            retrieve_for_requirements(
                intent,
                CHUNKS,
                SimpleNamespace(embeddings=Embeddings()),
                embedding_model="test",
                top_k=2,
                use_lexical=False,
                mmr_diversity=0.35,
            )
        )

        self.assertEqual(
            [item["path"] for item in result["deploy"]],
            ["docs/deploy.md", "docs/theme.md"],
        )

    def test_embedding_cache_reuses_identical_chunks(self):
        class Embeddings:
            def __init__(self):
                self.calls = 0

            async def create(self, **kwargs: object) -> SimpleNamespace:
                self.calls += 1
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in kwargs["input"]]
                )

        embeddings = Embeddings()
        client = SimpleNamespace(embeddings=embeddings)
        intent = SearchIntent(
            goal="cache verification",
            requirements=[RequirementItem(id="cache", description="cache verification")],
            keywords=["cache verification"],
        )
        for _ in range(2):
            asyncio.run(
                retrieve_for_requirements(
                    intent,
                    CHUNKS,
                    client,
                    embedding_model="unique-cache-test-model",
                    top_k=1,
                )
            )

        self.assertEqual(embeddings.calls, 1)


if __name__ == "__main__":
    unittest.main()
