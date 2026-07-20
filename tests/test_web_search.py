import asyncio
import unittest

import httpx

from src.reposcout.web_search import (
    BraveWebSearchClient,
    CompositeWebSearchProvider,
    SearXNGSearchProvider,
    WebRepositoryHit,
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
                    "web": {
                        "results": [
                            {
                                "title": "Immich",
                                "url": "https://github.com/immich-app/immich",
                                "description": "Photo management",
                            }
                        ]
                    }
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = BraveWebSearchClient("key", http, max_queries=2)
            hits = await client.search_repositories(["photos", "photo backup"])

        self.assertEqual([item.full_name for item in hits], ["immich-app/immich"])
        self.assertEqual(hits[0].query, "photos")

    async def test_total_time_budget_cancels_slow_web_queries(self):
        class SlowClient(BraveWebSearchClient):
            async def _search(self, query):
                await asyncio.Future()

        client = SlowClient("key", timeout_seconds=0.01)
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
        self.assertEqual(hits[0].providers, ("searxng",))

    async def test_composite_merges_sources_and_tolerates_partial_failure(self):
        class Provider:
            def __init__(self, result=None, error=None):
                self.result = result or []
                self.error = error
                self.closed = False

            async def search_repositories(self, _queries):
                if self.error:
                    raise self.error
                return self.result

            async def close(self):
                self.closed = True

        searxng = Provider(
            [
                WebRepositoryHit(
                    "immich-app/immich",
                    "Immich",
                    "https://github.com/immich-app/immich",
                    "Photos",
                    "photos",
                    ("searxng",),
                )
            ]
        )
        brave = Provider(
            [
                WebRepositoryHit(
                    "immich-app/immich",
                    "Immich",
                    "https://github.com/immich-app/immich",
                    "Photos",
                    "photos",
                    ("brave",),
                )
            ]
        )
        composite = CompositeWebSearchProvider([searxng, brave])

        hits = await composite.search_repositories(["photos"])
        self.assertEqual(hits[0].providers, ("searxng", "brave"))

        fallback = CompositeWebSearchProvider(
            [Provider(error=WebSearchError("offline")), brave]
        )
        hits = await fallback.search_repositories(["photos"])
        self.assertEqual(hits[0].providers, ("brave",))

        await composite.close()
        self.assertTrue(searxng.closed)
        self.assertTrue(brave.closed)
