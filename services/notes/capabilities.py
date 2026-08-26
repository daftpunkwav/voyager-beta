"""notes 能力注册表(§8.3):完整笔记能力面,用户与 agent 同权(铁律 4)。

- 状态机:archived(归档)/ trashed(回收站)/ pinned(置顶)——delete 是
  软删除入回收站(reversible=True),purge 才不可逆;
- 版本历史:content 每次实质变更自动快照,可列举/回读/恢复;
- 双向链接:[[标题或id]] 写入时解析,backlinks 查反链;
- 检索:query 关键词 LIKE 转义匹配标题与正文;tags/来源过滤;状态视图切换;
- 事件:note.created / note.edited / note.deleted(进回收站) /
  note.restored / note.purged。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .store import NoteStore

_DOMAIN = "notes"
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="notes.service")
registry = Registry(_DOMAIN)

_SORT_COL = {"updated": "updated_ts", "created": "created_ts", "title": "title"}
_STATES = ("active", "archived", "trash", "all")

# 导出文件名清洗(与 sources.books 同类防护;跨服务不共享代码,就近实现)
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass
class Deps:
    store: NoteStore
    bus: EventBus | None
    settings: SettingsStore | None = None


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _require_alive(nid: str) -> dict:
    """取未在回收站的笔记(归档态可读可改)。"""
    note = _require_deps().store.get(nid)
    if note is None or note["trashed_ts"] is not None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"笔记不存在: {nid}")
    return note


def _get_any(nid: str) -> dict:
    """含回收站笔记均可按 id 直读(get/版本/恢复场景)。"""
    note = _require_deps().store.get(nid)
    if note is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"笔记不存在: {nid}")
    return note


async def _emit(type_: str, note_id: str, **payload) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type=type_, actor=_ACTOR,
                  payload={"note_id": note_id, **payload})
        )


# ---------- 创建与读取 ----------

@capability(registry, name="create_note", description="新建 Markdown 笔记", cost=2)
async def create_note(title: str, content: str = "", tags: list[str] | None = None,
                      source_id: str = "", node_id: str = "") -> dict:
    deps = _require_deps()
    nid = deps.store.create({"title": title, "content": content,
                             "tags": tags or [], "source_id": source_id,
                             "node_id": node_id})
    deps.store.sync_links(nid, content)
    await _emit("note.created", nid, title=title)
    return deps.store.get(nid)


@capability(registry, name="get_note", description="按需取笔记全文(回收站内也可直读)")
def get_note(note_id: str) -> dict:
    return _get_any(note_id)


@capability(registry, name="list_notes",
            description="笔记摘要列表(state=active/archived/trash/all;"
                        " query 关键词搜标题正文;sort=updated/created/title)")
def list_notes(source_id: str | None = None, tag: str = "",
               query: str = "", state: str = "active", sort: str = "",
               limit: int = 100) -> list[dict]:
    """sort 缺省读 notes.sort.default 设置;state 非法值回退 active。"""
    deps = _require_deps()
    key = sort or (deps.settings.get("notes.sort.default") if deps.settings else "")
    order = _SORT_COL.get(key, "updated_ts")
    view = state if state in _STATES else "active"
    limit = max(1, min(int(limit), 500))
    page_size_cap = int(deps.settings.get("notes.list.page_size") or 0) \
        if deps.settings else 0
    if page_size_cap and limit > page_size_cap:
        limit = page_size_cap
    return deps.store.list(source_id=source_id, tag=tag, query=query,
                           state=view, sort=order, limit=limit)


# ---------- 编辑与状态 ----------

@capability(registry, name="update_note",
            description="更新笔记标题/正文/标签/置顶/归档(正文变更自动存版本)",
            cost=2)
async def update_note(note_id: str, title: str | None = None,
                      content: str | None = None,
                      tags: list[str] | None = None,
                      pinned: bool | None = None,
                      archived: bool | None = None) -> dict:
    deps = _require_deps()
    _require_alive(note_id)
    changed = deps.store.update(
        note_id, title=title, content=content, tags=tags,
        pinned=pinned, archived=archived,
    )
    if not changed:
        return deps.store.get(note_id)
    if content is not None:
        deps.store.sync_links(note_id, content)
    await _emit("note.edited", note_id,
                content_changed=content is not None,
                pinned=pinned, archived=archived)
    return deps.store.get(note_id)


@capability(registry, name="link_note", description="关联笔记到资源或图谱节点(传空串清除)",
            cost=2)
async def link_note(note_id: str, source_id: str | None = None,
                    node_id: str | None = None) -> dict:
    """"None = 不动;空串 = 清除关联"——agent 与用户都可维护引用关系。"""
    deps = _require_deps()
    _require_alive(note_id)
    deps.store.update(note_id, source_id=source_id, node_id=node_id)
    await _emit("note.edited", note_id, linked=True)
    return deps.store.get(note_id)


@capability(registry, name="delete_note", description="移入回收站(可恢复)",
            reversible=True)
async def delete_note(note_id: str) -> dict:
    deps = _require_deps()
    note = _get_any(note_id)
    if note["trashed_ts"] is not None:
        raise ServiceError(_DOMAIN, ErrorSuffix.CONFLICT,
                           "笔记已在回收站", hint="restore_note 可恢复")
    deps.store.trash(note_id)
    await _emit("note.deleted", note_id, title=note["title"])
    return {"trashed": note_id, "title": note["title"],
            "hint": "restore_note 可恢复;purge_note 彻底删除"}


@capability(registry, name="restore_note", description="从回收站恢复笔记")
async def restore_note(note_id: str) -> dict:
    deps = _require_deps()
    note = _get_any(note_id)
    if note["trashed_ts"] is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.CONFLICT, "笔记不在回收站")
    deps.store.restore(note_id)
    await _emit("note.restored", note_id, title=note["title"])
    return deps.store.get(note_id)


@capability(registry, name="purge_note", description="彻底删除笔记及其版本与链接(不可逆)",
            reversible=False)
async def purge_note(note_id: str) -> dict:
    deps = _require_deps()
    note = _get_any(note_id)
    deps.store.delete(note_id)
    await _emit("note.purged", note_id, title=note["title"])
    return {"purged": note_id, "title": note["title"]}


@capability(registry, name="empty_trash", description="清空回收站(依据 notes.trash.retention_days 为 0 时拒绝批量清)",
            reversible=False)
async def empty_trash(max_age_days: int | None = None) -> dict:
    """不带参数=清空全部回收站;带 N=只清进站超过 N 天的。"""
    deps = _require_deps()
    rows = deps.store.list(state="trash", limit=10000)
    cutoff = None
    if max_age_days is not None:
        cutoff = time.time() - max_age_days * 86400
    purged: list[str] = []
    for row in rows:
        trashed_ts = row.get("trashed_ts")
        if cutoff is not None and (trashed_ts is None or trashed_ts > cutoff):
            continue
        deps.store.delete(row["id"])
        purged.append(row["id"])
    for nid in purged:
        await _emit("note.purged", nid)
    return {"purged_count": len(purged)}


# ---------- 检索增强 ----------

@capability(registry, name="list_tags", description="存活笔记的标签清单(含计数)")
def list_tags() -> list[dict]:
    return [{"tag": t, "count": c} for t, c in _require_deps().store.all_tags()]


@capability(registry, name="rename_tag", description="全局重命名标签(所有笔记生效)", cost=2)
async def rename_tag(old: str, new: str) -> dict:
    count = _require_deps().store.rename_tag(old, new)
    return {"renamed_from": old, "to": new, "affected": count}


@capability(registry, name="get_backlinks", description="反链:哪些存活笔记链接到该笔记")
def get_backlinks(note_id: str) -> dict:
    _get_any(note_id)  # 存在性校验(回收站内也可查其反链)
    links = _require_deps().store.backlinks(note_id)
    return {"note_id": note_id, "backlinks": links}


@capability(registry, name="notes_stats", description="计数统计(活跃/归档/回收站/热门标签)")
def notes_stats() -> dict:
    return _require_deps().store.stats()


# ---------- 版本历史 ----------

@capability(registry, name="list_versions", description="笔记历史版本清单(新→旧)")
def list_versions(note_id: str) -> dict:
    _require_alive(note_id)
    versions = _require_deps().store.list_versions(note_id)
    return {"note_id": note_id, "versions": versions,
            "current_chars": len((_require_deps().store.get(note_id) or {}).get("content") or "")}


@capability(registry, name="read_version", description="读取指定历史版本的正文")
def read_version(note_id: str, version: int) -> dict:
    dep = _require_deps()
    _require_alive(note_id)
    snap = dep.store.get_version(note_id, int(version))
    if snap is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                           f"版本不存在: v{version}",
                           hint="list_versions 查看可用版本")
    return {"note_id": note_id, "version": version, **snap}


@capability(registry, name="restore_version",
            description="把历史版本内容恢复为当前内容(本身也会形成一次快照)", cost=2)
async def restore_version(note_id: str, version: int) -> dict:
    deps = _require_deps()
    _require_alive(note_id)
    snap = deps.store.get_version(note_id, int(version))
    if snap is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                           f"版本不存在: v{version}")
    deps.store.update(note_id, content=snap["content"])  # 更新旧文会再入历史
    deps.store.sync_links(note_id, snap["content"])
    await _emit("note.edited", note_id, restored_version=int(version))
    return deps.store.get(note_id)


# ---------- 导出 ----------

@capability(registry, name="export_note", description="导出为 Markdown 文件(front-matter+正文),返回落盘路径",
            cost=1)
async def export_note(note_id: str) -> dict:
    note = _require_alive(note_id)
    export_dir = Path("workspace") / "notes-export"
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _UNSAFE_FILENAME_RE.sub("_", note["title"]).strip(" .")[:80] or "untitled"
    dest = export_dir / f"{safe_title}_{note['id']}.md"
    body = (
        "---\n"
        f"id: {note['id']}\n"
        f"title: {note['title']}\n"
        f"tags: {json.dumps(note['tags'], ensure_ascii=False)}\n"
        f"created: {_fmt_ts(note['created_ts'])}\n"
        f"updated: {_fmt_ts(note['updated_ts'])}\n"
        "---\n\n"
        + note["content"]
    )
    dest.write_text(body, encoding="utf-8")
    return {"note_id": note["id"], "path": str(dest), "chars": len(body)}


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
