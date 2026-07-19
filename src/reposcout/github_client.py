from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()

GITHUB_TOKEN_ENV = "GITHUB_TOKEN"


class GitHubSearchError(RuntimeError):
    pass


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
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 30),
    }
    try:
        with httpx.Client(headers=_build_github_headers(), timeout=15.0) as client:
            response = client.get("https://api.github.com/search/repositories", params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise _handle_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _handle_request_error(exc) from exc

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
            "updated_at": item.get("updated_at", ""),
            "pushed_at": item.get("pushed_at") or item.get("updated_at", ""),
        }
        for item in payload.get("items", [])
    ]


def get_rate_limit() -> dict[str, Any]:
    try:
        with httpx.Client(headers=_build_github_headers(), timeout=10.0) as client:
            response = client.get("https://api.github.com/rate_limit")
            response.raise_for_status()
            payload = response.json()
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
