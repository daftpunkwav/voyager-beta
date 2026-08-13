"""
GitHub API —— Star 导入、绑定账号、仓库搜索（读写 AppState）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.core.security import encrypt_secret
from api_backend.models.app_state import AppState
from api_backend.models.project import Project
from api_backend.schemas.common import DataResponse
from api_backend.services.app_state_service import get_or_create_app_state
from api_backend.services.github_accounts import (
    load_accounts as _load_accounts,
)
from api_backend.services.github_accounts import (
    migrate_plaintext_pats as _migrate_plaintext_pats,
)
from api_backend.services.github_accounts import (
    primary_token as _primary_token,
)
from api_backend.services.github_accounts import (
    save_accounts as _save_accounts,
)
from api_backend.services.github_client import list_user_stars, search_repositories
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/github", tags=["github"])

STARS_CACHE_TTL = timedelta(hours=6)


class BindGithubBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    pat: str = Field(..., min_length=4, max_length=256)


class GithubAccountOut(BaseModel):
    id: str
    username: str
    avatar_url: Optional[str] = None
    bound_at: str


class StarRepoOut(BaseModel):
    owner: str
    repo: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    already_imported: bool = False


class StarsListOut(BaseModel):
    items: list[StarRepoOut]
    total: int
    cached: bool = False
    fetched_at: Optional[str] = None
    cache_ttl_hours: float = 6.0


def _load_settings(state: AppState) -> dict:
    try:
        data = json.loads(state.settings_json or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_settings(state: AppState, data: dict) -> None:
    state.settings_json = json.dumps(data, ensure_ascii=False)


def _stars_from_cache(
    state: AppState, username: str
) -> tuple[list[dict], str | None] | None:
    raw = _load_settings(state)
    cache = raw.get("github_stars_cache")
    if not isinstance(cache, dict):
        return None
    if (cache.get("username") or "").lower() != username.lower():
        return None
    fetched_at = cache.get("fetched_at")
    items = cache.get("items")
    if not fetched_at or not isinstance(items, list):
        return None
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return None
    if datetime.utcnow() - ts > STARS_CACHE_TTL:
        return None
    return items, fetched_at


def _write_stars_cache(state: AppState, username: str, items: list[dict]) -> str:
    raw = _load_settings(state)
    fetched_at = datetime.utcnow().isoformat() + "Z"
    slim = []
    for it in items:
        slim.append(
            {
                "owner": it.get("owner"),
                "name": it.get("name"),
                "full_name": it.get("full_name"),
                "url": it.get("url"),
                "description": (it.get("description") or "")[:300] or None,
                "language": it.get("language"),
                "stars": it.get("stars") or 0,
            }
        )
    raw["github_stars_cache"] = {
        "username": username,
        "fetched_at": fetched_at,
        "items": slim,
    }
    _save_settings(state, raw)
    return fetched_at


def _to_star_out(s: dict, existing_urls: set[str]) -> StarRepoOut:
    full = s.get("full_name") or ""
    if "/" in full:
        owner, repo = full.split("/", 1)
    else:
        owner, repo = s.get("owner") or "", s.get("name") or s.get("repo") or ""
    url = s.get("url") or f"https://github.com/{owner}/{repo}"
    return StarRepoOut(
        owner=owner,
        repo=repo,
        url=url,
        description=s.get("description"),
        language=s.get("language"),
        stars=int(s.get("stars") or 0),
        already_imported=url in existing_urls or s.get("already_imported") is True,
    )


@router.get("/accounts", response_model=DataResponse[list[GithubAccountOut]])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    state = await get_or_create_app_state(db)
    if _migrate_plaintext_pats(state):
        await db.commit()
    accounts = _load_accounts(state)
    out = []
    for a in accounts:
        out.append(
            GithubAccountOut(
                id=str(a.get("id") or a.get("username")),
                username=a.get("username") or "",
                avatar_url=a.get("avatar_url"),
                bound_at=a.get("bound_at") or "",
            )
        )
    return wrap_data(out)


@router.get("/stars", response_model=DataResponse[StarsListOut])
async def get_stars(
    username: str | None = Query(None),
    refresh: bool = Query(False, description="强制刷新，忽略缓存"),
    db: AsyncSession = Depends(get_db),
):
    """拉取全部 Stars；默认 6 小时缓存。"""
    state = await get_or_create_app_state(db)
    bound_user, token = _primary_token(state)
    uname = username or bound_user
    if not uname:
        await db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "GITHUB_NOT_BOUND",
                "message": "请先绑定 GitHub 账号或传入 username",
            },
        )

    existing = (await db.execute(select(Project.url))).scalars().all()
    existing_set = set(existing)

    cached = False
    fetched_at: str | None = None
    raw_items: list[dict] = []

    if not refresh:
        hit = _stars_from_cache(state, uname)
        if hit:
            raw_items, fetched_at = hit
            cached = True

    if not cached:
        from api_backend.services.github_client import GithubClientError

        try:
            raw_items = await list_user_stars(
                uname, token=token, per_page=100, max_pages=30
            )
        except GithubClientError as exc:
            await db.commit()
            raise HTTPException(
                exc.status,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        fetched_at = _write_stars_cache(state, uname, raw_items)
        await db.commit()
    else:
        await db.commit()

    items = [_to_star_out(s, existing_set) for s in raw_items]
    return wrap_data(
        StarsListOut(
            items=items,
            total=len(items),
            cached=cached,
            fetched_at=fetched_at,
            cache_ttl_hours=STARS_CACHE_TTL.total_seconds() / 3600,
        )
    )


@router.post("/bindaccount", response_model=DataResponse[GithubAccountOut])
async def bind_account(
    body: BindGithubBody,
    db: AsyncSession = Depends(get_db),
):
    from api_backend.services.github_client import _request

    state = await get_or_create_app_state(db)
    status_code, data, _ = await _request("/user", token=body.pat)
    if status_code != 200:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "GITHUB_PAT_INVALID",
                "message": "GitHub PAT 无效或权限不足",
            },
        )
    login = (data.get("login") if isinstance(data, dict) else None) or body.username
    avatar = data.get("avatar_url") if isinstance(data, dict) else None
    accounts = _load_accounts(state)
    accounts = [a for a in accounts if a.get("username") != login]
    entry = {
        "id": str(uuid4()),
        "username": login,
        "pat": encrypt_secret(body.pat),
        "avatar_url": avatar,
        "bound_at": datetime.utcnow().isoformat() + "Z",
    }
    accounts.insert(0, entry)
    _save_accounts(state, accounts)
    settings = _load_settings(state)
    settings.pop("github_stars_cache", None)
    _save_settings(state, settings)
    await db.commit()
    return wrap_data(
        GithubAccountOut(
            id=entry["id"],
            username=login,
            avatar_url=avatar,
            bound_at=entry["bound_at"],
        )
    )


@router.delete("/accounts/{account_id}", response_model=DataResponse[dict])
async def unbind_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
):
    state = await get_or_create_app_state(db)
    accounts = _load_accounts(state)
    new_accounts = [
        a
        for a in accounts
        if str(a.get("id")) != account_id and a.get("username") != account_id
    ]
    if len(new_accounts) == len(accounts):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "GITHUB_ACCOUNT_NOT_FOUND", "message": "GitHub 账号记录不存在"},
        )
    _save_accounts(state, new_accounts)
    settings = _load_settings(state)
    settings.pop("github_stars_cache", None)
    _save_settings(state, settings)
    await db.commit()
    return wrap_data({"success": True})


@router.get("/search", response_model=DataResponse[list[StarRepoOut]])
async def search_repos(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    state = await get_or_create_app_state(db)
    _, token = _primary_token(state)
    items = await search_repositories(q, token=token, per_page=30)
    existing = (await db.execute(select(Project.url))).scalars().all()
    existing_set = set(existing)
    out = []
    for s in items:
        full = s.get("full_name") or ""
        if "/" in full:
            owner, repo = full.split("/", 1)
        else:
            owner, repo = s.get("owner") or "", s.get("name") or ""
        url = s.get("url") or f"https://github.com/{owner}/{repo}"
        out.append(
            StarRepoOut(
                owner=owner,
                repo=repo,
                url=url,
                description=s.get("description"),
                language=s.get("language"),
                stars=int(s.get("stars") or 0),
                already_imported=url in existing_set,
            )
        )
    await db.commit()
    return wrap_data(out)
