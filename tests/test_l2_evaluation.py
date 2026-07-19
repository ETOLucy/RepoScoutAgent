import unittest

from evals.run_l2 import evaluate


class L2EvaluationTest(unittest.TestCase):
    def test_static_guardrail_metrics(self):
        report = evaluate()

        self.assertEqual(report["case_count"], 5)
        self.assertEqual(report["metrics"]["l2_precision"], 1.0)
        self.assertEqual(report["metrics"]["documented_only_detection"], 1.0)
        self.assertEqual(report["metrics"]["false_implementation_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
