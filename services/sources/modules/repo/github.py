"""GitHub API 客户端(修订自旧 github_client.py):元数据 / README / 搜索 / stars。

修订点:统一 `_request` 出口(便于测试 mock 与限流),token 由调用方
经 secrets 传入,客户端本身不碰密钥存储;克隆不在此(在 worker)。
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
from platform_contracts import ErrorSuffix, ServiceError

_API = "https://api.github.com"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


def parse_repo_url(url: str) -> tuple[str, str]:
    """从 https://github.com/owner/repo(.git|/tree/...) 解析 (owner, repo)。"""
    text = url.strip().removesuffix(".git").rstrip("/")
    if "github.com" not in text:
        raise ServiceError(
            "sources", ErrorSuffix.INVALID_INPUT,
            f"仅支持 GitHub 仓库地址: {url}", hint="形如 https://github.com/owner/repo",
        )
    parts = text.split("github.com/", 1)[1].split("/")
    if len(parts) < 2 or not all(parts[:2]):
        raise ServiceError("sources", ErrorSuffix.INVALID_INPUT, f"无法解析仓库地址: {url}")
    return parts[0], parts[1]


async def _request(path: str, token: str | None = None,
                   params: dict[str, Any] | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(f"{_API}{path}", headers=headers, params=params)
    if resp.status_code == 404:
        raise ServiceError("sources", ErrorSuffix.NOT_FOUND, f"GitHub 资源不存在: {path}")
    if resp.status_code == 403:
        raise ServiceError(
            "sources", ErrorSuffix.RATE_LIMITED, "GitHub API 限流或未授权",
            hint="可在设置页配置 GitHub token 提高限额",
        )
    resp.raise_for_status()
    return resp.json()


async def fetch_repo_info(owner: str, repo: str, token: str | None = None) -> dict[str, Any]:
    data = await _request(f"/repos/{owner}/{repo}", token)
    return {
        "owner": owner,
        "name": data.get("name", repo),
        "url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
        "description": data.get("description") or "",
        "stars": int(data.get("stargazers_count") or 0),
        "language": data.get("language") or "",
    }


async def fetch_readme(owner: str, repo: str, token: str | None = None) -> str:
    try:
        data = await _request(f"/repos/{owner}/{repo}/readme", token)
    except ServiceError as exc:
        if exc.body.code.endswith("NOT_FOUND"):
            return ""
        raise
    content = data.get("content") or ""
    if data.get("encoding") == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return content


async def search_repos(query: str, token: str | None = None,
                       limit: int = 10) -> list[dict[str, Any]]:
    data = await _request("/search/repositories", token,
                          params={"q": query, "per_page": min(limit, 30)})
    return [
        {
            "owner": (r.get("owner") or {}).get("login", ""),
            "name": r.get("name", ""),
            "url": r.get("html_url", ""),
            "description": r.get("description") or "",
            "stars": int(r.get("stargazers_count") or 0),
            "language": r.get("language") or "",
        }
        for r in data.get("items", [])
    ]


async def list_starred(username: str, token: str | None = None,
                       limit: int = 100) -> list[dict[str, Any]]:
    data = await _request(f"/users/{username}/stars", token,
                          params={"per_page": min(limit, 100)})
    return [
        {
            "owner": (r.get("owner") or {}).get("login", ""),
            "name": r.get("name", ""),
            "url": r.get("html_url", ""),
            "description": r.get("description") or "",
            "stars": int(r.get("stargazers_count") or 0),
            "language": r.get("language") or "",
        }
        for r in data
    ]
