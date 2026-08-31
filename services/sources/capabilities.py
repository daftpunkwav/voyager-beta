"""sources 聚合注册表(§6.4/§8.2):合并子模块注册表 + 跨类型统一资源流。

子模块在 modules/ 下自包含,互不 import;壳只读合并(依赖矩阵 §12)。
统一资源流(list_sources/search_sources/sources_stats)只做 fan-out 与
合并排序:每个子模块 store 暴露同形状的 summaries()/stats(),聚合层
不含任何类型分支;新增资源类型 = STORES 注册一行,聚合能力零改动。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError
from platform_eventbus import EventBus
from platform_secrets import SecretStore

from .modules.doc import capabilities as doc_caps
from .modules.doc.store import DocStore
from .modules.repo import capabilities as repo_caps
from .modules.repo.store import RepoStore
from .modules.web import capabilities as web_caps
from .modules.web.store import WebStore

_DOMAIN = "sources"

registry = Registry(_DOMAIN)
registry.merge(repo_caps.registry, doc_caps.registry, web_caps.registry)

#: kind → store;wiring(init_all)完成后填充,聚合能力据此 fan-out
STORES: dict[str, object] = {}


@dataclass
class SourcesDeps:
    """聚合层统一装配的子模块依赖。"""

    repo_store: RepoStore
    doc_store: DocStore
    web_store: WebStore
    secrets: SecretStore
    bus: EventBus | None
    repo_queue: asyncio.Queue
    doc_queue: asyncio.Queue
    workspace: Path
    settings: object | None = None  # SettingsStore;doc 子模块读解析上限用


def init_all(deps: SourcesDeps) -> None:
    repo_caps.init_deps(repo_caps.RepoDeps(
        store=deps.repo_store, secrets=deps.secrets, bus=deps.bus,
        queue=deps.repo_queue, workspace=deps.workspace,
    ))
    doc_caps.init_deps(doc_caps.DocDeps(
        store=deps.doc_store, bus=deps.bus, queue=deps.doc_queue,
        workspace=deps.workspace, settings=deps.settings,
    ))
    web_caps.init_deps(web_caps.WebDeps(store=deps.web_store, bus=deps.bus))
    STORES.clear()
    STORES.update({"repo": deps.repo_store, "doc": deps.doc_store,
                   "web": deps.web_store})


def _stores(kind: str) -> list:
    """选中的 store 列表;kind 非法即 INVALID_INPUT(参数校验,非类型逻辑)。"""
    kind = kind.strip().lower()
    if kind and kind not in STORES:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"未知资源类型: {kind}",
                           hint=f"可选: {'/'.join(sorted(STORES))} 或留空取全部")
    if kind:
        return [STORES[kind]]
    return [STORES[k] for k in sorted(STORES)]


_SORT_KEYS = {"added": "added_ts", "updated": "updated_ts", "title": "title"}

#: 单店单次 fan-out 的行数上限;≥ graph L0 的 per-kind 取数(2000),抬帽
#: 必须连带核对 L0(deploy 资源目录桥),否则 L0 会被静默截断成残图
_MAX_PER_STORE = 2000


@capability(registry, name="list_sources",
            description="跨类型列出资料库资源摘要(统一资源流;kind 空=全部)")
def list_sources(kind: str = "", status: str = "", tag: str = "", query: str = "",
                 sort: str = "added", desc: bool = True,
                 limit: int = 200) -> list[dict]:
    merged: list[dict] = []
    for store in _stores(kind):
        merged.extend(store.summaries(status=status.strip(), tag=tag.strip(),
                                      query=query.strip(),
                                      limit=min(limit, _MAX_PER_STORE)))
    key = _SORT_KEYS.get(sort, "added_ts")
    merged.sort(key=lambda r: str(r.get(key) or ""), reverse=desc)
    return merged[:limit]


@capability(registry, name="search_sources",
            description="跨类型检索资源:标题/标签命中 + 文档分章正文命中(带章号定位)")
def search_sources(query: str, kind: str = "", limit: int = 20) -> list[dict]:
    query = query.strip()
    if not query:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "query 不能为空")
    merged: list[dict] = []
    for store in _stores(kind):
        merged.extend(store.summaries(query=query, limit=min(limit, 100)))
    # 文档分章正文命中:附加到结果流,带 section_no 定位(与标题命中去重)
    if not kind or kind.strip().lower() == "doc":
        doc_store = STORES.get("doc")
        if doc_store is not None:
            seen = {r["id"] for r in merged}
            for hit in doc_store.search_summaries(query, min(limit, 100)):
                if hit["id"] in seen:
                    continue
                merged.append(hit)
                seen.add(hit["id"])
    merged.sort(key=lambda r: float(r.get("added_ts") or 0.0), reverse=True)
    return merged[:limit]


@capability(registry, name="sources_stats",
            description="资料库统计(各类型数量与导入中/失败数;agent 上下文摘要用)")
def sources_stats() -> dict:
    stats = {name: store.stats() for name, store in STORES.items()}
    out = {name: s["total"] for name, s in stats.items()}
    out["importing"] = sum(s.get("importing", 0) for s in stats.values())
    out["failed"] = sum(s.get("failed", 0) for s in stats.values())
    return out
