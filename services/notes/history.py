"""笔记历史与正文支撑:版本、大纲、内链解析、选区编辑、底纹。"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .marks import MarkError, apply_note_mark
from .runtime import DOMAIN, emit, registry, require_alive, require_deps
from .toc import extract_toc
from .validate import validate_content


@capability(registry, name="list_versions", description="笔记历史版本清单(新→旧)")
def list_versions(note_id: str) -> dict:
    require_alive(note_id)
    versions = require_deps().store.list_versions(note_id)
    return {"note_id": note_id, "versions": versions,
            "current_chars": len((require_deps().store.get(note_id) or {}).get("content") or "")}


@capability(registry, name="read_version", description="读取指定历史版本的正文")
def read_version(note_id: str, version: int) -> dict:
    dep = require_deps()
    require_alive(note_id)
    snap = dep.store.get_version(note_id, int(version))
    if snap is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND,
                           f"版本不存在: v{version}",
                           hint="list_versions 查看可用版本")
    return {"note_id": note_id, "version": version, **snap}


@capability(registry, name="restore_version",
            description="把历史版本内容恢复为当前内容(本身也会形成一次快照)", cost=2)
async def restore_version(note_id: str, version: int) -> dict:
    deps = require_deps()
    require_alive(note_id)
    snap = deps.store.get_version(note_id, int(version))
    if snap is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND,
                           f"版本不存在: v{version}")
    deps.store.update(note_id, content=snap["content"])
    deps.store.sync_links(note_id, snap["content"])
    await emit("note.edited", note_id, restored_version=int(version))
    return deps.store.get(note_id)


@capability(registry, name="get_note_toc",
            description="笔记标题大纲(level/text/line),供大纲面板与滚动定位")
def get_note_toc(note_id: str) -> dict:
    note = require_alive(note_id)
    return {"note_id": note_id, "toc": extract_toc(note["content"])}


@capability(registry, name="resolve_links",
            description="解析正文 [[内链]] 为 {raw,target_id,title} 明细;悬空链接 target_id 为空")
def resolve_links(note_id: str) -> dict:
    note = require_alive(note_id)
    links = require_deps().store.resolve_link_targets(note["content"])
    return {"note_id": note_id,
            "links": links,
            "resolved": sum(1 for i in links if i["target_id"]),
            "unresolved": sum(1 for i in links if not i["target_id"])}


@capability(registry, name="edit_note_range",
            description="按字符偏移原子替换正文区段([start,end);配合前端选中文字加粗/斜体/底纹等工具栏)",
            cost=2)
async def edit_note_range(note_id: str, start: int, end: int, new_text: str) -> dict:
    deps = require_deps()
    note = require_alive(note_id)
    content = note["content"]
    if not (0 <= start <= end <= len(content)):
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"区间 [{start},{end}) 超出正文范围(长度 {len(content)})",
        )
    new_content = content[:start] + (new_text or "") + content[end:]
    deps.store.update(note_id, content=new_content)
    deps.store.sync_links(note_id, new_content)
    await emit("note.edited", note_id,
                range_edit=True, start=start, end=end)
    return deps.store.get(note_id)


@capability(registry, name="mark_note_span",
            description="给正文中围栏外首次出现的可见片段加上或去掉底纹。"
                        "tone=warm|cool|rose|lime|violet|sand 着色;"
                        "亦可 rgbRRGGBB / #RRGGBB / RRGGBB 自定义色,clear 去掉。"
                        "语法 ==tone:文本==(仍是 Markdown)。代码围栏与行内代码内不着色;"
                        "ASCII 框线/表格行整行不包。已有底纹被更大选区套住时先拆平再包,不嵌套。"
                        "用户工具栏与本能力同权。",
            cost=2)
async def mark_note_span(note_id: str, quote: str, tone: str = "warm") -> dict:
    deps = require_deps()
    note = require_alive(note_id)
    try:
        new_content = apply_note_mark(note["content"], quote, tone)
    except MarkError as exc:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, str(exc)) from exc
    if new_content == note["content"]:
        return note
    validate_content(new_content)
    deps.store.update(note_id, content=new_content)
    deps.store.sync_links(note_id, new_content)
    await emit("note.edited", note_id, mark_span=True, tone=tone)
    return deps.store.get(note_id)
