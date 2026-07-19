import unittest
from unittest.mock import AsyncMock, patch

import httpx

from main import app


class StreamingGraph:
    async def astream(self, _state, stream_mode):
        self.stream_mode = stream_mode
        yield {"validate_request": {"node_timings": {"validate_request": 1.5}}}
        yield {
            "generate_report": {
                "report": "done",
                "node_timings": {"validate_request": 1.5, "generate_report": 2.0},
            }
        }


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
        self.assertTrue(response.json()["conversation_id"])
        self.assertEqual(response.json()["turn"], 1)
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
        self.assertIn("duration_ms", response.text)
        self.assertIn('event: result\ndata: {"requirement":{}', response.text)
        self.assertEqual(graph.stream_mode, "updates")

    async def test_follow_up_reuses_conversation_context(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post("/api/search", json={"requirement": "find Python RAG"})
                conversation_id = first.json()["conversation_id"]
                second = await client.post(
                    "/api/search",
                    json={
                        "requirement": "Rust instead",
                        "conversation_id": conversation_id,
                    },
                )

        self.assertEqual(second.json()["turn"], 2)
        second_state = graph.ainvoke.await_args_list[1].args[0]
        self.assertIn("find Python RAG", second_state["raw_requirement"])
        self.assertIn("Rust instead", second_state["raw_requirement"])


if __name__ == "__main__":
    unittest.main()
