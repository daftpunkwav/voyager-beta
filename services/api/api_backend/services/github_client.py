"""GitHub REST API 客户端（公开接口 + 可选 PAT）"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GithubClientError(Exception):
    """GitHub 客户端可映射到登记报错码的异常。"""

    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


async def _request(
    path: str,
    *,
    token: str | None = None,
    accept: str = "application/vnd.github+json",
) -> tuple[int, Any, dict[str, str]]:
    """返回 (status, body, headers)。"""
    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed")
        return 0, {"error": "httpx 未安装"}, {}

    headers = {
        "Accept": accept,
        "User-Agent": "Voyager/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{GITHUB_API}{path}", headers=headers)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:500]}
        # 小写 header key 方便读 Link
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status_code, data, hdrs


def _parse_next_link(link_header: str | None) -> str | None:
    """从 GitHub Link 头解析 rel=next 的 path（含 query）。"""
    if not link_header:
        return None
    # <https://api.github.com/user/starred?page=2>; rel="next"
    for part in link_header.split(","):
        if 'rel="next"' not in part and "rel=next" not in part:
            continue
        m = re.search(r"<([^>]+)>", part)
        if not m:
            continue
        url = m.group(1)
        if url.startswith(GITHUB_API):
            return url[len(GITHUB_API) :]
        # 已是 path
        if url.startswith("/"):
            return url
    return None


async def fetch_repo_info(owner: str, repo: str, token: str | None = None) -> dict:
    status, data, _ = await _request(f"/repos/{owner}/{repo}", token=token)
    if status != 200:
        return {
            "error": f"GitHub API {status}",
            "message": data.get("message") if isinstance(data, dict) else str(data),
        }
    return {
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "stars": data.get("stargazers_count", 0),
        "language": data.get("language"),
        "topics": data.get("topics") or [],
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "license": (data.get("license") or {}).get("spdx_id"),
        "homepage": data.get("homepage"),
        "default_branch": data.get("default_branch"),
        "html_url": data.get("html_url"),
        "updated_at": data.get("updated_at"),
    }


async def fetch_readme_text(
    owner: str, repo: str, token: str | None = None
) -> str | None:
    status, data, _ = await _request(f"/repos/{owner}/{repo}/readme", token=token)
    if status != 200 or not isinstance(data, dict):
        return None
    content = data.get("content")
    if not content:
        return None
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception:
        return None


async def search_repositories(
    query: str, token: str | None = None, per_page: int = 10
) -> list[dict]:
    if not query.strip():
        return []
    status, data, _ = await _request(
        f"/search/repositories?q={quote(query)}&per_page={per_page}&sort=stars",
        token=token,
    )
    if status != 200 or not isinstance(data, dict):
        return []
    items = []
    for r in data.get("items") or []:
        items.append(
            {
                "id": str(r.get("id")),
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "url": r.get("html_url"),
                "description": r.get("description"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count", 0),
                "owner": (r.get("owner") or {}).get("login"),
            }
        )
    return items


def _map_star_item(r: dict) -> dict:
    return {
        "id": str(r.get("id")),
        "name": r.get("name"),
        "full_name": r.get("full_name"),
        "url": r.get("html_url"),
        "description": r.get("description"),
        "language": r.get("language"),
        "stars": r.get("stargazers_count", 0),
        "owner": (r.get("owner") or {}).get("login"),
    }


async def list_user_stars(
    username: str,
    token: str | None = None,
    *,
    per_page: int = 100,
    max_pages: int = 30,
) -> list[dict]:
    """
    分页拉取用户全部公开 Stars。
    - 有 PAT 时优先 /user/starred（含私有 star，且限流更高）
    - 否则 /users/{username}/starred
    per_page 最大 100；max_pages 默认 30 → 最多约 3000 个。
    """
    per_page = max(1, min(per_page, 100))
    # 有 token 时用认证端点更稳
    if token:
        path = f"/user/starred?per_page={per_page}"
    else:
        path = f"/users/{quote(username)}/starred?per_page={per_page}"

    items: list[dict] = []
    page = 0
    while path and page < max_pages:
        page += 1
        status, data, headers = await _request(path, token=token)
        if status != 200 or not isinstance(data, list):
            if page == 1:
                logger.warning(
                    "list_user_stars failed status=%s body=%s",
                    status,
                    str(data)[:200],
                )
                msg = (
                    data.get("message")
                    if isinstance(data, dict)
                    else f"GitHub API {status}"
                )
                if status in (403, 429):
                    raise GithubClientError(
                        "GITHUB_API_RATE_LIMIT",
                        str(msg) or "GitHub API 限流",
                        status=502,
                    )
                if status in (401, 404):
                    raise GithubClientError(
                        "GITHUB_PAT_INVALID",
                        str(msg) or "GitHub 鉴权失败或用户不存在",
                        status=400,
                    )
                raise GithubClientError(
                    "GITHUB_STARS_FETCH_FAILED",
                    str(msg) or "Stars 拉取失败",
                    status=502,
                )
            break
        for r in data:
            items.append(_map_star_item(r))
        if len(data) < per_page:
            break
        next_path = _parse_next_link(headers.get("link"))
        if next_path:
            path = next_path
        else:
            # 无 Link 时按 page 递增兜底
            if token:
                path = f"/user/starred?per_page={per_page}&page={page + 1}"
            else:
                path = f"/users/{quote(username)}/starred?per_page={per_page}&page={page + 1}"
            # 若本页已空则上面已 break；若 GitHub 不给 Link 但还有数据，继续
            # 若下一页重复，由调用方去重
    # 按 full_name 去重保序
    seen: set[str] = set()
    unique: list[dict] = []
    for it in items:
        key = it.get("full_name") or f"{it.get('owner')}/{it.get('name')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    return unique


async def list_trending_approx(language: str = "", limit: int = 10) -> list[dict]:
    """用 search 近似 trending。"""
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    q = f"created:>{since}"
    if language:
        q += f" language:{language}"
    status, data, _ = await _request(
        f"/search/repositories?q={quote(q)}&sort=stars&order=desc&per_page={limit}"
    )
    if status != 200 or not isinstance(data, dict):
        status, data, _ = await _request(
            f"/search/repositories?q={quote('stars:>10000')}&sort=stars&order=desc&per_page={limit}"
        )
    if status != 200 or not isinstance(data, dict):
        return []
    out = []
    for r in data.get("items") or []:
        out.append(
            {
                "id": str(r.get("id")),
                "name": r.get("full_name") or r.get("name"),
                "url": r.get("html_url"),
                "description": r.get("description"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "period": "weekly",
            }
        )
    return out
