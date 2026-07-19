import unittest
from unittest.mock import patch

from src.reposcout.graph import build_graph


SAMPLE_REPOSITORIES = [
    {
        "full_name": "example/langgraph-agent",
        "url": "https://github.com/example/langgraph-agent",
        "description": "A Python LangGraph agent with tool calling",
        "language": "Python",
        "stars": 320,
        "forks": 40,
        "open_issues": 3,
        "license": "MIT",
        "topics": ["langgraph", "agent"],
        "archived": False,
        "updated_at": "2026-07-01T00:00:00Z",
    }
]


class RepoScoutGraphTest(unittest.TestCase):
    def test_invalid_requirement_stops_before_search(self):
        result = build_graph().invoke({"raw_requirement": "hi"})
        self.assertIn("至少描述", result["report"])
        self.assertNotIn("query", result)

    @patch("src.reposcout.nodes.search_repositories", return_value=SAMPLE_REPOSITORIES)
    def test_search_and_rank_flow(self, _mock_search):
        result = build_graph().invoke(
            {"raw_requirement": "Python LangGraph agent，至少 20 stars，近期维护"}
        )
        self.assertIn("language:Python", result["query"])
        self.assertEqual(result["recommendations"][0]["full_name"], "example/langgraph-agent")
        self.assertGreater(result["recommendations"][0]["score"], 0)
        self.assertIn("最近半年仍有更新", result["recommendations"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
