import unittest

from evals.run_baseline import DEFAULT_CASES, evaluate


class OfflineEvaluationTest(unittest.TestCase):
    def test_baseline_replays_fifteen_cases_without_network(self):
        report = evaluate(DEFAULT_CASES)

        self.assertEqual(report["case_count"], 15)
        self.assertEqual(report["pipeline"], "full_document_context")
        self.assertEqual(report["known_failure_count"], 5)
        self.assertGreater(report["metrics"]["precision_at_5_micro"], 0)
        self.assertEqual(report["metrics"]["evidence_recall"], 0.8)
        self.assertEqual(report["metrics"]["citation_accuracy"], 1.0)
        self.assertIn("candidate_recall_macro", report["metrics"])
        self.assertIn("recall_at_24_macro", report["metrics"])
        self.assertIn("ndcg_at_24_macro", report["metrics"])
        self.assertIn("search_stages", report["cases"][0])
        self.assertEqual(report["metrics"]["model_calls"], 44)
        self.assertEqual(report["metrics"]["github_calls"], 90)
        self.assertGreater(report["metrics"]["estimated_input_tokens"], 0)
        self.assertEqual(report["metrics"]["cost_status"], "price_not_configured")

    def test_baseline_calculates_cost_with_versioned_prices(self):
        report = evaluate(
            DEFAULT_CASES,
            input_price_per_million=1.0,
            output_price_per_million=2.0,
        )

        self.assertEqual(report["metrics"]["cost_status"], "calculated")
        expected = round(
            (
                report["metrics"]["estimated_input_tokens"]
                + report["metrics"]["estimated_output_tokens"] * 2
            )
            / 1_000_000,
            6,
        )
        self.assertEqual(report["metrics"]["estimated_cost_usd"], expected)

    def test_hybrid_report_preserves_evidence_and_citation_quality(self):
        baseline = evaluate(DEFAULT_CASES)
        rag = evaluate(DEFAULT_CASES, pipeline="hybrid_top_k")

        self.assertEqual(rag["pipeline"], "hybrid_top_k")
        self.assertEqual(rag["metrics"]["evidence_recall"], baseline["metrics"]["evidence_recall"])
        self.assertEqual(
            rag["metrics"]["citation_accuracy"], baseline["metrics"]["citation_accuracy"]
        )


if __name__ == "__main__":
    unittest.main()
