from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubSearchError(RuntimeError):
    pass


def search_repositories(query: str, limit: int = 15) -> list[dict[str, Any]]:
    params = urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": min(limit, 30)}
    )
    request = Request(
        f"https://api.github.com/search/repositories?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "RepoScout-MVP",
            **(
                {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
                if os.getenv("GITHUB_TOKEN")
                else {}
            ),
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise GitHubSearchError("GitHub API 请求受限，请稍后重试或配置 GITHUB_TOKEN。") from exc
        raise GitHubSearchError(f"GitHub API 返回错误：HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise GitHubSearchError("暂时无法连接 GitHub，请检查网络后重试。") from exc

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
        }
        for item in payload.get("items", [])
    ]
