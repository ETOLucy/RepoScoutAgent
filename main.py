from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.reposcout import build_graph
from src.reposcout.conversations import ConversationStore
from src.reposcout.github_client import GitHubClient, set_github_client
from src.reposcout.nodes import set_requirement_timeout
from src.reposcout.research import ResearchStore
from src.reposcout.web_search import BraveWebSearchClient, set_web_search_client

load_dotenv()

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
GRAPH = build_graph()
CONVERSATIONS = ConversationStore()
RESEARCH = ResearchStore(ROOT / ".cache" / "research_tasks.db")


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    github_max_concurrency: int = 4
    github_max_attempts: int = 3
    web_search_max_queries: int = 2
    web_search_results: int = 8
    web_search_timeout: float = 4.0
    requirement_timeout: float = 15.0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _port(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the RepoScoutAgent web service."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to bind (default: %(default)s)",
    )
    parser.add_argument(
        "--port", type=_port, default=8000, help="port to bind (default: %(default)s)"
    )
    parser.add_argument(
        "--github-max-concurrency",
        type=_positive_int,
        default=4,
        help="maximum concurrent GitHub API requests (default: %(default)s)",
    )
    parser.add_argument(
        "--github-max-attempts",
        type=_positive_int,
        default=3,
        help="maximum attempts for a GitHub API request (default: %(default)s)",
    )
    parser.add_argument(
        "--web-search-max-queries",
        type=_positive_int,
        default=2,
        help="maximum parallel web discovery queries (default: %(default)s)",
    )
    parser.add_argument(
        "--web-search-results",
        type=_positive_int,
        default=8,
        help="results requested per web query (default: %(default)s)",
    )
    parser.add_argument(
        "--web-search-timeout",
        type=_positive_float,
        default=4.0,
        help="total web discovery time budget in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--requirement-timeout",
        type=_positive_float,
        default=15.0,
        help="LLM requirement parsing time budget in seconds (default: %(default)s)",
    )
    return parser


def parse_config(args: list[str] | None = None) -> ServerConfig:
    namespace = create_parser().parse_args(args)
    return ServerConfig(**vars(namespace))


class SearchRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=80)
    context_mode: Literal["auto", "new", "refine"] = "auto"


class SearchResponse(BaseModel):
    requirement: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    executed_queries: list[str] = Field(default_factory=list)
    report: str = ""
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    component_candidates: list[dict[str, Any]] = Field(default_factory=list)
    solutions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: dict[str, Any] = Field(default_factory=dict)
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
    research_id: str = ""
    created_at: str = ""


def _response_payload(
    result: dict[str, Any], conversation_id: str = "", turn: int = 1
) -> dict[str, Any]:
    return SearchResponse.model_validate(
        {**result, "conversation_id": conversation_id, "turn": turn}
    ).model_dump()


def _conversation_input(request: SearchRequest) -> tuple[str, str, int]:
    return CONVERSATIONS.begin_turn(
        request.conversation_id, request.requirement, request.context_mode
    )


def _remember_clarification(conversation_id: str, result: dict[str, Any]) -> None:
    questions = result.get("clarification_questions", [])
    CONVERSATIONS.record_clarification(
        conversation_id, str(questions[0]) if questions else None
    )


async def _save_research(
    payload: dict[str, Any], conversation_id: str, query: str
) -> dict[str, Any]:
    if not payload.get("query") or (
        payload.get("error") and not payload.get("solutions")
    ):
        return payload
    return await asyncio.to_thread(RESEARCH.save, conversation_id, query, payload)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    config: ServerConfig = _app.state.config
    set_requirement_timeout(config.requirement_timeout)
    client = GitHubClient(
        max_concurrency=config.github_max_concurrency,
        max_attempts=config.github_max_attempts,
    )
    set_github_client(client)
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
    web_client = (
        BraveWebSearchClient(
            brave_key,
            timeout_seconds=config.web_search_timeout,
            max_queries=config.web_search_max_queries,
            results_per_query=config.web_search_results,
        )
        if brave_key
        else None
    )
    set_web_search_client(web_client)
    try:
        yield
    finally:
        set_web_search_client(None)
        if web_client:
            await web_client.close()
        set_github_client(None)
        await client.close()


app = FastAPI(title="RepoScout", version="0.3.0", lifespan=lifespan)
app.state.config = ServerConfig()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "graph": "reposcout-research"}


@app.post("/api/search")
async def search(request: SearchRequest) -> JSONResponse:
    conversation_id, raw_requirement, turn = _conversation_input(request)
    result = await GRAPH.ainvoke({"raw_requirement": raw_requirement})
    _remember_clarification(conversation_id, result)
    payload = _response_payload(result, conversation_id, turn)
    payload = await _save_research(payload, conversation_id, request.requirement)
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
            payload = _response_payload(state, conversation_id, turn)
            payload = await _save_research(
                payload, conversation_id, request.requirement
            )
            yield _sse("result", payload)
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


@app.get("/api/research")
async def list_research(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(RESEARCH.list, limit)


@app.get("/api/research/{research_id}")
async def get_research(research_id: str) -> dict[str, Any]:
    result = await asyncio.to_thread(RESEARCH.get, research_id)
    if result is None:
        raise HTTPException(status_code=404, detail="research task not found")
    return result


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    config = parse_config()
    app.state.config = config
    uvicorn.run(app, host=config.host, port=config.port, reload=False)
