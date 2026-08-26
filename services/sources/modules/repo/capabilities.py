"""repo 子模块能力(§8.2):导入 / 列表 / 排序 / README / 元数据 / 远程搜索。

导入是长任务(§7.3):登记 → 入队 clone → 完成发 source.ready(§8.2)。
GitHub token 走 platform/secrets,仅用户可写(与 llm key 同边界)。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, JobRef, ServiceError
from platform_eventbus import EventBus
from platform_secrets import SecretStore

from . import github
from .store import RepoStore

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

_TOKEN_KEY = "sources.github.token"
_REPO_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.repo")


@dataclass
class RepoDeps:
    store: RepoStore
    secrets: SecretStore
    bus: EventBus | None
    queue: asyncio.Queue  # clone 任务:repo_id
    workspace: Path  # clone 目的地根(workspace/repo/)


_deps: RepoDeps | None = None


def init_deps(deps: RepoDeps) -> None:
    global _deps
    _deps = deps


def require_deps() -> RepoDeps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _token() -> str | None:
    return _deps.secrets.get(_TOKEN_KEY) if _deps else None


def _require_repo(rid: str) -> dict[str, Any]:
    repo = require_deps().store.get(rid)
    if repo is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"资源不存在: {rid}")
    return repo


@capability(registry, name="import_repo", description="导入 GitHub 仓库:登记元数据+README,后台克隆",
            long_running=True, cost=5)
async def import_repo(url: str, category: str = "", clone: bool = True) -> JobRef:
    deps = require_deps()
    owner, name = github.parse_repo_url(url)
    existing = deps.store.get_by_url(f"https://github.com/{owner}/{name}")
    if existing and existing["status"] == "ready":
        raise ServiceError(_DOMAIN, ErrorSuffix.CONFLICT, f"仓库已导入: {owner}/{name}",
                           hint="list_repos 查看;重复导入请先 remove_repo")
    info = await github.fetch_repo_info(owner, name, _token())
    readme = await github.fetch_readme(owner, name, _token())
    rid = deps.store.add({**info, "category": category, "readme": readme,
                          "status": "importing", "source": "github"})
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.added", actor=_REPO_ACTOR,
            payload={"source_id": rid, "kind": "repo", "name": f"{owner}/{name}"}))
    if clone:
        deps.queue.put_nowait(rid)
    else:
        deps.store.set_status(rid, "ready")
    return JobRef(job_id=rid)


@capability(registry, name="list_repos", description="仓库列表(摘要,不含 README;§9.20)")
def list_repos(sort: str = "added", desc: bool = True, category: str = "") -> list[dict]:
    return require_deps().store.list(sort=sort, desc=desc, category=category)


@capability(registry, name="sort_repos", description="按字段排序:name/stars/added/updated")
def sort_repos(by: str = "name", desc: bool = False) -> list[dict]:
    """"按名字为项目排序"——用户能排,agent 也能排(铁律 4)。"""
    return require_deps().store.list(sort=by, desc=desc)


@capability(registry, name="get_readme", description="按需取仓库 README 全文")
def get_readme(repo_id: str) -> dict:
    repo = _require_repo(repo_id)
    return {"repo_id": repo_id, "name": repo["name"], "readme": repo["readme"]}


@capability(registry, name="get_repo", description="单个仓库详情(含 README)")
def get_repo(repo_id: str) -> dict:
    return _require_repo(repo_id)


@capability(registry, name="set_repo_meta",
            description="设置分类/标签/进度/备注(修订自旧 categories+tags+进度)")
def set_repo_meta(repo_id: str, category: str | None = None,
                  tags: list[str] | None = None, progress: str | None = None,
                  note: str | None = None) -> dict:
    deps = require_deps()
    _require_repo(repo_id)
    deps.store.set_meta(repo_id, category=category, tags=tags,
                        progress=progress, note=note)
    return deps.store.get(repo_id, with_readme=False)


@capability(registry, name="list_categories", description="已有分类(distinct)")
def list_categories() -> list[str]:
    return require_deps().store.categories()


@capability(registry, name="remove_repo", description="删除仓库记录与本地克隆",
            reversible=False, cost=2)
def remove_repo(repo_id: str) -> dict:
    deps = require_deps()
    repo = _require_repo(repo_id)
    deps.store.remove(repo_id)
    if repo["local_path"]:
        # 本地目录清理由 worker 异步做(与克隆同一队列,保序)
        deps.queue.put_nowait(("remove", repo_id, repo["local_path"]))
    return {"removed": repo_id, "name": repo["name"],
            "local_path": repo["local_path"]}


@capability(registry, name="search_remote_repos", description="搜索 GitHub 仓库(未导入的候选)",
            cost=3)
async def search_remote_repos(query: str, limit: int = 10) -> list[dict]:
    return await github.search_repos(query, _token(), limit)


@capability(registry, name="list_starred_repos", description="列出某 GitHub 账号的 stars",
            cost=3)
async def list_starred_repos(username: str, limit: int = 100) -> list[dict]:
    return await github.list_starred(username, _token(), limit)


@capability(registry, name="set_github_token", description="设置 GitHub token(secret:仅用户本人)")
def set_github_token(token: str, _actor: ActorRef = None) -> dict:
    if _actor is None or _actor.kind is not ActorKind.USER:
        raise ServiceError(_DOMAIN, ErrorSuffix.FORBIDDEN,
                           "GitHub token 属隐私数据,只能由用户本人填写")
    require_deps().secrets.set(_TOKEN_KEY, token)
    return {"has_token": True}
