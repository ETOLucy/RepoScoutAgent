import unittest

from src.reposcout.code_understanding import (
    CodeExplanation,
    CodeModuleExplanation,
    build_repo_map,
    choose_code_inspection_budget,
    validate_code_explanation,
)


class CodeUnderstandingTest(unittest.TestCase):
    def test_adaptive_budgets_cover_reputation_and_size_boundaries(self):
        established = choose_code_inspection_budget(
            {"size": 500_000, "stars": 20_000, "forks": 2_000}
        )
        small = choose_code_inspection_budget({"size": 10_000, "stars": 2})
        medium = choose_code_inspection_budget({"size": 10_001, "stars": 2})
        large = choose_code_inspection_budget({"size": 100_001, "stars": 2})

        self.assertEqual(established.mode, "established_map")
        self.assertEqual(small.mode, "broad")
        self.assertEqual(small.max_files, 24)
        self.assertEqual(medium.mode, "targeted")
        self.assertEqual(large.mode, "repo_map")
        self.assertLess(large.max_files, medium.max_files)

    def test_repo_map_extracts_python_symbols(self):
        snapshot = {
            "repository": "example/repo",
            "total_code_files": 1,
            "tree_truncated": False,
            "files": [
                {
                    "path": "src/main.py",
                    "content": "class Worker:\n    pass\n\ndef run():\n    pass\n",
                }
            ],
        }

        repo_map = build_repo_map(snapshot)

        self.assertIn("Worker", repo_map)
        self.assertIn("run", repo_map)

    def test_unverifiable_module_quote_is_removed(self):
        explanation = CodeExplanation(
            summary="test",
            entry_points=["src/main.py", "missing.py"],
            modules=[
                CodeModuleExplanation(
                    path="src/main.py", purpose="starts server", evidence="invented"
                ),
                CodeModuleExplanation(
                    path="src/main.py", purpose="starts server", evidence="def run"
                ),
            ],
        )
        snapshot = {
            "files": [{"path": "src/main.py", "content": "def run(): pass"}]
        }

        result = validate_code_explanation(explanation, snapshot)

        self.assertEqual(result.entry_points, ["src/main.py"])
        self.assertEqual([item.evidence for item in result.modules], ["def run"])
