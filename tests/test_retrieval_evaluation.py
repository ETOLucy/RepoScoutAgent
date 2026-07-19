import asyncio
import unittest

from evals.run_retrieval import evaluate


class RetrievalEvaluationTest(unittest.TestCase):
    def test_hybrid_covers_exact_and_semantic_cases(self):
        report = asyncio.run(evaluate())

        metrics = report["metrics"]
        self.assertEqual(metrics["hybrid"]["recall_at_1"], 1.0)
        self.assertGreater(
            metrics["hybrid"]["recall_at_1"],
            metrics["lexical_only"]["recall_at_1"],
        )
        self.assertGreater(
            metrics["hybrid"]["recall_at_1"],
            metrics["dense_only"]["recall_at_1"],
        )


if __name__ == "__main__":
    unittest.main()
