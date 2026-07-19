import unittest
from types import SimpleNamespace

from evals.search_quality import evaluate_search_stages
from src.reposcout.reranking import (
    close_embedding_circuit,
    embedding_circuit_open,
    open_embedding_circuit,
    rerank_repositories,
    task_contract_text,
)
from src.reposcout.search.models import RequirementItem, SearchIntent, SearchStrategy


class FakeEmbeddings:
    async def create(self, **_kwargs):
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[1.0, 0.0]),
                SimpleNamespace(embedding=[0.0, 1.0]),
                SimpleNamespace(embedding=[0.9, 0.1]),
            ]
        )


class RepositoryRerankingTest(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        close_embedding_circuit()

    def setUp(self):
        self.intent = SearchIntent(
            goal="learn representative neural retrieval implementations",
            requirements=[
                RequirementItem(
                    id="implementation",
                    description="core retrieval implementation is readable",
                    evidence_sources=["source_code"],
                )
            ],
            keywords=["neural retrieval"],
            search_strategies=[
                SearchStrategy(
                    strategy_type="reference lineage",
                    terms=["neural retrieval reference implementation"],
                    rationale="Find representative implementations",
                    hypothesis="Research-maintained implementations expose the core algorithm",
                    expected_signals=["paper citation", "evaluation scripts"],
                    verifies=["implementation"],
                )
            ],
        )

    def test_task_contract_keeps_criteria_and_hypothesis_connected(self):
        contract = task_contract_text(self.intent)
        self.assertIn("core retrieval implementation is readable", contract)
        self.assertIn("Research-maintained implementations", contract)
        self.assertIn("source_code", contract)

    async def test_semantic_reranking_changes_discovery_order(self):
        repositories = [
            {
                "full_name": "popular/unrelated",
                "description": "popular web framework",
                "topics": ["web"],
                "discovery": {"query_fingerprints": ["q1"]},
            },
            {
                "full_name": "research/retrieval",
                "description": "neural retrieval reference implementation",
                "topics": ["retrieval"],
                "discovery": {"query_fingerprints": ["q1"]},
            },
        ]
        client = SimpleNamespace(embeddings=FakeEmbeddings())
        ranked = await rerank_repositories(self.intent, repositories, client=client)

        self.assertEqual(ranked[0]["full_name"], "research/retrieval")
        self.assertEqual(ranked[0]["repository_ranking"]["mode"], "semantic")

    def test_stage_evaluation_reports_early_candidate_loss(self):
        result = evaluate_search_stages(
            ["good/a", "good/b", "noise/c"],
            ["good/a", "noise/c", "good/b"],
            {"good/a": 3, "good/b": 2, "missing/d": 1},
            inspect_k=2,
            inspected_names=["good/a", "good/b"],
            analyzed_names=["good/a"],
        )
        self.assertAlmostEqual(result["candidate_recall"], 2 / 3)
        self.assertAlmostEqual(result["recall_at_inspection_cutoff"], 1 / 3)
        self.assertEqual(result["relevant_not_discovered"], ["missing/d"])
        self.assertEqual(result["relevant_dropped_before_inspection"], ["good/b"])
        self.assertAlmostEqual(result["recall_at_analysis_cutoff"], 0.5)

    def test_embedding_circuit_expires_or_can_be_closed(self):
        open_embedding_circuit(60)
        self.assertTrue(embedding_circuit_open())
        close_embedding_circuit()
        self.assertFalse(embedding_circuit_open())


if __name__ == "__main__":
    unittest.main()
