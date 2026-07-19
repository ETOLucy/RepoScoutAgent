import base64
import unittest
from collections.abc import Callable
from unittest.mock import patch

import httpx

from src.reposcout.github_client import (
    GitHubSearchError,
    fetch_repository_documents,
    search_repositories,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client_with(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _status_handler(status: int) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    return handler


class GitHubClientTest(unittest.TestCase):
    def test_fetch_repository_documents_reads_readme_and_docs(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "/git/trees/" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "tree": [
                            {"path": "src/main.py", "type": "blob"},
                            {"path": "docs/setup.md", "type": "blob"},
                            {"path": "README.md", "type": "blob"},
                        ]
                    },
                )
            path = "README" if request.url.path.endswith("README.md") else "setup"
            content = base64.b64encode(path.encode()).decode()
            return httpx.Response(200, json={"encoding": "base64", "content": content})

        with patch(
            "src.reposcout.github_client.httpx.Client",
            return_value=_client_with(handler),
        ):
            result = fetch_repository_documents("example/repo", "main")

        self.assertEqual([item["path"] for item in result], ["README.md", "docs/setup.md"])

    def test_search_maps_repository_and_limits_page_size(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params["per_page"], "30")
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "full_name": "example/repo",
                            "html_url": "https://github.com/example/repo",
                            "description": None,
                            "language": "Python",
                            "stargazers_count": 10,
                            "forks_count": 2,
                            "open_issues_count": 1,
                            "license": None,
                            "topics": None,
                            "archived": False,
                            "disabled": False,
                            "fork": False,
                            "size": 42,
                            "default_branch": "main",
                            "updated_at": "2026-01-01T00:00:00Z",
                            "pushed_at": None,
                        }
                    ]
                },
            )

        with patch(
            "src.reposcout.github_client.httpx.Client",
            return_value=_client_with(handler),
        ):
            result = search_repositories("agent", limit=100)

        self.assertEqual(result[0]["full_name"], "example/repo")
        self.assertEqual(result[0]["description"], "暂无项目描述")
        self.assertEqual(result[0]["license"], "Unknown")
        self.assertEqual(result[0]["pushed_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(result[0]["size"], 42)

    def test_rate_limit_errors_are_user_visible(self):
        for status in (403, 429):
            with (
                self.subTest(status=status),
                patch(
                    "src.reposcout.github_client.httpx.Client",
                    return_value=_client_with(_status_handler(status)),
                ),
                self.assertRaisesRegex(GitHubSearchError, "请求受限"),
            ):
                search_repositories("agent")

    def test_timeout_is_converted_to_domain_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)

        with (
            patch(
                "src.reposcout.github_client.httpx.Client",
                return_value=_client_with(handler),
            ),
            self.assertRaisesRegex(GitHubSearchError, "无法连接 GitHub"),
        ):
            search_repositories("agent")

    def test_malformed_json_is_converted_to_domain_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not-json")

        with (
            patch(
                "src.reposcout.github_client.httpx.Client",
                return_value=_client_with(handler),
            ),
            self.assertRaisesRegex(GitHubSearchError, "无法解析的 JSON"),
        ):
            search_repositories("agent")

    def test_malformed_payload_is_converted_to_domain_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": {"unexpected": "object"}})

        with (
            patch(
                "src.reposcout.github_client.httpx.Client",
                return_value=_client_with(handler),
            ),
            self.assertRaisesRegex(GitHubSearchError, "items 列表"),
        ):
            search_repositories("agent")


if __name__ == "__main__":
    unittest.main()
