from __future__ import annotations

import base64
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


def _handle_http_error(exc: httpx.HTTPStatusError) -> GitHubSearchError:
    status = exc.response.status_code
    if status in (403, 429):
        return GitHubSearchError("GitHub API 请求受限，请稍后重试或配置 GITHUB_TOKEN。")
    return GitHubSearchError(f"GitHub API 返回错误：HTTP {status}")


def _handle_request_error(exc: httpx.RequestError) -> GitHubSearchError:
    return GitHubSearchError("暂时无法连接 GitHub，请检查网络后重试。")


def search_repositories(query: str, limit: int = 15) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 30),
    }
    try:
        with httpx.Client(headers=_build_github_headers(), timeout=15.0) as client:
            response = client.get("https://api.github.com/search/repositories", params=params)
            response.raise_for_status()
            payload = _decode_json_response(response)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _handle_request_error(exc) from exc

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


def _is_repository_document(path: str) -> bool:
    normalized = path.lower()
    name = PurePosixPath(normalized).name
    return (name.startswith("readme") and name.endswith((".md", ".rst", ".txt"))) or (
        normalized.startswith(("docs/", "doc/", "documentation/"))
        and normalized.endswith((".md", ".rst", ".txt"))
    )


def fetch_repository_documents(
    full_name: str,
    default_branch: str,
    max_documents: int = 6,
    max_total_chars: int = 240_000,
) -> list[dict[str, str]]:
    repository = quote(full_name, safe="/")
    branch = quote(default_branch, safe="")
    tree_url = f"https://api.github.com/repos/{repository}/git/trees/{branch}"
    try:
        with httpx.Client(headers=_build_github_headers(), timeout=15.0) as client:
            tree_response = client.get(tree_url, params={"recursive": "1"})
            tree_response.raise_for_status()
            tree_payload = _decode_json_response(tree_response)
            tree = tree_payload.get("tree", [])
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

            documents: list[dict[str, str]] = []
            remaining = max_total_chars
            for path in paths[:max_documents]:
                content_url = (
                    f"https://api.github.com/repos/{repository}/contents/"
                    f"{quote(path, safe='/')}"
                )
                response = client.get(content_url, params={"ref": default_branch})
                response.raise_for_status()
                payload = _decode_json_response(response)
                encoded = payload.get("content")
                if not isinstance(encoded, str) or payload.get("encoding") != "base64":
                    continue
                content = base64.b64decode(encoded).decode("utf-8", errors="replace")[:80_000]
                content = content[:remaining]
                if not content:
                    break
                documents.append(
                    {
                        "path": path,
                        "url": f"https://github.com/{full_name}/blob/{default_branch}/{path}",
                        "content": content,
                    }
                )
                remaining -= len(content)
                if remaining <= 0:
                    break
            return documents
    except httpx.HTTPStatusError as exc:
        raise _handle_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _handle_request_error(exc) from exc
    except (ValueError, TypeError) as exc:
        raise GitHubSearchError("仓库文档内容无法解析。") from exc


def get_rate_limit() -> dict[str, Any]:
    try:
        with httpx.Client(headers=_build_github_headers(), timeout=10.0) as client:
            response = client.get("https://api.github.com/rate_limit")
            response.raise_for_status()
            payload = _decode_json_response(response)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _handle_request_error(exc) from exc

    resources = payload.get("resources", {})
    core = resources.get("core", {})
    search = resources.get("search", {})
    return {
        "core": {
            "limit": core.get("limit"),
            "remaining": core.get("remaining"),
            "used": core.get("used"),
            "reset": core.get("reset"),
        },
        "search": {
            "limit": search.get("limit"),
            "remaining": search.get("remaining"),
            "used": search.get("used"),
            "reset": search.get("reset"),
        },
    }
