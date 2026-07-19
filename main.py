from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.reposcout import build_graph
from src.reposcout.conversations import ConversationStore
from src.reposcout.github_client import GitHubClient, set_github_client

load_dotenv()

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
GRAPH = build_graph()
CONVERSATIONS = ConversationStore()


class SearchRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=80)


class SearchResponse(BaseModel):
    requirement: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    executed_queries: list[str] = Field(default_factory=list)
    report: str = ""
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    requirement_parser: str = ""
    search_intent: dict[str, Any] = Field(default_factory=dict)
    clarification_questions: list[str] = Field(default_factory=list)
    search_plan: dict[str, Any] = Field(default_factory=dict)
    queries: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rate_limit: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    conversation_id: str = ""
    turn: int = 1
    node_timings: dict[str, float] = Field(default_factory=dict)


def _response_payload(
    result: dict[str, Any], conversation_id: str = "", turn: int = 1
) -> dict[str, Any]:
    return SearchResponse.model_validate(
        {**result, "conversation_id": conversation_id, "turn": turn}
    ).model_dump()


def _conversation_input(request: SearchRequest) -> tuple[str, str, int]:
    return CONVERSATIONS.begin_turn(request.conversation_id, request.requirement)


def _remember_clarification(conversation_id: str, result: dict[str, Any]) -> None:
    questions = result.get("clarification_questions", [])
    CONVERSATIONS.record_clarification(
        conversation_id, str(questions[0]) if questions else None
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    client = GitHubClient(
        max_concurrency=int(os.getenv("GITHUB_MAX_CONCURRENCY", "4")),
        max_attempts=int(os.getenv("GITHUB_MAX_ATTEMPTS", "3")),
    )
    set_github_client(client)
    try:
        yield
    finally:
        set_github_client(None)
        await client.close()


app = FastAPI(title="RepoScoutAgent", version="0.2.0", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "graph": "reposcout-agent-mvp"}


@app.post("/api/search")
async def search(request: SearchRequest) -> JSONResponse:
    conversation_id, raw_requirement, turn = _conversation_input(request)
    result = await GRAPH.ainvoke({"raw_requirement": raw_requirement})
    _remember_clarification(conversation_id, result)
    payload = _response_payload(result, conversation_id, turn)
    status = 400 if result.get("error") and not result.get("query") else 200
    return JSONResponse(content=payload, status_code=status)


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@app.post("/api/search/stream")
async def search_stream(request: SearchRequest) -> StreamingResponse:
    conversation_id, raw_requirement, turn = _conversation_input(request)

    async def events() -> AsyncIterator[str]:
        state: dict[str, Any] = {"raw_requirement": raw_requirement}
        try:
            async for update in GRAPH.astream(state, stream_mode="updates"):
                for node, values in update.items():
                    if isinstance(values, dict):
                        state.update(values)
                    progress: dict[str, Any] = {"node": node}
                    timings = values.get("node_timings", {}) if isinstance(values, dict) else {}
                    if node in timings:
                        progress["duration_ms"] = timings[node]
                    if node == "rank_candidates":
                        progress["candidates"] = [
                            {
                                "full_name": item.get("full_name"),
                                "description": item.get("description"),
                                "score": item.get("repository_ranking", {}).get("score"),
                            }
                            for item in values.get("ranked_candidates", [])[:5]
                        ]
                    if node == "prepare_evidence":
                        progress["analysis_count"] = len(
                            values.get("analysis_candidates", [])
                        )
                    yield _sse("progress", progress)
            _remember_clarification(conversation_id, state)
            yield _sse("result", _response_payload(state, conversation_id, turn))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield _sse("error", {"error": f"任务执行失败：{type(exc).__name__}"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/conversations/{conversation_id}")
async def reset_conversation(conversation_id: str) -> dict[str, str]:
    CONVERSATIONS.reset(conversation_id)
    return {"status": "reset", "conversation_id": conversation_id}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False)
