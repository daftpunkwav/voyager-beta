"""笔记页界面:get/set_notes_view。与全站 appearance 分离;用户按钮与 agent 同权。"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ActorRef, ErrorSuffix, Event, ServiceError

from .runtime import ACTOR, DOMAIN, get_any, registry, require_deps

_UI_FONT_MIN, _UI_FONT_MAX, _UI_FONT_DEFAULT = 12, 24, 15
_UI_TOC_WIDTH_MIN, _UI_TOC_WIDTH_MAX, _UI_TOC_WIDTH_DEFAULT = 148, 480, 188
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
    "toc_width": "notes.ui.toc_width",
}


def _ui_get(key: str, default):
    s = require_deps().settings
    if s is None:
        return default
    try:
        val = s.get(key)
    except ServiceError:
        return default
    return default if val is None else val


def _clamp_toc_width(raw: object) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _UI_TOC_WIDTH_DEFAULT
    return max(_UI_TOC_WIDTH_MIN, min(_UI_TOC_WIDTH_MAX, n))


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
        "toc_width": _clamp_toc_width(_ui_get("notes.ui.toc_width", _UI_TOC_WIDTH_DEFAULT)),
        "persisted": require_deps().settings is not None,
    }


async def _emit_notes_ui(payload: dict, actor: ActorRef) -> None:
    deps = require_deps()
    if deps.bus is not None:
        await deps.bus.publish(Event(type="notes.ui.changed", actor=actor,
                                     payload=payload))


@capability(registry, name="get_notes_view",
            description="读笔记页界面:字号/视图/布局/当前或归档/排序/筛选/关键词/"
                        "关联资源/回收站面板/疏密/目录宽度。与全站字号无关。")
def get_notes_view() -> dict:
    return _read_notes_view()


@capability(registry, name="set_notes_view",
            description="改笔记页界面(用户点按钮与 agent 调本能力等价,不影响全站)。"
                        "font_size 或 font_delta;mode=edit|preview|split;"
                        "layout=list|card;sync_scroll;list_state=active|archived;"
                        "sort=updated|created|title;filter=all|pinned|untitled|unlinked|today;"
                        "query 关键词;source_id 关联资源(空串=全部);"
                        "panel=none|trash;density=comfortable|compact;"
                        "toc_width 目录宽度(像素,148–480);"
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
                         toc_width: int | None = None,
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
        sort, filter, query, source_id, panel, density, toc_width,
    )) or index or assist or quote_text is not None
    if not touched:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "至少提供一个界面参数",
                           hint="font_size / font_delta / mode / layout / "
                                "sync_scroll / list_state / sort / filter / "
                                "query / source_id / panel / density / toc_width / "
                                "assist / quote / note_id / index")
    if mode is not None and mode not in _UI_MODES:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"mode 须为 {list(_UI_MODES)}")
    if layout is not None and layout not in _UI_LAYOUTS:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"layout 须为 {list(_UI_LAYOUTS)}")
    if list_state is not None and list_state not in _UI_LIST_STATES:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"list_state 须为 {list(_UI_LIST_STATES)}")
    if sort is not None and sort not in _UI_SORTS:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"sort 须为 {list(_UI_SORTS)}")
    if filter is not None and filter not in _UI_FILTERS:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"filter 须为 {list(_UI_FILTERS)}")
    if panel is not None and panel not in _UI_PANELS:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"panel 须为 {list(_UI_PANELS)}")
    if density is not None and density not in _UI_DENSITIES:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"density 须为 {list(_UI_DENSITIES)}")
    if font_size is not None and not (_UI_FONT_MIN <= int(font_size) <= _UI_FONT_MAX):
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"font_size 须在 {_UI_FONT_MIN}–{_UI_FONT_MAX}")
    if source_id is not None:
        sid = str(source_id).strip()
        if "/" in sid or "\\" in sid or ".." in sid:
            raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                               "source_id 非法")
        source_id = sid[:_UI_SOURCE_MAX]
    if query is not None:
        query = str(query)[:_UI_QUERY_MAX]
    if note_id and note_id != "new" and not index:
        get_any(note_id)

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
    if toc_width is not None:
        patch["toc_width"] = _clamp_toc_width(toc_width)
    if panel is not None:
        patch["panel"] = panel
    elif note_id:
        patch["panel"] = "none"

    actor = _actor or ACTOR
    deps = require_deps()
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
