from __future__ import annotations

import asyncio
import base64
import binascii
import os
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN_ENV = "GITHUB_TOKEN"


class GitHubSearchError(RuntimeError):
    pass


def _decode_json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubSearchError("GitHub API 返回了无法解析的 JSON。") from exc
    if not isinstance(payload, dict):
        raise GitHubSearchError("GitHub API 返回了不符合预期的数据结构。")
    return payload


def _build_github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RepoScoutAgent-MVP",
    }
    token = os.getenv(GITHUB_TOKEN_ENV)
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _status_error(status: int) -> GitHubSearchError:
    if status in (403, 429):
        return GitHubSearchError("GitHub API 请求受限，请稍后重试或配置 GITHUB_TOKEN。")
    return GitHubSearchError(f"GitHub API 返回错误：HTTP {status}")


def _is_repository_document(path: str) -> bool:
    normalized = path.lower()
    name = PurePosixPath(normalized).name
    return (name.startswith("readme") and name.endswith((".md", ".rst", ".txt"))) or (
        normalized.startswith(("docs/", "doc/", "documentation/"))
        and normalized.endswith((".md", ".rst", ".txt"))
    )


class GitHubClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        max_concurrency: int = 4,
        max_attempts: int = 3,
        backoff_seconds: float = 0.25,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            headers=_build_github_headers(),
            timeout=httpx.Timeout(15.0),
            follow_redirects=False,
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> httpx.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with self._semaphore:
                    response = await self._client.get(url, params=params)
                if response.status_code in (403, 429):
                    raise _status_error(response.status_code)
                if response.status_code >= 500 and attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_seconds * 2 ** (attempt - 1))
                    continue
                response.raise_for_status()
                return response
            except GitHubSearchError:
                raise
            except httpx.HTTPStatusError as exc:
                raise _status_error(exc.response.status_code) from exc
            except httpx.RequestError as exc:
                if attempt == self._max_attempts:
                    raise GitHubSearchError("暂时无法连接 GitHub，请检查网络后重试。") from exc
                await asyncio.sleep(self._backoff_seconds * 2 ** (attempt - 1))
        raise GitHubSearchError("GitHub 请求在有限重试后失败。")

    async def search_repositories(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        response = await self._request(
            "https://api.github.com/search/repositories",
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(limit, 30),
            },
        )
        payload = _decode_json_response(response)
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise GitHubSearchError("GitHub 搜索结果缺少有效的 items 列表。")
        try:
            return [
                {
                    "full_name": item["full_name"],
                    "url": item["html_url"],
                    "description": item.get("description") or "暂无项目描述",
                    "language": item.get("language"),
                    "stars": item.get("stargazers_count", 0),
                    "forks": item.get("forks_count", 0),
                    "open_issues": item.get("open_issues_count", 0),
                    "license": (item.get("license") or {}).get("spdx_id") or "Unknown",
                    "topics": item.get("topics") or [],
                    "archived": item.get("archived", False),
                    "disabled": item.get("disabled", False),
                    "fork": item.get("fork", False),
                    "size": item.get("size"),
                    "default_branch": item.get("default_branch"),
                    "updated_at": item.get("updated_at", ""),
                    "pushed_at": item.get("pushed_at") or item.get("updated_at", ""),
                }
                for item in items
            ]
        except (AttributeError, KeyError, TypeError) as exc:
            raise GitHubSearchError("GitHub 搜索结果中的仓库数据不完整。") from exc

    async def fetch_repository_documents(
        self,
        full_name: str,
        default_branch: str,
        max_documents: int = 6,
        max_total_chars: int = 240_000,
    ) -> list[dict[str, str]]:
        repository = quote(full_name, safe="/")
        branch = quote(default_branch, safe="")
        tree_response = await self._request(
            f"https://api.github.com/repos/{repository}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        tree = _decode_json_response(tree_response).get("tree", [])
        if not isinstance(tree, list):
            raise GitHubSearchError("仓库文件树数据结构无效。")
        paths = [
            str(item.get("path"))
            for item in tree
            if isinstance(item, dict)
            and item.get("type") == "blob"
            and _is_repository_document(str(item.get("path", "")))
        ]
        paths.sort(
            key=lambda path: (
                not PurePosixPath(path).name.lower().startswith("readme"),
                path,
            )
        )

        async def fetch(path: str) -> tuple[str, str] | None:
            response = await self._request(
                f"https://api.github.com/repos/{repository}/contents/{quote(path, safe='/')}",
                params={"ref": default_branch},
            )
            payload = _decode_json_response(response)
            encoded = payload.get("content")
            if not isinstance(encoded, str) or payload.get("encoding") != "base64":
                return None
            try:
                content = base64.b64decode(encoded).decode("utf-8", errors="replace")[:80_000]
            except (binascii.Error, ValueError) as exc:
                raise GitHubSearchError("仓库文档内容无法解析。") from exc
            return path, content

        fetched = await asyncio.gather(*(fetch(path) for path in paths[:max_documents]))
        documents: list[dict[str, str]] = []
        remaining = max_total_chars
        for item in fetched:
            if item is None or remaining <= 0:
                continue
            path, content = item
            content = content[:remaining]
            if not content:
                continue
            documents.append(
                {
                    "path": path,
                    "url": f"https://github.com/{full_name}/blob/{default_branch}/{path}",
                    "content": content,
                }
            )
            remaining -= len(content)
        return documents

    async def get_rate_limit(self) -> dict[str, Any]:
        payload = _decode_json_response(
            await self._request("https://api.github.com/rate_limit")
        )
        resources = payload.get("resources", {})
        core = resources.get("core", {})
        search = resources.get("search", {})
        return {
            "core": {key: core.get(key) for key in ("limit", "remaining", "used", "reset")},
            "search": {
                key: search.get(key) for key in ("limit", "remaining", "used", "reset")
            },
        }


_shared_client: GitHubClient | None = None


def get_github_client() -> GitHubClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = GitHubClient()
    return _shared_client


def set_github_client(client: GitHubClient | None) -> None:
    global _shared_client
    _shared_client = client
