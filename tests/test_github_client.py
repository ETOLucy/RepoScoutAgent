import asyncio
import base64
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

import httpx

from src.reposcout.github_client import GitHubClient, GitHubSearchError

Handler = Callable[[httpx.Request], httpx.Response]


def _async_client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class GitHubClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_only_relevant_whitelisted_static_files(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "/git/trees/" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "sha": "commit-static",
                        "tree": [
                            {"path": "README.md", "type": "blob"},
                            {"path": "package.json", "type": "blob"},
                            {"path": "src/auth/saml.ts", "type": "blob"},
                            {"path": "src/theme/colors.ts", "type": "blob"},
                            {"path": "tests/auth/saml.test.ts", "type": "blob"},
                            {"path": "vendor/auth/saml.ts", "type": "blob"},
                            {"path": "assets/logo.png", "type": "blob"},
                        ],
                    },
                )
            if "/contents/" in request.url.path:
                content = base64.b64encode(request.url.path.encode()).decode()
                return httpx.Response(
                    200, json={"encoding": "base64", "content": content}
                )
            return httpx.Response(200, json=[])

        with tempfile.TemporaryDirectory() as directory:
            async with _async_client(handler) as transport_client:
                client = GitHubClient(transport_client, document_cache_dir=Path(directory))
                result = await client.fetch_repository_documents(
                    "example/repo", "main", implementation_terms=["SAML authentication"]
                )

        static = {
            item["path"]: item["source_type"]
            for item in result
            if item["source_type"] in {"manifest", "implementation"}
        }
        self.assertEqual(
            static,
            {"package.json": "manifest", "src/auth/saml.ts": "implementation"},
        )

    async def test_fetch_repository_documents_reads_readme_and_docs(self):
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

        with tempfile.TemporaryDirectory() as directory:
            async with _async_client(handler) as transport_client:
                client = GitHubClient(transport_client, document_cache_dir=Path(directory))
                result = await client.fetch_repository_documents("example/repo", "main")

        self.assertEqual([item["path"] for item in result], ["README.md", "docs/setup.md"])

    async def test_fetch_adds_release_issue_and_commit_sources(self):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if "/git/trees/" in request.url.path:
                return httpx.Response(200, json={"sha": "commit-1", "tree": []})
            if request.url.path.endswith("/releases"):
                return httpx.Response(
                    200,
                    json=[{"tag_name": "v1", "published_at": "2026-01-01", "body": "Stable"}],
                )
            if request.url.path.endswith("/issues"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "number": 7,
                            "title": "Feature request",
                            "state": "open",
                            "comments": 4,
                            "updated_at": "2026-01-02",
                            "body": "Needed feature",
                        },
                        {"number": 8, "title": "PR", "pull_request": {}},
                    ],
                )
            if request.url.path.endswith("/commits"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "sha": "abcdef1234567890",
                            "commit": {
                                "message": "Fix startup",
                                "author": {"date": "2026-01-03"},
                            },
                        }
                    ],
                )
            raise AssertionError(f"unexpected request: {request.url}")

        with tempfile.TemporaryDirectory() as directory:
            async with _async_client(handler) as transport_client:
                client = GitHubClient(transport_client, document_cache_dir=Path(directory))
                result = await client.fetch_repository_documents("example/repo", "main")
                first_call_count = len(calls)
                cached = await client.fetch_repository_documents("example/repo", "main")

        self.assertEqual(
            {item["source_type"] for item in result}, {"release", "issue", "commit"}
        )
        self.assertEqual(result, cached)
        self.assertEqual(len(calls), first_call_count + 1)

    async def test_search_maps_repository_and_limits_page_size(self):
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

        async with _async_client(handler) as transport_client:
            result = await GitHubClient(transport_client).search_repositories("agent", limit=100)

        self.assertEqual(result[0]["full_name"], "example/repo")
        self.assertEqual(result[0]["description"], "暂无项目描述")
        self.assertEqual(result[0]["license"], "Unknown")
        self.assertEqual(result[0]["pushed_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(result[0]["size"], 42)

    async def test_rate_limit_errors_are_not_retried(self):
        for status in (403, 429):
            calls = 0

            def handler(
                request: httpx.Request, response_status: int = status
            ) -> httpx.Response:
                nonlocal calls
                calls += 1
                return httpx.Response(response_status, request=request)

            with self.subTest(status=status):
                async with _async_client(handler) as transport_client:
                    client = GitHubClient(transport_client, backoff_seconds=0)
                    with self.assertRaisesRegex(GitHubSearchError, "请求受限"):
                        await client.search_repositories("agent")
                self.assertEqual(calls, 1)

    async def test_timeout_is_retried_with_a_finite_limit(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectTimeout("timed out", request=request)

        async with _async_client(handler) as transport_client:
            client = GitHubClient(transport_client, max_attempts=3, backoff_seconds=0)
            with self.assertRaisesRegex(GitHubSearchError, "无法连接 GitHub"):
                await client.search_repositories("agent")

        self.assertEqual(calls, 3)

    async def test_server_error_is_retried_then_succeeds(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(503, request=request)
            return httpx.Response(200, json={"items": []}, request=request)

        async with _async_client(handler) as transport_client:
            client = GitHubClient(transport_client, max_attempts=3, backoff_seconds=0)
            result = await client.search_repositories("agent")

        self.assertEqual(result, [])
        self.assertEqual(calls, 3)

    async def test_malformed_payload_is_converted_to_domain_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": {}}, request=request)

        async with _async_client(handler) as transport_client:
            with self.assertRaisesRegex(GitHubSearchError, "items 列表"):
                await GitHubClient(transport_client).search_repositories("agent")

    async def test_shared_semaphore_limits_concurrency(self):
        active = 0
        peak = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200, json={"items": []}, request=request)

        async with _async_client(handler) as transport_client:
            client = GitHubClient(transport_client, max_concurrency=2)
            await asyncio.gather(*(client.search_repositories(str(item)) for item in range(6)))

        self.assertEqual(peak, 2)

    async def test_cancellation_is_not_retried(self):
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            await asyncio.sleep(10)
            return httpx.Response(200, json={"items": []}, request=request)

        async with _async_client(handler) as transport_client:
            client = GitHubClient(transport_client, backoff_seconds=0)
            task = asyncio.create_task(client.search_repositories("agent"))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(calls, 1)

    async def test_rate_limit_uses_response_headers_without_extra_request(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={"items": []},
                headers={
                    "X-RateLimit-Resource": "search",
                    "X-RateLimit-Limit": "30",
                    "X-RateLimit-Remaining": "28",
                    "X-RateLimit-Used": "2",
                    "X-RateLimit-Reset": "123456",
                },
                request=request,
            )

        async with _async_client(handler) as transport_client:
            client = GitHubClient(transport_client)
            await client.search_repositories("agent")
            rate_limit = await client.get_rate_limit()

        self.assertEqual(calls, 1)
        self.assertEqual(rate_limit["search"]["remaining"], 28)


if __name__ == "__main__":
    unittest.main()
