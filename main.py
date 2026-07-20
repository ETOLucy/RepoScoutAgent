from __future__ import annotations

import argparse
import asyncio
import json
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
from src.reposcout.github_client import (
    GitHubClient,
    GitHubSearchError,
    get_github_client,
    set_github_client,
)
from src.reposcout.nodes import inspect_repository_code, set_requirement_timeout
from src.reposcout.research import ResearchStore
from src.reposcout.web_search import (
    SearXNGSearchProvider,
    set_web_search_client,
)

load_dotenv()

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
DATABASE_PATH = ROOT / ".cache" / "research_tasks.db"
GRAPH = build_graph()
CONVERSATIONS = ConversationStore(DATABASE_PATH)
RESEARCH = ResearchStore(DATABASE_PATH)


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    github_max_concurrency: int = 4
    github_max_attempts: int = 3
    web_search_max_queries: int = 2
    web_search_results: int = 8
    web_search_timeout: float = 4.0
    requirement_timeout: float = 60.0
    searxng_url: str | None = None


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
        default=60.0,
        help="LLM requirement parsing time budget in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--searxng-url",
        help="SearXNG base URL; enables the preferred free web search provider",
    )
    return parser


def parse_config(args: list[str] | None = None) -> ServerConfig:
    namespace = create_parser().parse_args(args)
    return ServerConfig(**vars(namespace))


class SearchRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=80)
    context_mode: Literal["auto", "new", "refine"] = "auto"
    deep_code_search: bool = False
    allow_requirement_fallback: bool = False
    interactive: bool = False


class ResumeRequest(BaseModel):
    action: Literal["confirm", "edit", "skip"]
    feedback: str = Field(default="", max_length=4000)


class DeepCodeSearchRequest(BaseModel):
    repository: str = Field(
        min_length=3,
        max_length=200,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    requirement: str = Field(default="", max_length=4000)


class SearchResponse(BaseModel):
    requirement: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    executed_queries: list[str] = Field(default_factory=list)
    report: str = ""
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    component_candidates: list[dict[str, Any]] = Field(default_factory=list)
    solutions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: dict[str, Any] = Field(default_factory=dict)
    code_understanding: list[dict[str, Any]] = Field(default_factory=list)
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
    interaction: dict[str, Any] = Field(default_factory=dict)
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


async def _persist_result(
    result: dict[str, Any],
    conversation_id: str,
    query: str,
    turn: int,
    research_id: str | None = None,
) -> dict[str, Any]:
    payload = _response_payload(result, conversation_id, turn)
    pending = result.get("interaction", {}).get("status") == "pending"
    if pending:
        checkpoint_state = {**result, "conversation_id": conversation_id}
        if research_id:
            payload = await asyncio.to_thread(
                RESEARCH.update_checkpoint, research_id, payload, checkpoint_state
            )
        else:
            payload = await asyncio.to_thread(
                RESEARCH.save_checkpoint,
                conversation_id,
                query,
                payload,
                checkpoint_state,
            )
    elif research_id:
        payload = await asyncio.to_thread(RESEARCH.complete, research_id, payload)
    elif payload.get("query") and not (
        payload.get("error") and not payload.get("solutions")
    ):
        payload = await asyncio.to_thread(
            RESEARCH.save, conversation_id, query, payload
        )
    content = str(payload.get("report") or payload.get("error") or "任务已更新")
    await asyncio.to_thread(
        CONVERSATIONS.record_assistant, conversation_id, content, payload
    )
    return payload


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    config: ServerConfig = _app.state.config
    set_requirement_timeout(config.requirement_timeout)
    client = GitHubClient(
        max_concurrency=config.github_max_concurrency,
        max_attempts=config.github_max_attempts,
    )
    set_github_client(client)
    web_client = (
        SearXNGSearchProvider(
            config.searxng_url,
            timeout_seconds=config.web_search_timeout,
            max_queries=config.web_search_max_queries,
            results_per_query=config.web_search_results,
        )
        if config.searxng_url
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
    result = await GRAPH.ainvoke(
        {
            "raw_requirement": raw_requirement,
            "deep_code_search": request.deep_code_search,
            "allow_requirement_fallback": request.allow_requirement_fallback,
            "conversation_id": conversation_id,
            "interactive": request.interactive,
            "requirement_reviewed": False,
        }
    )
    _remember_clarification(conversation_id, result)
    payload = await _persist_result(
        result, conversation_id, request.requirement, turn
    )
    status = 400 if result.get("error") and not result.get("query") else 200
    return JSONResponse(content=payload, status_code=status)


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@app.post("/api/search/stream")
async def search_stream(request: SearchRequest) -> StreamingResponse:
    conversation_id, raw_requirement, turn = _conversation_input(request)

    async def events() -> AsyncIterator[str]:
        state: dict[str, Any] = {
            "raw_requirement": raw_requirement,
            "deep_code_search": request.deep_code_search,
            "allow_requirement_fallback": request.allow_requirement_fallback,
            "conversation_id": conversation_id,
            "interactive": request.interactive,
            "requirement_reviewed": False,
        }
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
            payload = await _persist_result(
                state, conversation_id, request.requirement, turn
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
    await asyncio.to_thread(CONVERSATIONS.reset, conversation_id)
    return {"status": "reset", "conversation_id": conversation_id}


@app.get("/api/conversations")
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(CONVERSATIONS.list, limit)


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, Any]:
    result = await asyncio.to_thread(CONVERSATIONS.get, conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return result


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


@app.post("/api/research/{research_id}/resume")
async def resume_research(
    research_id: str, request: ResumeRequest
) -> JSONResponse:
    saved_state = await asyncio.to_thread(RESEARCH.resume_state, research_id)
    if saved_state is None:
        raise HTTPException(
            status_code=409, detail="research task is not waiting for input"
        )
    conversation_id = str(saved_state.get("conversation_id", ""))
    if not conversation_id:
        raise HTTPException(status_code=409, detail="checkpoint has no conversation")

    if request.action == "edit":
        feedback = request.feedback.strip()
        if not feedback:
            raise HTTPException(status_code=422, detail="feedback is required for edit")
        _, raw_requirement, turn = await asyncio.to_thread(
            CONVERSATIONS.begin_turn, conversation_id, feedback, "refine"
        )
        state: dict[str, Any] = {
            "raw_requirement": raw_requirement,
            "conversation_id": conversation_id,
            "interactive": True,
            "requirement_reviewed": False,
            "deep_code_search": bool(saved_state.get("deep_code_search")),
            "allow_requirement_fallback": bool(
                saved_state.get("allow_requirement_fallback")
            ),
        }
        query = feedback
    else:
        label = "确认需求并继续" if request.action == "confirm" else "跳过确认并继续"
        await asyncio.to_thread(
            CONVERSATIONS.record_user_event, conversation_id, label
        )
        conversation = await asyncio.to_thread(CONVERSATIONS.get, conversation_id)
        turn = int(conversation["turn_count"]) if conversation else 1
        state = {
            **saved_state,
            "report": "",
            "error": "",
            "interaction": {},
            "requirement_reviewed": True,
            "interactive": request.action != "skip",
        }
        query = str(saved_state.get("raw_requirement", ""))

    result = await GRAPH.ainvoke(state)
    _remember_clarification(conversation_id, result)
    payload = await _persist_result(
        result, conversation_id, query, turn, research_id
    )
    status = 400 if result.get("error") and not result.get("query") else 200
    return JSONResponse(content=payload, status_code=status)


@app.post("/api/tools/deep-code-search")
async def deep_code_search_tool(request: DeepCodeSearchRequest) -> dict[str, Any]:
    try:
        repository = await get_github_client().get_repository(request.repository)
        return await inspect_repository_code(repository, request.requirement)
    except GitHubSearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    config = parse_config()
    app.state.config = config
    uvicorn.run(app, host=config.host, port=config.port, reload=False)
