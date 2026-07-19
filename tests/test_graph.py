import unittest
from os import environ
from types import SimpleNamespace
from unittest.mock import patch

from src.reposcout.graph import build_graph
from src.reposcout.nodes import _validate_evidence
from src.reposcout.search.models import (
    CriterionMatch,
    RepositoryAssessment,
    RequirementItem,
    SearchIntent,
)

REPOSITORY = {
    "full_name": "example/photo-app",
    "url": "https://github.com/example/photo-app",
    "description": "Self-hosted photos",
    "language": "TypeScript",
    "stars": 500,
    "forks": 20,
    "open_issues": 3,
    "license": "MIT",
    "topics": ["photos"],
    "archived": False,
    "disabled": False,
    "fork": False,
    "size": 100,
    "default_branch": "main",
    "updated_at": "2099-01-01T00:00:00Z",
    "pushed_at": "2099-01-01T00:00:00Z",
}
DOCUMENTS = [
    {
        "path": "README.md",
        "url": "https://github.com/example/photo-app/blob/main/README.md",
        "content": "Private photo backup with face recognition and Docker deployment.",
    }
]


class GraphTest(unittest.TestCase):
    def test_invalid_requirement_stops_early(self):
        result = build_graph().invoke({"raw_requirement": "hi"})
        self.assertIn("至少描述", result["report"])
        self.assertNotIn("query", result)

    @patch("src.reposcout.nodes.get_rate_limit", return_value={})
    @patch("src.reposcout.nodes.fetch_repository_documents", return_value=DOCUMENTS)
    @patch("src.reposcout.nodes.search_repositories", return_value=[REPOSITORY])
    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    def test_rule_fallback_searches_and_reads_documents(
        self, mock_search, mock_documents, _mock_rate_limit
    ):
        result = build_graph().invoke({"raw_requirement": "find Python photo backup project"})

        mock_search.assert_called_once()
        mock_documents.assert_called_once_with("example/photo-app", "main", max_documents=6)
        self.assertEqual(result["recommendations"][0]["document_paths"], ["README.md"])
        self.assertIn("README/docs", result["report"])

    @patch("src.reposcout.nodes.get_rate_limit", return_value={})
    @patch("src.reposcout.nodes.fetch_repository_documents", return_value=DOCUMENTS)
    @patch("src.reposcout.nodes.search_repositories", return_value=[REPOSITORY])
    @patch("src.reposcout.nodes._openai_client")
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    def test_llm_matches_each_requirement_with_document_evidence(
        self, mock_client, _mock_search, _mock_documents, _mock_rate_limit
    ):
        intent = SearchIntent(
            goal="self-host photos",
            requirements=[
                RequirementItem(id="face", description="支持人脸识别"),
                RequirementItem(id="docker", description="支持 Docker 部署"),
            ],
            keywords=["self-hosted photos", "face recognition"],
            minimum_stars=999,
        )
        assessment = RepositoryAssessment(
            summary="支持照片管理和人脸识别",
            criteria=[
                CriterionMatch(
                    requirement_id="face",
                    status="satisfied",
                    evidence="face recognition",
                    source_path="README.md",
                )
            ],
        )
        mock_client.return_value.responses.parse.side_effect = [
            SimpleNamespace(output_parsed=intent),
            SimpleNamespace(output_parsed=assessment),
        ]

        result = build_graph().invoke({"raw_requirement": "找一个支持人脸识别的照片项目"})

        self.assertNotIn("stars:", result["query"])
        self.assertEqual(result["recommendations"][0]["criteria"][0]["status"], "satisfied")
        self.assertEqual(result["recommendations"][0]["criteria"][1]["status"], "unknown")
        self.assertGreater(result["recommendations"][0]["score"], 45)

    @patch("src.reposcout.nodes.get_rate_limit", return_value={})
    @patch("src.reposcout.nodes.fetch_repository_documents", return_value=[])
    @patch("src.reposcout.nodes.search_repositories", return_value=[REPOSITORY])
    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    def test_repository_without_readme_or_docs_is_rejected(
        self, _mock_search, _mock_documents, _mock_rate_limit
    ):
        result = build_graph().invoke({"raw_requirement": "find photo backup project"})

        self.assertEqual(result["recommendations"], [])
        self.assertIn("README 或 docs", result["rejected_candidates"][0]["reasons"][0])

    def test_unverifiable_llm_quote_is_downgraded_to_unknown(self):
        assessment = RepositoryAssessment(
            summary="test",
            criteria=[
                CriterionMatch(
                    requirement_id="face",
                    status="satisfied",
                    evidence="invented quote",
                    source_path="README.md",
                )
            ],
        )

        result = _validate_evidence(assessment, DOCUMENTS)

        self.assertEqual(result.criteria[0].status, "unknown")
        self.assertIsNone(result.criteria[0].evidence)

    def test_unverifiable_violation_is_also_downgraded(self):
        assessment = RepositoryAssessment(
            summary="test",
            criteria=[
                CriterionMatch(
                    requirement_id="docker",
                    status="violated",
                    evidence="Docker is unsupported",
                    source_path="README.md",
                )
            ],
        )

        result = _validate_evidence(assessment, DOCUMENTS)

        self.assertEqual(result.criteria[0].status, "unknown")


if __name__ == "__main__":
    unittest.main()
