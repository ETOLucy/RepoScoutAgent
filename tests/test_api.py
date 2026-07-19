import unittest
from unittest.mock import AsyncMock, patch

import httpx

from main import app


class StreamingGraph:
    async def astream(self, _state, stream_mode):
        self.stream_mode = stream_mode
        yield {"validate_request": {}}
        yield {"generate_report": {"report": "done"}}


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_endpoint(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    async def test_json_search_uses_async_graph(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done", "query": "agent archived:false"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/search", json={"requirement": "find an agent"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report"], "done")
        graph.ainvoke.assert_awaited_once()

    async def test_sse_stream_exposes_progress_and_result(self):
        graph = StreamingGraph()
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/search/stream", json={"requirement": "find an agent"}
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: progress", response.text)
        self.assertIn('event: result\ndata: {"requirement":{}', response.text)
        self.assertEqual(graph.stream_mode, "updates")


if __name__ == "__main__":
    unittest.main()
