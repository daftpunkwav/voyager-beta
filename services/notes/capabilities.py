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

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .marks import MarkError, apply_note_mark
from .store import NoteStore, extract_toc

_DOMAIN = "notes"
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="notes.service")
registry = Registry(_DOMAIN)

_SORT_COL = {"updated": "updated_ts", "created": "created_ts", "title": "title"}
_STATES = ("active", "archived", "trash", "all")

# 导出文件名清洗(与 sources.books 同类防护;跨服务不共享代码,就近实现)
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_MAX_TITLE = 200
_MAX_CONTENT = 200_000
# 导入按字节硬顶,避免先把超大文件读进内存再截断
_MAX_IMPORT_BYTES = _MAX_CONTENT * 4
# 标签名进入 JSON 文本做整词替换,这些字符会破坏数组结构或转义语义
_TAG_FORBIDDEN = '"\\,[]'


def _validate_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "标题不能为空")
    if len(title) > _MAX_TITLE:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"标题过长(≤{_MAX_TITLE} 字)")
    return title


def _validate_content(content: str | None) -> None:
    if content is not None and len(content) > _MAX_CONTENT:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"正文过长(≤{_MAX_CONTENT} 字符)")


def _validate_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not tag or any(ch in _TAG_FORBIDDEN for ch in tag):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"标签为空或含非法字符({_TAG_FORBIDDEN}): {tag!r}")
    if len(tag) > 32:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "标签过长(≤32 字)")
    return tag


@dataclass
class Deps:
    store: NoteStore
    bus: EventBus | None
    settings: SettingsStore | None = None
    purge_assets: Callable[[str], list[str]] | None = None  # purge 时连带清附件
    workspace: Path | None = None  # import/export 的 jail 根;wire() 必填


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


# ---------- 笔记页界面(与全站 appearance.* 分离;用户按钮 = 本能力) ----------

_UI_FONT_MIN, _UI_FONT_MAX, _UI_FONT_DEFAULT = 12, 24, 15
_UI_MODES = ("edit", "preview", "split")
_UI_LAYOUTS = ("list", "card")
_UI_LIST_STATES = ("active", "archived")
_UI_SORTS = ("updated", "created", "title")
_UI_FILTERS = ("all", "pinned", "untitled", "unlinked", "today")
_UI_PANELS = ("none", "trash")
_UI_DENSITIES = ("comfortable", "compact")
_UI_QUERY_MAX = 80
_UI_SOURCE_MAX = 80
_UI_QUOTE_MAX = 500
_UI_KEYS = {
    "font_size": "notes.ui.font_size",
    "mode": "notes.ui.mode",
    "layout": "notes.ui.layout",
    "sync_scroll": "notes.ui.sync_scroll",
    "list_state": "notes.ui.list_state",
    "sort": "notes.ui.sort",
    "filter": "notes.ui.filter",
    "query": "notes.ui.query",
    "source_id": "notes.ui.source_id",
    "panel": "notes.ui.panel",
    "density": "notes.ui.density",
}


def _ui_get(key: str, default):
    s = _require_deps().settings
    if s is None:
        return default
    try:
        val = s.get(key)
    except ServiceError:
        return default
    return default if val is None else val


def _read_notes_view() -> dict:
    mode = str(_ui_get("notes.ui.mode", "edit"))
    layout = str(_ui_get("notes.ui.layout", "list"))
    list_state = str(_ui_get("notes.ui.list_state", "active"))
    sort = str(_ui_get("notes.ui.sort", "updated"))
    filt = str(_ui_get("notes.ui.filter", "all"))
    panel = str(_ui_get("notes.ui.panel", "none"))
    density = str(_ui_get("notes.ui.density", "comfortable"))
    return {
        "font_size": int(_ui_get("notes.ui.font_size", _UI_FONT_DEFAULT)),
        "mode": mode if mode in _UI_MODES else "edit",
        "layout": layout if layout in _UI_LAYOUTS else "list",
        "sync_scroll": bool(_ui_get("notes.ui.sync_scroll", True)),
        "list_state": list_state if list_state in _UI_LIST_STATES else "active",
        "sort": sort if sort in _UI_SORTS else "updated",
        "filter": filt if filt in _UI_FILTERS else "all",
        "query": str(_ui_get("notes.ui.query", "") or "")[:_UI_QUERY_MAX],
        "source_id": str(_ui_get("notes.ui.source_id", "") or "")[:_UI_SOURCE_MAX],
        "panel": panel if panel in _UI_PANELS else "none",
        "density": density if density in _UI_DENSITIES else "comfortable",
        "persisted": _require_deps().settings is not None,
    }


async def _emit_notes_ui(payload: dict, actor: ActorRef) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(Event(type="notes.ui.changed", actor=actor,
                                     payload=payload))


# ---------- 创建与读取 ----------

@capability(registry, name="create_note", description="新建 Markdown 笔记", cost=2)
async def create_note(title: str, content: str = "", tags: list[str] | None = None,
                      source_id: str = "", node_id: str = "") -> dict:
    deps = _require_deps()
    title = _validate_title(title)
    _validate_content(content)
    clean_tags = [_validate_tag(t) for t in (tags or [])]
    nid = deps.store.create({"title": title, "content": content,
                             "tags": clean_tags, "source_id": source_id,
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


@capability(registry, name="get_notes_view",
            description="读笔记页界面:字号/视图/布局/在用或归档/排序/筛选/关键词/"
                        "关联资源/回收站面板/疏密。与全站字号无关。")
def get_notes_view() -> dict:
    return _read_notes_view()


@capability(registry, name="set_notes_view",
            description="改笔记页界面(用户点按钮与 agent 调本能力等价,不影响全站)。"
                        "font_size 或 font_delta;mode=edit|preview|split;"
                        "layout=list|card;sync_scroll;list_state=active|archived;"
                        "sort=updated|created|title;filter=all|pinned|untitled|unlinked|today;"
                        "query 关键词;source_id 关联资源(空串=全部);"
                        "panel=none|trash;density=comfortable|compact;"
                        "assist=true 打开笔记页悬浮对话;quote 把选区交给侦察人格快速解读(不落库);"
                        "note_id 打开一篇(含 new);index=true 回列表。",
            cost=1)
async def set_notes_view(font_size: int | None = None,
                         font_delta: int | None = None,
                         mode: str | None = None,
                         layout: str | None = None,
                         sync_scroll: bool | None = None,
                         list_state: str | None = None,
                         sort: str | None = None,
                         filter: str | None = None,
                         query: str | None = None,
                         source_id: str | None = None,
                         panel: str | None = None,
                         density: str | None = None,
                         assist: bool = False,
                         quote: str | None = None,
                         note_id: str | None = None,
                         index: bool = False,
                         _actor: ActorRef = None) -> dict:
    quote_text = None
    if quote is not None:
        quote_text = " ".join(str(quote).split())[:_UI_QUOTE_MAX] or None
    touched = any(v is not None for v in (
        font_size, font_delta, mode, layout, sync_scroll, list_state, note_id,
        sort, filter, query, source_id, panel, density,
    )) or index or assist or quote_text is not None
    if not touched:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "至少提供一个界面参数",
                           hint="font_size / font_delta / mode / layout / "
                                "sync_scroll / list_state / sort / filter / "
                                "query / source_id / panel / density / "
                                "assist / quote / note_id / index")
    if mode is not None and mode not in _UI_MODES:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"mode 须为 {list(_UI_MODES)}")
    if layout is not None and layout not in _UI_LAYOUTS:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"layout 须为 {list(_UI_LAYOUTS)}")
    if list_state is not None and list_state not in _UI_LIST_STATES:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"list_state 须为 {list(_UI_LIST_STATES)}")
    if sort is not None and sort not in _UI_SORTS:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"sort 须为 {list(_UI_SORTS)}")
    if filter is not None and filter not in _UI_FILTERS:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"filter 须为 {list(_UI_FILTERS)}")
    if panel is not None and panel not in _UI_PANELS:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"panel 须为 {list(_UI_PANELS)}")
    if density is not None and density not in _UI_DENSITIES:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"density 须为 {list(_UI_DENSITIES)}")
    if font_size is not None and not (_UI_FONT_MIN <= int(font_size) <= _UI_FONT_MAX):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"font_size 须在 {_UI_FONT_MIN}–{_UI_FONT_MAX}")
    if source_id is not None:
        sid = str(source_id).strip()
        if "/" in sid or "\\" in sid or ".." in sid:
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               "source_id 非法")
        source_id = sid[:_UI_SOURCE_MAX]
    if query is not None:
        query = str(query)[:_UI_QUERY_MAX]
    if note_id and note_id != "new" and not index:
        _get_any(note_id)

    view = _read_notes_view()
    patch: dict = {}
    if font_size is not None:
        patch["font_size"] = int(font_size)
    elif font_delta is not None:
        nxt = int(view["font_size"]) + int(font_delta)
        patch["font_size"] = max(_UI_FONT_MIN, min(_UI_FONT_MAX, nxt))
    if mode is not None:
        patch["mode"] = mode
    if layout is not None:
        patch["layout"] = layout
    if sync_scroll is not None:
        patch["sync_scroll"] = bool(sync_scroll)
    if list_state is not None:
        patch["list_state"] = list_state
    if sort is not None:
        patch["sort"] = sort
    if filter is not None:
        patch["filter"] = filter
    if query is not None:
        patch["query"] = query
    if source_id is not None:
        patch["source_id"] = source_id
    if density is not None:
        patch["density"] = density
    if panel is not None:
        patch["panel"] = panel
    elif note_id:
        patch["panel"] = "none"

    actor = _actor or _ACTOR
    deps = _require_deps()
    persisted = deps.settings is not None
    if patch and deps.settings is not None:
        for field, value in patch.items():
            await deps.settings.set(_UI_KEYS[field], value, actor)
        view = _read_notes_view()
    else:
        view = {**view, **patch, "persisted": persisted}

    action = "index" if index else ("open" if note_id else None)
    out = {
        **view,
        "persisted": persisted,
        "action": action,
        "note_id": None if index else note_id,
        "assist": bool(assist) or bool(quote_text),
        "quote": quote_text or "",
    }
    # 事件只带本次变更,避免用整份快照盖掉并行的字号/视图本地乐观更新
    event_payload = {
        **patch,
        "action": action,
        "note_id": out["note_id"],
        "persisted": persisted,
    }
    if assist:
        event_payload["assist"] = True
    if quote_text:
        event_payload["quote"] = quote_text
        event_payload["assist"] = True
    await _emit_notes_ui(event_payload, actor)
    return out


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
    if title is not None:
        title = _validate_title(title)
    _validate_content(content)
    clean_tags = [_validate_tag(t) for t in tags] if tags is not None else None
    # 版本保留数允许运行中调整设置即时生效
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
    removed_assets = deps.purge_assets(note_id) if deps.purge_assets else []
    await _emit("note.purged", note_id, title=note["title"],
                removed_assets=len(removed_assets))
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
        nid = row["id"]
        removed_assets = deps.purge_assets(nid) if deps.purge_assets else []
        deps.store.delete(nid)
        purged.append(nid)
        await _emit("note.purged", nid, removed_assets=len(removed_assets))
    return {"purged_count": len(purged)}


# ---------- 检索增强 ----------

@capability(registry, name="list_tags", description="存活笔记的标签清单(含计数)")
def list_tags() -> list[dict]:
    return [{"tag": t, "count": c} for t, c in _require_deps().store.all_tags()]


@capability(registry, name="rename_tag", description="全局重命名标签(所有笔记生效)", cost=2)
async def rename_tag(old: str, new: str) -> dict:
    old = _validate_tag(old)
    new = _validate_tag(new)
    if old == new:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "新旧标签相同")
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


# ---------- 渲染与编辑支撑(参考主流 Markdown 工具:大纲/内链/选区编辑/导入) ----------

@capability(registry, name="get_note_toc",
            description="笔记标题大纲(level/text/line),供大纲面板与滚动定位")
def get_note_toc(note_id: str) -> dict:
    note = _require_alive(note_id)
    return {"note_id": note_id, "toc": extract_toc(note["content"])}


@capability(registry, name="resolve_links",
            description="解析正文 [[内链]] 为 {raw,target_id,title} 明细;悬空链接 target_id 为空")
def resolve_links(note_id: str) -> dict:
    note = _require_alive(note_id)
    links = _require_deps().store.resolve_link_targets(note["content"])
    return {"note_id": note_id,
            "links": links,
            "resolved": sum(1 for i in links if i["target_id"]),
            "unresolved": sum(1 for i in links if not i["target_id"])}


@capability(registry, name="edit_note_range",
            description="按字符偏移原子替换正文区段([start,end);配合前端选中文字加粗/斜体/底纹等工具栏)",
            cost=2)
async def edit_note_range(note_id: str, start: int, end: int, new_text: str) -> dict:
    deps = _require_deps()
    note = _require_alive(note_id)
    content = note["content"]  # 存储层已统一 LF,偏移量以此为基准
    if not (0 <= start <= end <= len(content)):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"区间 [{start},{end}) 超出正文范围(长度 {len(content)})",
        )
    new_content = content[:start] + (new_text or "") + content[end:]
    deps.store.update(note_id, content=new_content)  # 自动快照旧文
    deps.store.sync_links(note_id, new_content)
    await _emit("note.edited", note_id,
                range_edit=True, start=start, end=end)
    return deps.store.get(note_id)


@capability(registry, name="mark_note_span",
            description="给正文中围栏外首次出现的可见片段加上或去掉底纹。"
                        "tone=warm|cool|rose|lime 着色,clear 去掉。"
                        "语法 ==tone:文本==(仍是 Markdown)。代码围栏与行内代码内不着色;"
                        "ASCII 框线/表格行整行不包。已有底纹被更大选区套住时先拆平再包,不嵌套。"
                        "用户工具栏与本能力同权。",
            cost=2)
async def mark_note_span(note_id: str, quote: str, tone: str = "warm") -> dict:
    deps = _require_deps()
    note = _require_alive(note_id)
    try:
        new_content = apply_note_mark(note["content"], quote, tone)
    except MarkError as exc:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, str(exc)) from exc
    if new_content == note["content"]:
        return note
    _validate_content(new_content)
    deps.store.update(note_id, content=new_content)
    deps.store.sync_links(note_id, new_content)
    await _emit("note.edited", note_id, mark_span=True, tone=tone)
    return deps.store.get(note_id)


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _workspace() -> Path:
    """jail 根。未注入则失败关闭,避免测试夹具漏配时放行任意路径。"""
    root = _require_deps().workspace
    if root is None:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.UNAVAILABLE,
            "服务未配置 workspace,拒绝按路径读写",
            hint="独立运行与聚合运行均须经 wiring.wire(workspace=...) 注入",
        )
    return Path(root)


@capability(registry, name="import_note",
            description="导入外部 .md 文件(YAML front-matter 的 title/tags 可选生效)", cost=2)
async def import_note(file_path: str, title: str = "", tags: list[str] | None = None) -> dict:
    deps = _require_deps()
    root = _workspace()
    src = Path(file_path)
    # 先 jail 再存在性:避免用 NOT_FOUND 泄露 jail 外路径是否存在
    if not _within(src, root):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.FORBIDDEN,
            "文件须位于 workspace/ 内",
            hint="先把 .md 放到 workspace/ 再导入,禁止读取 jail 外路径",
        )
    if not src.is_file():
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"文件不存在: {file_path}")
    if src.stat().st_size > _MAX_IMPORT_BYTES:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"文件超过导入上限 {_MAX_IMPORT_BYTES} 字节",
        )
    raw = await asyncio.to_thread(src.read_text, encoding="utf-8", errors="replace")
    meta_title, meta_tags, body = _split_front_matter(raw)
    _validate_content(body)
    clean_tags = [_validate_tag(t) for t in (tags or [])] or \
        [_validate_tag(t) for t in meta_tags]
    final_title = _validate_title(title or meta_title or src.stem)
    nid = deps.store.create({"title": final_title, "content": body,
                             "tags": clean_tags})
    deps.store.sync_links(nid, body)
    await _emit("note.created", nid, title=final_title, imported=True)
    return deps.store.get(nid)


def _split_front_matter(text: str) -> tuple[str, list[str], str]:
    """轻量 YAML front-matter:支持 title 与 tags([a,b] 或逐行 '- a')。

    只认文档开头第一个 '---' 块;其余字段一律忽略,块后内容原样保留。
    """
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "", [], text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return "", [], text
    title = ""
    tags: list[str] = []
    in_tags_list = False
    for line in lines[1:end]:
        stripped = line.strip()
        if stripped.startswith("- ") and in_tags_list:
            tags.append(stripped[2:].strip().strip("'\""))
            continue
        in_tags_list = False
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "title":
            title = value.strip("'\"")
        elif key == "tags":
            in_tags_list = True
            if value.startswith("[") and value.endswith("]"):
                tags = [t.strip().strip("'\"") for t in value[1:-1].split(",")
                        if t.strip()]
                in_tags_list = False
            elif not value:
                continue
    body = "\n".join(lines[end + 1:])
    return title, [t for t in tags if t], body


# ---------- 导出 ----------

@capability(registry, name="export_note", description="导出为 Markdown 文件(front-matter+正文),返回落盘路径",
            cost=1)
async def export_note(note_id: str) -> dict:
    note = _require_alive(note_id)
    deps = _require_deps()
    root = _workspace()
    export_dir_setting = ""
    if deps.settings is not None:
        export_dir_setting = str(deps.settings.get("notes.export.dir") or "")
    raw = export_dir_setting or "workspace/notes-export"
    export_dir = Path(raw)
    if not export_dir.is_absolute():
        export_dir = root / export_dir
    export_dir = export_dir.resolve()
    if not _within(export_dir, root):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.FORBIDDEN,
            "导出目录必须位于 workspace 内",
            hint="notes.export.dir 不得指向 jail 外路径",
        )
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
