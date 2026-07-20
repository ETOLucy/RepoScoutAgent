import asyncio
import unittest
from os import environ
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.reposcout.evidence import (
    validate_evidence,
    validate_implementation_evidence,
)
from src.reposcout.github_client import GitHubSearchError
from src.reposcout.graph import build_graph
from src.reposcout.nodes import (
    deep_code_search,
    match_documents,
    set_requirement_timeout,
    understand_requirement,
)
from src.reposcout.search.models import (
    CorePurposeMatch,
    CriterionMatch,
    RepositoryAssessment,
    RequirementItem,
    SearchIntent,
)
from src.reposcout.web_search import WebRepositoryHit

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
        get_repository=AsyncMock(return_value=(repositories or [REPOSITORY])[0]),
        fetch_repository_documents=AsyncMock(),
        fetch_code_snapshot=AsyncMock(),
        get_rate_limit=AsyncMock(return_value={}),
    )
    if isinstance(documents, Exception):
        client.fetch_repository_documents.side_effect = documents
    else:
        client.fetch_repository_documents.return_value = documents or []
    return client


class GraphTest(unittest.IsolatedAsyncioTestCase):
    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    async def test_deep_code_search_is_explicit_and_returns_repo_map(self):
        github = github_mock()
        github.fetch_code_snapshot.return_value = {
            "repository": "example/photo-app",
            "commit_sha": "abc",
            "tree_truncated": False,
            "total_code_files": 1,
            "files": [{"path": "src/main.py", "content": "def run(): pass"}],
        }
        state = {
            "deep_code_search": True,
            "raw_requirement": "understand the code",
            "recommendations": [REPOSITORY],
        }

        with patch("src.reposcout.nodes.get_github_client", return_value=github):
            result = await deep_code_search(state)

        self.assertEqual(result["code_understanding"][0]["mode"], "broad")
        self.assertIn("run", result["code_understanding"][0]["repo_map"])
        github.fetch_code_snapshot.assert_awaited_once_with(
            "example/photo-app", "main", max_files=24, max_total_chars=240_000
        )

    async def test_deep_code_search_disabled_does_no_io(self):
        result = await deep_code_search({"deep_code_search": False})
        self.assertEqual(result, {"code_understanding": []})

    @patch("src.reposcout.nodes.parse_search_intent_with_llm")
    @patch.dict(environ, {"OPENAI_API_KEY": "test-key"})
    async def test_requirement_timeout_falls_back_to_rules(self, parse_intent):
        async def slow_parse(*_args):
            await asyncio.sleep(1)

        parse_intent.side_effect = slow_parse
        set_requirement_timeout(0.001)
        try:
            result = await understand_requirement(
                {"raw_requirement": "find GitHub repository discovery tool"}
            )
        finally:
            set_requirement_timeout(15)

        self.assertEqual(result["requirement_parser"], "rules_fallback")
        self.assertIn("超时", result["warnings"][0])

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

        self.assertEqual(
            github.search_repositories.await_count,
            len(result["search_plan"]["queries"]),
        )
        github.fetch_repository_documents.assert_awaited_once_with(
            "example/photo-app",
            "main",
            max_documents=6,
            implementation_terms=["photo management", "python", "photo", "backup"],
        )
        self.assertGreater(len(result["executed_queries"]), 1)
        self.assertEqual(result["recommendations"][0]["document_paths"], ["README.md"])
        self.assertIn("match_documents", result["node_timings"])
        self.assertGreaterEqual(result["node_timings"]["match_documents"], 0)

    @patch.dict(environ, {"OPENAI_API_KEY": ""})
    async def test_web_discovery_is_hydrated_and_merged_with_github(self):
        github = github_mock([], DOCUMENTS)
        web = SimpleNamespace(
            search_repositories=AsyncMock(
                return_value=[
                    WebRepositoryHit(
                        full_name="example/photo-app",
                        title="Photo App",
                        url="https://github.com/example/photo-app",
                        description="Web result",
                        query="photo backup",
                        source="searxng_web_search",
                    )
                ]
            )
        )
        with (
            patch("src.reposcout.nodes.get_github_client", return_value=github),
            patch("src.reposcout.nodes.get_web_search_client", return_value=web),
        ):
            result = await build_graph().ainvoke(
                {"raw_requirement": "find self hosted photo backup project"}
            )

        self.assertEqual(result["candidates"][0]["full_name"], "example/photo-app")
        self.assertIn(
            "searxng_web_search", result["candidates"][0]["discovery"]["sources"]
        )
        github.get_repository.assert_awaited_once_with("example/photo-app")

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

        async def fetch(
            full_name: str,
            _branch: str,
            max_documents: int = 6,
            implementation_terms: list[str] | None = None,
        ):
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
        result = validate_evidence(assessment, DOCUMENTS)
        self.assertEqual(result.criteria[0].status, "unknown")

    def test_wrong_commit_sha_is_downgraded_to_unknown(self):
        assessment = RepositoryAssessment(
            summary="test",
            criteria=[
                CriterionMatch(
                    requirement_id="face",
                    status="satisfied",
                    evidence="face recognition",
                    source_path="README.md",
                    source_commit_sha="wrong-sha",
                )
            ],
        )
        documents = [{**DOCUMENTS[0], "commit_sha": "actual-sha"}]

        result = validate_evidence(assessment, documents)

        self.assertEqual(result.criteria[0].status, "unknown")
        self.assertIsNone(result.criteria[0].source_commit_sha)

    @patch("src.reposcout.nodes._openai_client")
    @patch.dict(
        environ,
        {"OPENAI_API_KEY": "test-key", "REPOSCOUT_RETRIEVAL_MODE": "full"},
    )
    async def test_only_required_violation_is_returned_as_near_match(self, mock_client):
        assessment = RepositoryAssessment(
            summary="conflicts with requirement",
            criteria=[
                CriterionMatch(
                    requirement_id="docker",
                    status="violated",
                    evidence="Docker deployment",
                    source_path="README.md",
                )
            ],
        )
        mock_client.return_value.responses.parse = AsyncMock(
            return_value=SimpleNamespace(output_parsed=assessment)
        )
        state = {
            "search_intent": SearchIntent(
                goal="deployment",
                requirements=[
                    RequirementItem(id="docker", description="requires Docker")
                ],
                keywords=["deployment"],
            ).model_dump(),
            "document_candidates": [{**REPOSITORY, "documents": DOCUMENTS}],
        }

        result = await match_documents(state)

        self.assertEqual(result["recommendations"][0]["match_kind"], "near_miss")
        self.assertIn("明确冲突", result["recommendations"][0]["risks"][0])
        self.assertIn("没有发现满足全部硬条件", result["warnings"][0])

    @patch("src.reposcout.nodes._openai_client")
    @patch.dict(
        environ,
        {"OPENAI_API_KEY": "test-key", "REPOSCOUT_RETRIEVAL_MODE": "full"},
    )
    async def test_required_violation_is_rejected_when_eligible_result_exists(
        self, mock_client
    ):
        eligible = RepositoryAssessment(
            summary="eligible",
            criteria=[
                CriterionMatch(
                    requirement_id="docker",
                    status="satisfied",
                    evidence="Docker deployment",
                    source_path="README.md",
                )
            ],
        )
        violation = RepositoryAssessment(
            summary="conflict",
            criteria=[
                CriterionMatch(
                    requirement_id="docker",
                    status="violated",
                    evidence="Docker deployment",
                    source_path="README.md",
                )
            ],
        )
        mock_client.return_value.responses.parse = AsyncMock(
            side_effect=[
                SimpleNamespace(output_parsed=eligible),
                SimpleNamespace(output_parsed=violation),
            ]
        )
        state = {
            "search_intent": SearchIntent(
                goal="deployment",
                requirements=[
                    RequirementItem(id="docker", description="requires Docker")
                ],
                keywords=["deployment"],
            ).model_dump(),
            "document_candidates": [
                {**REPOSITORY, "documents": DOCUMENTS},
                {
                    **REPOSITORY,
                    "full_name": "example/no-docker",
                    "documents": DOCUMENTS,
                },
            ],
        }

        result = await match_documents(state)

        self.assertEqual(
            [item["full_name"] for item in result["recommendations"]],
            ["example/photo-app"],
        )
        self.assertEqual(result["recommendations"][0]["match_kind"], "eligible")
        self.assertEqual(result["rejected_candidates"][0]["full_name"], "example/no-docker")

    @patch("src.reposcout.nodes._openai_client")
    @patch.dict(
        environ,
        {"OPENAI_API_KEY": "test-key", "REPOSCOUT_RETRIEVAL_MODE": "full"},
    )
    async def test_mismatched_core_purpose_is_rejected(self, mock_client):
        assessment = RepositoryAssessment(
            summary="A vulnerability dataset, not a repository discovery product",
            core_purpose=CorePurposeMatch(
                status="mismatched",
                evidence="dataset of vulnerability fixes",
                source_path="README.md",
            ),
            criteria=[
                CriterionMatch(
                    requirement_id="discovery",
                    status="satisfied",
                    evidence="repository discovery",
                    source_path="README.md",
                )
            ],
        )
        mock_client.return_value.responses.parse = AsyncMock(
            return_value=SimpleNamespace(output_parsed=assessment)
        )
        documents = [
            {
                **DOCUMENTS[0],
                "content": "A dataset of vulnerability fixes mentioning repository discovery.",
            }
        ]
        state = {
            "search_intent": SearchIntent(
                goal="find repository discovery products",
                requirements=[
                    RequirementItem(
                        id="discovery", description="repository discovery"
                    )
                ],
                keywords=["repository discovery"],
            ).model_dump(),
            "document_candidates": [{**REPOSITORY, "documents": documents}],
        }

        result = await match_documents(state)

        self.assertEqual(result["recommendations"], [])
        self.assertEqual(
            result["rejected_candidates"][0]["full_name"], "example/photo-app"
        )
        self.assertIn("核心用途", result["rejected_candidates"][0]["reasons"][0])

    def test_manifest_alone_cannot_prove_implementation(self):
        assessment = RepositoryAssessment(
            summary="dependency only",
            criteria=[
                CriterionMatch(
                    requirement_id="sso",
                    status="satisfied",
                    implementation_status="implemented",
                    implementation_evidence='"saml2-js"',
                    implementation_source_path="package.json",
                    implementation_source_commit_sha="abc",
                )
            ],
        )
        documents = [
            {
                "path": "package.json",
                "content": '{"dependencies":{"saml2-js":"1.0.0"}}',
                "source_type": "manifest",
                "commit_sha": "abc",
            }
        ]

        result = validate_implementation_evidence(assessment, documents)

        self.assertEqual(result.criteria[0].implementation_status, "uncertain")

    def test_source_quote_can_prove_static_implementation(self):
        assessment = RepositoryAssessment(
            summary="source evidence",
            criteria=[
                CriterionMatch(
                    requirement_id="sso",
                    status="satisfied",
                    implementation_status="implemented",
                    implementation_evidence="validateSamlResponse",
                    implementation_source_path="src/auth/saml.ts",
                    implementation_source_commit_sha="abc",
                )
            ],
        )
        documents = [
            {
                "path": "src/auth/saml.ts",
                "content": "export function validateSamlResponse(input) {}",
                "source_type": "implementation",
                "commit_sha": "abc",
            }
        ]

        result = validate_implementation_evidence(assessment, documents)

        self.assertEqual(result.criteria[0].implementation_status, "implemented")


if __name__ == "__main__":
    unittest.main()
