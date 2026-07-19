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
        self.assertEqual(report["metrics"]["model_calls"], 44)
        self.assertEqual(report["metrics"]["github_calls"], 45)
        self.assertGreater(report["metrics"]["estimated_input_tokens"], 0)
        self.assertEqual(report["metrics"]["cost_status"], "price_not_configured")

    def test_baseline_calculates_cost_with_versioned_prices(self):
        report = evaluate(
            DEFAULT_CASES,
            input_price_per_million=1.0,
            output_price_per_million=2.0,
        )

        self.assertEqual(report["metrics"]["cost_status"], "calculated")
        self.assertEqual(report["metrics"]["estimated_cost_usd"], 0.010934)


if __name__ == "__main__":
    unittest.main()
