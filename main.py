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
from src.reposcout.github_client import GitHubClient, set_github_client

load_dotenv()

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
GRAPH = build_graph()


class SearchRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=4000)


class SearchResponse(BaseModel):
    requirement: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
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


def _response_payload(result: dict[str, Any]) -> dict[str, Any]:
    return SearchResponse.model_validate(result).model_dump()


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
    result = await GRAPH.ainvoke({"raw_requirement": request.requirement.strip()})
    payload = _response_payload(result)
    status = 400 if result.get("error") and not result.get("query") else 200
    return JSONResponse(content=payload, status_code=status)


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@app.post("/api/search/stream")
async def search_stream(request: SearchRequest) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        state: dict[str, Any] = {"raw_requirement": request.requirement.strip()}
        try:
            async for update in GRAPH.astream(state, stream_mode="updates"):
                for node, values in update.items():
                    if isinstance(values, dict):
                        state.update(values)
                    yield _sse("progress", {"node": node})
            yield _sse("result", _response_payload(state))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield _sse("error", {"error": f"任务执行失败：{type(exc).__name__}"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False)
