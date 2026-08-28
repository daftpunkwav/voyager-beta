"""笔记生命周期:创建/读取/更新/关联/回收站。"""

from __future__ import annotations

import time

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .runtime import DOMAIN, SORT_COL, STATES, emit, get_any, registry, require_alive, require_deps
from .validate import validate_content, validate_tag, validate_title


@capability(registry, name="create_note", description="新建 Markdown 笔记", cost=2)
async def create_note(title: str, content: str = "", tags: list[str] | None = None,
                      source_id: str = "", node_id: str = "") -> dict:
    deps = require_deps()
    title = validate_title(title)
    validate_content(content)
    clean_tags = [validate_tag(t) for t in (tags or [])]
    nid = deps.store.create({"title": title, "content": content,
                             "tags": clean_tags, "source_id": source_id,
                             "node_id": node_id})
    deps.store.sync_links(nid, content)
    await emit("note.created", nid, title=title)
    return deps.store.get(nid)


@capability(registry, name="get_note", description="按需取笔记全文(回收站内也可直读)")
def get_note(note_id: str) -> dict:
    return get_any(note_id)


@capability(registry, name="list_notes",
            description="笔记摘要列表(state=active/archived/trash/all;"
                        " query 关键词搜标题正文;sort=updated/created/title)")
def list_notes(source_id: str | None = None, tag: str = "",
               query: str = "", state: str = "active", sort: str = "",
               limit: int = 100) -> list[dict]:
    """sort 缺省读 notes.sort.default 设置;state 非法值回退 active。"""
    deps = require_deps()
    key = sort or (deps.settings.get("notes.sort.default") if deps.settings else "")
    order = SORT_COL.get(key, "updated_ts")
    view = state if state in STATES else "active"
    limit = max(1, min(int(limit), 500))
    page_size_cap = int(deps.settings.get("notes.list.page_size") or 0) \
        if deps.settings else 0
    if page_size_cap and limit > page_size_cap:
        limit = page_size_cap
    return deps.store.list(source_id=source_id, tag=tag, query=query,
                           state=view, sort=order, limit=limit)


@capability(registry, name="update_note",
            description="更新笔记标题/正文/标签/置顶/归档(正文变更自动存版本)",
            cost=2)
async def update_note(note_id: str, title: str | None = None,
                      content: str | None = None,
                      tags: list[str] | None = None,
                      pinned: bool | None = None,
                      archived: bool | None = None) -> dict:
    deps = require_deps()
    require_alive(note_id)
    if title is not None:
        title = validate_title(title)
    validate_content(content)
    clean_tags = [validate_tag(t) for t in tags] if tags is not None else None
    deps.store.history_keep = int(deps.settings.get("notes.history.per_note") or 0) \
        if deps.settings else deps.store.history_keep
    changed = deps.store.update(
        note_id, title=title, content=content, tags=clean_tags,
        pinned=pinned, archived=archived,
    )
    if not changed:
        return deps.store.get(note_id)
    if content is not None:
        deps.store.sync_links(note_id, content)
    await emit("note.edited", note_id,
                content_changed=content is not None,
                pinned=pinned, archived=archived)
    return deps.store.get(note_id)


@capability(registry, name="link_note", description="关联笔记到资源或图谱节点(传空串清除)",
            cost=2)
async def link_note(note_id: str, source_id: str | None = None,
                    node_id: str | None = None) -> dict:
    """"None = 不动;空串 = 清除关联"——agent 与用户都可维护引用关系。"""
    deps = require_deps()
    require_alive(note_id)
    deps.store.update(note_id, source_id=source_id, node_id=node_id)
    await emit("note.edited", note_id, linked=True)
    return deps.store.get(note_id)


@capability(registry, name="delete_note", description="移入回收站(可恢复)",
            reversible=True)
async def delete_note(note_id: str) -> dict:
    deps = require_deps()
    note = get_any(note_id)
    if note["trashed_ts"] is not None:
        raise ServiceError(DOMAIN, ErrorSuffix.CONFLICT,
                           "笔记已在回收站", hint="restore_note 可恢复")
    deps.store.trash(note_id)
    await emit("note.deleted", note_id, title=note["title"])
    return {"trashed": note_id, "title": note["title"],
            "hint": "restore_note 可恢复;purge_note 彻底删除"}


@capability(registry, name="restore_note", description="从回收站恢复笔记")
async def restore_note(note_id: str) -> dict:
    deps = require_deps()
    note = get_any(note_id)
    if note["trashed_ts"] is None:
        raise ServiceError(DOMAIN, ErrorSuffix.CONFLICT, "笔记不在回收站")
    deps.store.restore(note_id)
    await emit("note.restored", note_id, title=note["title"])
    return deps.store.get(note_id)


@capability(registry, name="purge_note", description="彻底删除笔记及其版本与链接(不可逆)",
            reversible=False)
async def purge_note(note_id: str) -> dict:
    deps = require_deps()
    note = get_any(note_id)
    deps.store.delete(note_id)
    removed_assets = deps.purge_assets(note_id) if deps.purge_assets else []
    await emit("note.purged", note_id, title=note["title"],
                removed_assets=len(removed_assets))
    return {"purged": note_id, "title": note["title"]}


@capability(registry, name="empty_trash", description="清空回收站(依据 notes.trash.retention_days 为 0 时拒绝批量清)",
            reversible=False)
async def empty_trash(max_age_days: int | None = None) -> dict:
    """不带参数=清空全部回收站;带 N=只清进站超过 N 天的。"""
    deps = require_deps()
    rows = deps.store.list(state="trash", limit=10000)
    cutoff = None
    if max_age_days is not None:
        cutoff = time.time() - max_age_days * 86400
    purged: list[str] = []
    for row in rows:
        trashed_ts = row.get("trashed_ts")
        if cutoff is not None and (trashed_ts is None or trashed_ts > cutoff):
            continue
        nid = row["id"]
        removed_assets = deps.purge_assets(nid) if deps.purge_assets else []
        deps.store.delete(nid)
        purged.append(nid)
        await emit("note.purged", nid, removed_assets=len(removed_assets))
    return {"purged_count": len(purged)}
