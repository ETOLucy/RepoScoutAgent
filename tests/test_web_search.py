import asyncio
import unittest

import httpx

from src.reposcout.web_search import (
    SearXNGSearchProvider,
    WebSearchError,
    github_repository_name,
)


class WebSearchTest(unittest.IsolatedAsyncioTestCase):
    def test_extracts_only_repository_landing_pages(self):
        self.assertEqual(
            github_repository_name("https://github.com/immich-app/immich/issues/1"),
            "immich-app/immich",
        )
        self.assertIsNone(github_repository_name("https://github.com/topics/photos"))
        self.assertIsNone(github_repository_name("https://example.com/org/repo"))

    async def test_deduplicates_repository_hits_across_queries(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("site:github.com", request.url.params["q"])
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Immich",
                            "url": "https://github.com/immich-app/immich",
                            "content": "Photo management",
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = SearXNGSearchProvider("http://searxng.local", http, max_queries=2)
            hits = await client.search_repositories(["photos", "photo backup"])

        self.assertEqual([item.full_name for item in hits], ["immich-app/immich"])
        self.assertEqual(hits[0].query, "photos")

    async def test_total_time_budget_cancels_slow_web_queries(self):
        class SlowClient(SearXNGSearchProvider):
            async def _search(self, query):
                await asyncio.Future()

        client = SlowClient("http://searxng.local", timeout_seconds=0.01)
        with self.assertRaisesRegex(WebSearchError, "time budget"):
            await client.search_repositories(["photos"])
        await client.close()

    async def test_searxng_parses_json_repository_results(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/search")
            self.assertEqual(request.url.params["format"], "json")
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Immich",
                            "url": "https://github.com/immich-app/immich",
                            "content": "Self-hosted photo management",
                        },
                        {"title": "Other", "url": "https://example.com/other"},
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = SearXNGSearchProvider("http://searxng.local", http)
            hits = await client.search_repositories(["photo backup"])

        self.assertEqual([item.full_name for item in hits], ["immich-app/immich"])
        self.assertEqual(hits[0].source, "searxng_web_search")
