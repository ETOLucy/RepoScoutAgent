import unittest
from os import environ
from types import SimpleNamespace
from unittest.mock import patch

from src.reposcout.graph import build_graph
from src.reposcout.nodes import RepositoryRequirement


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
        "updated_at": "2099-07-01T00:00:00Z",
        "pushed_at": "2099-07-01T00:00:00Z",
    }
]


class RepoScoutGraphTest(unittest.TestCase):
    def test_invalid_requirement_stops_before_search(self):
        result = build_graph().invoke({"raw_requirement": "hi"})
        self.assertIn("至少描述", result["report"])
        self.assertNotIn("query", result)

    @patch("src.reposcout.nodes._openai_client")
    @patch("src.reposcout.nodes.get_rate_limit", return_value={"core": {"limit": 5000, "remaining": 4999, "used": 1, "reset": 9999999999}, "search": {"limit": 30, "remaining": 30, "used": 0, "reset": 9999999999}})
    @patch("src.reposcout.nodes.search_repositories", return_value=SAMPLE_REPOSITORIES)
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    def test_search_and_rank_flow(self, _mock_search, _mock_rate_limit, mock_client):
        mock_client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=RepositoryRequirement.model_validate({
                "language": "Python",
                "minimum_stars": 20,
                "active_within_days": 180,
                "keywords": ["python", "langgraph", "agent"],
                "licenses": ["MIT"],
                "hard_conditions": {"language": "Python", "minimum_stars": 20, "active_within_days": 180, "licenses": ["MIT"]},
                "soft_preferences": ["python", "langgraph", "agent"],
                "sort_targets": ["relevance"]
            })
        )
        result = build_graph().invoke(
            {"raw_requirement": "Python LangGraph agent，至少 20 stars，近期维护"}
        )
        self.assertIn("language:Python", result["query"])
        self.assertEqual(result["recommendations"][0]["full_name"], "example/langgraph-agent")
        self.assertGreater(result["recommendations"][0]["score"], 0)
        self.assertIn("最近半年仍有更新", result["recommendations"][0]["reasons"])
        self.assertIn("rate_limit", result)
        self.assertEqual(result["rate_limit"]["search"]["limit"], 30)
        self.assertEqual(result["requirement_parser"], "llm")

    @patch("src.reposcout.nodes._openai_client")
    @patch("src.reposcout.nodes.get_rate_limit", return_value={})
    @patch("src.reposcout.nodes.search_repositories", return_value=SAMPLE_REPOSITORIES)
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    def test_llm_requirement_parsing_with_mixed_language(
        self, _mock_search, _mock_rate_limit, mock_client
    ):
        mock_client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=RepositoryRequirement.model_validate({
                "language": "Python",
                "minimum_stars": 50,
                "active_within_days": 180,
                "keywords": ["python", "agent", "langgraph"],
                "licenses": ["MIT"],
                "hard_conditions": {},
                "soft_preferences": ["python", "agent"],
                "sort_targets": ["relevance"]
            })
        )
        result = build_graph().invoke(
            {"raw_requirement": "我想要一个 Python LangGraph agent，至少 50 stars，近期维护，最好 MIT 许可。"}
        )
        self.assertEqual(result["recommendations"][0]["full_name"], "example/langgraph-agent")
        self.assertIn("Python", result["query"])
        self.assertIn("stars:>=50", result["query"])

    @patch("src.reposcout.nodes._openai_client")
    @patch("src.reposcout.nodes.get_rate_limit", return_value={})
    @patch(
        "src.reposcout.nodes.search_repositories",
        return_value=[
            SAMPLE_REPOSITORIES[0],
            {
                **SAMPLE_REPOSITORIES[0],
                "full_name": "example/wrong-license",
                "license": "GPL-3.0",
            },
            {
                **SAMPLE_REPOSITORIES[0],
                "full_name": "example/stale",
                "pushed_at": "2024-01-01T00:00:00Z",
            },
        ],
    )
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    def test_hard_constraints_reject_invalid_candidates(
        self, _mock_search, _mock_rate_limit, mock_client
    ):
        mock_client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=RepositoryRequirement(
                language="Python",
                minimum_stars=20,
                active_within_days=180,
                keywords=["langgraph", "agent"],
                licenses=["MIT"],
                hard_conditions={
                    "language": "Python",
                    "minimum_stars": 20,
                    "active_within_days": 180,
                    "licenses": ["MIT"],
                },
            )
        )
        result = build_graph().invoke(
            {"raw_requirement": "Python LangGraph agent，至少 20 stars，近期维护，MIT"}
        )

        self.assertEqual(
            [item["full_name"] for item in result["recommendations"]],
            ["example/langgraph-agent"],
        )
        self.assertEqual(len(result["rejected_candidates"]), 2)

    @patch("src.reposcout.nodes._openai_client", side_effect=RuntimeError("offline"))
    @patch("src.reposcout.nodes.get_rate_limit", return_value={})
    @patch("src.reposcout.nodes.search_repositories", return_value=SAMPLE_REPOSITORIES)
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    def test_llm_failure_is_visible_and_falls_back_to_rules(
        self, _mock_search, _mock_rate_limit, _mock_client
    ):
        result = build_graph().invoke(
            {"raw_requirement": "Python LangGraph agent，至少 20 stars"}
        )

        self.assertEqual(result["requirement_parser"], "rules_fallback")
        self.assertIn("RuntimeError", result["warnings"][0])


if __name__ == "__main__":
    unittest.main()
