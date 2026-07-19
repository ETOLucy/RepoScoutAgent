import unittest
from os import environ
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.reposcout.github_client import GitHubSearchError
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


def github_mock(
    repositories: list[dict] | None = None,
    documents: list[dict] | Exception | None = None,
) -> SimpleNamespace:
    client = SimpleNamespace(
        search_repositories=AsyncMock(return_value=repositories or []),
        fetch_repository_documents=AsyncMock(),
        get_rate_limit=AsyncMock(return_value={}),
    )
    if isinstance(documents, Exception):
        client.fetch_repository_documents.side_effect = documents
    else:
        client.fetch_repository_documents.return_value = documents or []
    return client


class GraphTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_requirement_stops_early(self):
        result = await build_graph().ainvoke({"raw_requirement": "hi"})
        self.assertIn("至少描述", result["report"])
        self.assertNotIn("query", result)

    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    async def test_rule_fallback_searches_and_reads_documents(self):
        github = github_mock([REPOSITORY], DOCUMENTS)
        with patch("src.reposcout.nodes.get_github_client", return_value=github):
            result = await build_graph().ainvoke(
                {"raw_requirement": "find Python photo backup project"}
            )

        github.search_repositories.assert_awaited_once()
        github.fetch_repository_documents.assert_awaited_once_with(
            "example/photo-app", "main", max_documents=6
        )
        self.assertEqual(result["recommendations"][0]["document_paths"], ["README.md"])

    @patch("src.reposcout.nodes._openai_client")
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    async def test_llm_matches_each_requirement_with_document_evidence(self, mock_client):
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
        mock_client.return_value.responses.parse = AsyncMock(
            side_effect=[
                SimpleNamespace(output_parsed=intent),
                SimpleNamespace(output_parsed=assessment),
            ]
        )
        github = github_mock([REPOSITORY], DOCUMENTS)
        with patch("src.reposcout.nodes.get_github_client", return_value=github):
            result = await build_graph().ainvoke(
                {"raw_requirement": "找一个支持人脸识别的照片项目"}
            )

        self.assertNotIn("stars:", result["query"])
        self.assertEqual(result["recommendations"][0]["criteria"][0]["status"], "satisfied")
        self.assertEqual(result["recommendations"][0]["criteria"][1]["status"], "unknown")

    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    async def test_repository_without_readme_or_docs_is_rejected(self):
        github = github_mock([REPOSITORY], [])
        with patch("src.reposcout.nodes.get_github_client", return_value=github):
            result = await build_graph().ainvoke({"raw_requirement": "find photo backup project"})

        self.assertEqual(result["recommendations"], [])
        self.assertIn("README 或 docs", result["rejected_candidates"][0]["reasons"][0])

    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    async def test_one_repository_failure_returns_partial_success(self):
        second = {**REPOSITORY, "full_name": "example/broken"}
        github = github_mock([REPOSITORY, second], DOCUMENTS)

        async def fetch(full_name: str, _branch: str, max_documents: int = 6):
            if full_name == "example/broken":
                raise GitHubSearchError("timeout")
            return DOCUMENTS[:max_documents]

        github.fetch_repository_documents.side_effect = fetch
        with patch("src.reposcout.nodes.get_github_client", return_value=github):
            result = await build_graph().ainvoke({"raw_requirement": "find photo backup project"})

        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["rejected_candidates"][0]["full_name"], "example/broken")
        self.assertIn("读取失败", result["rejected_candidates"][0]["reasons"][0])

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


if __name__ == "__main__":
    unittest.main()
