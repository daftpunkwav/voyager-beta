"""笔记导入导出:workspace jail 内读写 Markdown(含轻量 front-matter)。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .runtime import DOMAIN, emit, registry, require_alive, require_deps
from .validate import MAX_IMPORT_BYTES, validate_content, validate_tag, validate_title

UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def workspace_root() -> Path:
    """jail 根。未注入则失败关闭,避免测试夹具漏配时放行任意路径。"""
    root = require_deps().workspace
    if root is None:
        raise ServiceError(
            DOMAIN, ErrorSuffix.UNAVAILABLE,
            "服务未配置 workspace,拒绝按路径读写",
            hint="独立运行与聚合运行均须经 wiring.wire(workspace=...) 注入",
        )
    return Path(root)


def split_front_matter(text: str) -> tuple[str, list[str], str]:
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


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def export_markdown(note: dict) -> dict:
    deps = require_deps()
    root = workspace_root()
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
            DOMAIN, ErrorSuffix.FORBIDDEN,
            "导出目录必须位于 workspace 内",
            hint="notes.export.dir 不得指向 jail 外路径",
        )
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_title = UNSAFE_FILENAME_RE.sub("_", note["title"]).strip(" .")[:80] or "untitled"
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


@capability(registry, name="import_note",
            description="导入外部 .md 文件(YAML front-matter 的 title/tags 可选生效)", cost=2)
async def import_note(file_path: str, title: str = "", tags: list[str] | None = None) -> dict:
    deps = require_deps()
    root = workspace_root()
    src = Path(file_path)
    if not _within(src, root):
        raise ServiceError(
            DOMAIN, ErrorSuffix.FORBIDDEN,
            "文件须位于 workspace/ 内",
            hint="先把 .md 放到 workspace/ 再导入,禁止读取 jail 外路径",
        )
    if not src.is_file():
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"文件不存在: {file_path}")
    if src.stat().st_size > MAX_IMPORT_BYTES:
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"文件超过导入上限 {MAX_IMPORT_BYTES} 字节",
        )
    raw = await asyncio.to_thread(src.read_text, encoding="utf-8", errors="replace")
    meta_title, meta_tags, body = split_front_matter(raw)
    validate_content(body)
    clean_tags = [validate_tag(t) for t in (tags or [])] or \
        [validate_tag(t) for t in meta_tags]
    final_title = validate_title(title or meta_title or src.stem)
    nid = deps.store.create({"title": final_title, "content": body,
                             "tags": clean_tags})
    deps.store.sync_links(nid, body)
    await emit("note.created", nid, title=final_title, imported=True)
    return deps.store.get(nid)


@capability(registry, name="export_note", description="导出为 Markdown 文件(front-matter+正文),返回落盘路径",
            cost=1)
async def export_note(note_id: str) -> dict:
    return export_markdown(require_alive(note_id))
