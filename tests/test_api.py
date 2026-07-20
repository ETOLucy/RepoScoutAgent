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

    async def test_frontend_explains_deep_code_mode(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("什么时候开启 Deep Code", response.text)
        self.assertIn("不执行候选代码", response.text)
        self.assertIn("新任务", response.text)
        self.assertIn("证据矩阵", response.text)
        self.assertIn("完整搜索与快速降级", response.text)

    async def test_json_search_uses_async_graph(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done", "query": "agent archived:false"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/search", json={"requirement": "find an agent"})
                restored = await client.get(
                    f"/api/research/{response.json()['research_id']}"
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report"], "done")
        self.assertTrue(response.json()["conversation_id"])
        self.assertTrue(response.json()["research_id"])
        self.assertEqual(response.json()["turn"], 1)
        graph.ainvoke.assert_awaited_once()
        self.assertFalse(graph.ainvoke.await_args.args[0]["deep_code_search"])
        self.assertFalse(graph.ainvoke.await_args.args[0]["allow_requirement_fallback"])

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["report"], "done")

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

    async def test_search_passes_explicit_deep_code_mode(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/api/search",
                    json={"requirement": "find an agent", "deep_code_search": True},
                )

        self.assertTrue(graph.ainvoke.await_args.args[0]["deep_code_search"])

    async def test_search_passes_explicit_requirement_fallback_mode(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/api/search",
                    json={
                        "requirement": "find an agent project",
                        "allow_requirement_fallback": True,
                    },
                )

        self.assertTrue(
            graph.ainvoke.await_args.args[0]["allow_requirement_fallback"]
        )

    async def test_interactive_search_saves_checkpoint_and_confirm_resumes(self):
        graph = AsyncMock()
        graph.ainvoke.side_effect = [
            {
                "report": "Please confirm",
                "search_intent": {"goal": "agent project"},
                "interaction": {
                    "type": "requirement_review",
                    "status": "pending",
                    "goal": "agent project",
                    "criteria": [],
                },
                "conversation_id": "ignored",
            },
            {
                "report": "done",
                "query": "agent archived:false",
                "solutions": [{"id": "solution"}],
                "interaction": {},
            },
        ]
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                paused = await client.post(
                    "/api/search",
                    json={"requirement": "find an agent project", "interactive": True},
                )
                resumed = await client.post(
                    f"/api/research/{paused.json()['research_id']}/resume",
                    json={"action": "confirm"},
                )

        self.assertEqual(paused.json()["interaction"]["status"], "pending")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["report"], "done")
        resumed_state = graph.ainvoke.await_args_list[1].args[0]
        self.assertTrue(resumed_state["requirement_reviewed"])
        self.assertEqual(resumed_state["search_intent"]["goal"], "agent project")

    async def test_interactive_edit_reparses_and_pauses_again(self):
        graph = AsyncMock()
        graph.ainvoke.side_effect = [
            {
                "report": "confirm",
                "search_intent": {"goal": "generic agent"},
                "interaction": {
                    "type": "requirement_review",
                    "status": "pending",
                    "goal": "generic agent",
                    "criteria": [],
                },
            },
            {
                "report": "confirm revision",
                "search_intent": {"goal": "internship agent"},
                "interaction": {
                    "type": "requirement_review",
                    "status": "pending",
                    "goal": "internship agent",
                    "criteria": [],
                },
            },
        ]
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                paused = await client.post(
                    "/api/search",
                    json={"requirement": "find an agent project", "interactive": True},
                )
                revised = await client.post(
                    f"/api/research/{paused.json()['research_id']}/resume",
                    json={"action": "edit", "feedback": "适合大厂实习和二开"},
                )

        self.assertEqual(revised.status_code, 200)
        self.assertEqual(revised.json()["interaction"]["goal"], "internship agent")
        revised_state = graph.ainvoke.await_args_list[1].args[0]
        self.assertFalse(revised_state["requirement_reviewed"])
        self.assertNotIn("search_intent", revised_state)
        self.assertIn("适合大厂实习和二开", revised_state["raw_requirement"])

    async def test_conversation_history_lists_and_restores_messages(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                search = await client.post(
                    "/api/search", json={"requirement": "find history test project"}
                )
                conversation_id = search.json()["conversation_id"]
                summaries = await client.get("/api/conversations")
                detail = await client.get(f"/api/conversations/{conversation_id}")

        self.assertTrue(
            any(item["id"] == conversation_id for item in summaries.json())
        )
        self.assertEqual(
            [item["role"] for item in detail.json()["messages"]],
            ["user", "assistant"],
        )

    async def test_deep_code_tool_validates_repository_and_returns_analysis(self):
        github = AsyncMock()
        github.get_repository.return_value = {"full_name": "example/repo"}
        expected = {"repository": "example/repo", "summary": "worker service"}
        with (
            patch("main.get_github_client", return_value=github),
            patch("main.inspect_repository_code", AsyncMock(return_value=expected)),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                invalid = await client.post(
                    "/api/tools/deep-code-search", json={"repository": "invalid"}
                )
                response = await client.post(
                    "/api/tools/deep-code-search",
                    json={"repository": "example/repo", "requirement": "explain it"},
                )

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(response.json(), expected)

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

    async def test_standalone_follow_up_replaces_previous_topic(self):
        graph = AsyncMock()
        graph.ainvoke.return_value = {"report": "done"}
        with patch("main.GRAPH", graph):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/api/search", json={"requirement": "想找自托管照片项目"}
                )
                await client.post(
                    "/api/search",
                    json={
                        "requirement": "想找一个 GitHub repo 推荐项目，尽量可以实操",
                        "conversation_id": first.json()["conversation_id"],
                    },
                )

        second_state = graph.ainvoke.await_args_list[1].args[0]
        self.assertNotIn("照片", second_state["raw_requirement"])


if __name__ == "__main__":
    unittest.main()
