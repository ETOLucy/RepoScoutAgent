from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx


class WebSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebRepositoryHit:
    full_name: str
    title: str
    url: str
    description: str
    query: str
    providers: tuple[str, ...] = ()


class WebSearchProvider(Protocol):
    async def search_repositories(
        self, queries: list[str]
    ) -> list[WebRepositoryHit]: ...

    async def close(self) -> None: ...


def github_repository_name(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.hostname not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] in {"search", "topics", "marketplace"}:
        return None
    owner, repository = parts[:2]
    repository = re.sub(r"\.git$", "", repository, flags=re.I)
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", item) for item in (owner, repository)):
        return None
    return f"{owner}/{repository}"


class BraveWebSearchClient:
    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 4.0,
        max_queries: int = 2,
        results_per_query: int = 8,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._timeout_seconds = timeout_seconds
        self._max_queries = max_queries
        self._results_per_query = results_per_query

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _search(self, query: str) -> list[WebRepositoryHit]:
        response = await self._client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={
                "q": f"{query} site:github.com",
                "count": self._results_per_query,
                "search_lang": "en",
                "safesearch": "moderate",
            },
        )
        if response.status_code >= 400:
            raise WebSearchError(f"Brave Search returned HTTP {response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise WebSearchError("Brave Search returned invalid JSON") from exc
        raw_results = payload.get("web", {}).get("results", []) if isinstance(payload, dict) else []
        hits = []
        for item in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", ""))
            full_name = github_repository_name(url)
            if full_name:
                hits.append(
                    WebRepositoryHit(
                        full_name=full_name,
                        title=str(item.get("title", "")),
                        url=url,
                        description=str(item.get("description", "")),
                        query=query,
                        providers=("brave",),
                    )
                )
        return hits

    async def search_repositories(self, queries: list[str]) -> list[WebRepositoryHit]:
        selected = list(dict.fromkeys(queries))[: self._max_queries]
        try:
            async with asyncio.timeout(self._timeout_seconds):
                outcomes = await asyncio.gather(
                    *(self._search(query) for query in selected), return_exceptions=True
                )
        except TimeoutError as exc:
            raise WebSearchError("web search exceeded its time budget") from exc
        if outcomes and all(isinstance(item, Exception) for item in outcomes):
            raise WebSearchError("all web search queries failed")
        unique: dict[str, WebRepositoryHit] = {}
        for outcome in outcomes:
            if isinstance(outcome, list):
                for hit in outcome:
                    unique.setdefault(hit.full_name.casefold(), hit)
        return list(unique.values())


class SearXNGSearchProvider:
    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 4.0,
        max_queries: int = 2,
        results_per_query: int = 8,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("SearXNG URL must be an absolute HTTP(S) URL")
        normalized = base_url.rstrip("/")
        self._search_url = (
            normalized if normalized.endswith("/search") else f"{normalized}/search"
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
        self._timeout_seconds = timeout_seconds
        self._max_queries = max_queries
        self._results_per_query = results_per_query

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _search(self, query: str) -> list[WebRepositoryHit]:
        response = await self._client.get(
            self._search_url,
            params={
                "q": f"{query} site:github.com",
                "format": "json",
                "language": "en",
                "safesearch": 1,
            },
        )
        if response.status_code >= 400:
            raise WebSearchError(f"SearXNG returned HTTP {response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise WebSearchError("SearXNG returned invalid JSON") from exc
        raw_results = payload.get("results", []) if isinstance(payload, dict) else []
        hits = []
        for item in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", ""))
            full_name = github_repository_name(url)
            if full_name:
                hits.append(
                    WebRepositoryHit(
                        full_name=full_name,
                        title=str(item.get("title", "")),
                        url=url,
                        description=str(item.get("content", "")),
                        query=query,
                        providers=("searxng",),
                    )
                )
        return hits

    async def search_repositories(self, queries: list[str]) -> list[WebRepositoryHit]:
        selected = list(dict.fromkeys(queries))[: self._max_queries]
        try:
            async with asyncio.timeout(self._timeout_seconds):
                outcomes = await asyncio.gather(
                    *(self._search(query) for query in selected), return_exceptions=True
                )
        except TimeoutError as exc:
            raise WebSearchError("SearXNG exceeded its time budget") from exc
        if outcomes and all(isinstance(item, Exception) for item in outcomes):
            raise WebSearchError("all SearXNG queries failed")
        unique: dict[str, WebRepositoryHit] = {}
        for outcome in outcomes:
            if isinstance(outcome, list):
                for hit in outcome:
                    unique.setdefault(hit.full_name.casefold(), hit)
        return list(unique.values())


class CompositeWebSearchProvider:
    def __init__(self, providers: list[WebSearchProvider]) -> None:
        if not providers:
            raise ValueError("at least one web search provider is required")
        self._providers = providers

    async def close(self) -> None:
        await asyncio.gather(*(provider.close() for provider in self._providers))

    async def search_repositories(self, queries: list[str]) -> list[WebRepositoryHit]:
        outcomes = await asyncio.gather(
            *(provider.search_repositories(queries) for provider in self._providers),
            return_exceptions=True,
        )
        if all(isinstance(item, Exception) for item in outcomes):
            raise WebSearchError("all configured web search providers failed")
        unique: dict[str, WebRepositoryHit] = {}
        for outcome in outcomes:
            if not isinstance(outcome, list):
                continue
            for hit in outcome:
                key = hit.full_name.casefold()
                existing = unique.get(key)
                if existing is None:
                    unique[key] = hit
                    continue
                providers = tuple(dict.fromkeys((*existing.providers, *hit.providers)))
                unique[key] = replace(existing, providers=providers)
        return list(unique.values())


_shared_client: WebSearchProvider | None = None


def get_web_search_client() -> WebSearchProvider | None:
    return _shared_client


def set_web_search_client(client: WebSearchProvider | None) -> None:
    global _shared_client
    _shared_client = client
