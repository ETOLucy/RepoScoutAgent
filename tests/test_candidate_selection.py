import unittest

from src.reposcout.candidate_selection import select_analysis_candidates
from src.reposcout.search.models import RequirementItem, SearchIntent


def candidate(name: str, content: str, strategy: str, ranking: float) -> dict:
    return {
        "full_name": name,
        "repository_ranking": {"score": ranking},
        "discovery": {"strategy_types": [strategy]},
        "documents": [
            {"content": content, "source_type": "documentation"},
            {"content": "implementation", "source_type": "implementation"},
        ],
    }


class CandidateSelectionTest(unittest.TestCase):
    def test_prefilter_keeps_exploration_from_distinct_hypothesis(self):
        intent = SearchIntent(
            goal="learn retrieval",
            requirements=[
                RequirementItem(
                    id="eval",
                    description="evaluation scripts",
                    retrieval_terms=["evaluation"],
                )
            ],
            keywords=["retrieval"],
        )
        candidates = [
            candidate(f"common/{index}", "evaluation scripts", "common", 1 - index / 100)
            for index in range(8)
        ]
        candidates.append(candidate("novel/route", "different approach", "novel", 0.1))

        selected = select_analysis_candidates(
            intent, candidates, limit=5, exploration_slots=2
        )

        self.assertEqual(len(selected), 5)
        self.assertIn("novel/route", {item["full_name"] for item in selected})
        self.assertTrue(all("evidence_prefilter_score" in item for item in selected))


if __name__ == "__main__":
    unittest.main()
