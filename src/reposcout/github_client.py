from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from .documents import DocumentCache, chunk_documents, source_type_for_path
from .static_analysis import manifest_signals

load_dotenv()

GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

_MANIFEST_NAMES = {
    "cargo.toml",
    "go.mod",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}
_IMPLEMENTATION_SUFFIXES = (
    ".c",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".proto",
    ".rb",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
)
_EXCLUDED_PATH_PARTS = {
    ".git",
    "dist",
    "fixtures",
    "generated",
    "node_modules",
    "tests",
    "test",
    "vendor",
}


def _implementation_terms(values: list[str]) -> set[str]:
    return {
        token.casefold()
        for value in values
        for token in re.findall(r"[a-z][a-z0-9_-]{2,}", value, re.I)
    }


def _static_file_priority(path: str, terms: set[str]) -> tuple[int, int, str] | None:
    normalized = path.casefold()
    pure_path = PurePosixPath(normalized)
    if any(part in _EXCLUDED_PATH_PARTS for part in pure_path.parts):
        return None
    name = pure_path.name
    if name in _MANIFEST_NAMES or name.startswith("requirements") and name.endswith(".txt"):
        return (0, len(path), path)
    if not normalized.endswith(_IMPLEMENTATION_SUFFIXES):
        return None
    path_tokens = set(re.findall(r"[a-z][a-z0-9_-]{2,}", normalized, re.I))
    overlap = len(terms.intersection(path_tokens))
    structural = any(
        marker in normalized
        for marker in ("auth", "config", "route", "router", "schema", "service")
    )
    if not overlap and not structural:
        return None
    return (1 if overlap else 2, -overlap, path)


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
        document_cache_dir: Path | None = None,
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
        self._rate_limits: dict[str, dict[str, int | None]] = {}
        self._document_cache = DocumentCache(
            document_cache_dir or Path(".cache/repository_documents")
        )

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
                self._capture_rate_limit(response)
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

    def _capture_rate_limit(self, response: httpx.Response) -> None:
        resource = response.headers.get("X-RateLimit-Resource")
        if resource not in {"core", "search"}:
            return

        def header_int(name: str) -> int | None:
            raw = response.headers.get(name)
            try:
                return int(raw) if raw is not None else None
            except ValueError:
                return None

        self._rate_limits[resource] = {
            "limit": header_int("X-RateLimit-Limit"),
            "remaining": header_int("X-RateLimit-Remaining"),
            "used": header_int("X-RateLimit-Used"),
            "reset": header_int("X-RateLimit-Reset"),
        }

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
            return [self._map_repository(item) for item in items]
        except (AttributeError, KeyError, TypeError) as exc:
            raise GitHubSearchError("GitHub 搜索结果中的仓库数据不完整。") from exc

    @staticmethod
    def _map_repository(item: dict[str, Any]) -> dict[str, Any]:
        return {
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

    async def get_repository(self, full_name: str) -> dict[str, Any]:
        repository = quote(full_name, safe="/")
        payload = _decode_json_response(
            await self._request(f"https://api.github.com/repos/{repository}")
        )
        try:
            return self._map_repository(payload)
        except (AttributeError, KeyError, TypeError) as exc:
            raise GitHubSearchError("GitHub 仓库数据不完整。") from exc

    async def fetch_repository_documents(
        self,
        full_name: str,
        default_branch: str,
        max_documents: int = 6,
        max_total_chars: int = 240_000,
        implementation_terms: list[str] | None = None,
        max_implementation_files: int = 10,
    ) -> list[dict[str, str]]:
        repository = quote(full_name, safe="/")
        branch = quote(default_branch, safe="")
        tree_response = await self._request(
            f"https://api.github.com/repos/{repository}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        tree_payload = _decode_json_response(tree_response)
        tree = tree_payload.get("tree", [])
        if not isinstance(tree, list):
            raise GitHubSearchError("仓库文件树数据结构无效。")
        commit_sha = str(tree_payload.get("sha") or default_branch)
        terms = _implementation_terms(implementation_terms or [])
        term_fingerprint = hashlib.sha256(" ".join(sorted(terms)).encode()).hexdigest()[:12]
        cache_key = f"{commit_sha}-{term_fingerprint}"
        cached = self._document_cache.load(full_name, cache_key)
        if cached is not None:
            return cached
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
        static_paths = [
            (priority, str(item.get("path")))
            for item in tree
            if isinstance(item, dict)
            and item.get("type") == "blob"
            and (
                priority := _static_file_priority(str(item.get("path", "")), terms)
            )
            is not None
        ]
        static_paths.sort(key=lambda item: item[0])
        selected_static_paths = [
            path for _priority, path in static_paths[:max_implementation_files]
        ]

        async def fetch(path: str, source_type: str | None = None) -> dict[str, str] | None:
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
            document = {
                "path": path,
                "url": f"https://github.com/{full_name}/blob/{commit_sha}/{path}",
                "source_type": source_type or source_type_for_path(path),
                "content": content,
            }
            if document["source_type"] == "manifest":
                document["static_signals"] = ", ".join(manifest_signals(path, content))
            return document

        async def optional_list(
            endpoint: str, params: dict[str, str | int]
        ) -> list[dict[str, Any]]:
            try:
                response = await self._request(
                    f"https://api.github.com/repos/{repository}/{endpoint}", params=params
                )
                payload = response.json()
            except (GitHubSearchError, ValueError):
                return []
            if not isinstance(payload, list):
                return []
            return [item for item in payload if isinstance(item, dict)]

        async def fetch_activity_documents() -> list[dict[str, str]]:
            releases, issues, commits = await asyncio.gather(
                optional_list("releases", {"per_page": 3}),
                optional_list(
                    "issues",
                    {"state": "all", "sort": "comments", "direction": "desc", "per_page": 8},
                ),
                optional_list("commits", {"sha": default_branch, "per_page": 5}),
            )
            activity: list[dict[str, str]] = []
            if releases:
                sections = [
                    f"## {item.get('name') or item.get('tag_name') or 'Release'}\n"
                    f"Published: {item.get('published_at') or 'unknown'}\n\n"
                    f"{str(item.get('body') or '')[:20_000]}"
                    for item in releases
                ]
                activity.append(
                    {
                        "path": ".github-data/releases.md",
                        "url": f"https://github.com/{full_name}/releases",
                        "source_type": "release",
                        "content": "# Releases\n\n" + "\n\n".join(sections),
                    }
                )
            key_issues = [item for item in issues if "pull_request" not in item][:5]
            if key_issues:
                sections = [
                    f"## #{item.get('number')} {item.get('title') or 'Untitled'}\n"
                    f"State: {item.get('state')}; comments: {item.get('comments', 0)}; "
                    f"updated: {item.get('updated_at') or 'unknown'}\n\n"
                    f"{str(item.get('body') or '')[:12_000]}"
                    for item in key_issues
                ]
                activity.append(
                    {
                        "path": ".github-data/issues.md",
                        "url": f"https://github.com/{full_name}/issues",
                        "source_type": "issue",
                        "content": "# Key issues\n\n" + "\n\n".join(sections),
                    }
                )
            if commits:
                sections = []
                for item in commits:
                    raw_detail = item.get("commit")
                    detail: dict[str, Any] = raw_detail if isinstance(raw_detail, dict) else {}
                    raw_author = detail.get("author")
                    author: dict[str, Any] = raw_author if isinstance(raw_author, dict) else {}
                    message_lines = str(detail.get("message") or "").splitlines()
                    message = message_lines[0] if message_lines else "No commit message"
                    sections.append(
                        f"- `{str(item.get('sha') or '')[:12]}` "
                        f"{message} "
                        f"({author.get('date') or 'unknown'})"
                    )
                activity.append(
                    {
                        "path": ".github-data/commits.md",
                        "url": f"https://github.com/{full_name}/commits/{default_branch}",
                        "source_type": "commit",
                        "content": "# Recent commits\n\n" + "\n".join(sections),
                    }
                )
            return activity

        fetched, static_files, activity = await asyncio.gather(
            asyncio.gather(*(fetch(path) for path in paths[:max_documents])),
            asyncio.gather(
                *(
                    fetch(
                        path,
                        "manifest"
                        if PurePosixPath(path).name.casefold() in _MANIFEST_NAMES
                        or PurePosixPath(path).name.casefold().startswith("requirements")
                        else "implementation",
                    )
                    for path in selected_static_paths
                )
            ),
            fetch_activity_documents(),
        )
        documents = (
            [item for item in fetched if item is not None]
            + [item for item in static_files if item is not None]
            + activity
        )
        chunks = chunk_documents(
            documents,
            repository=full_name,
            commit_sha=commit_sha,
            max_total_chars=max_total_chars,
        )
        self._document_cache.save(full_name, cache_key, chunks, documents)
        return chunks

    async def get_rate_limit(self) -> dict[str, Any]:
        if self._rate_limits:
            return {
                resource: self._rate_limits.get(resource, {})
                for resource in ("core", "search")
            }
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
