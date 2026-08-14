"""books 子模块能力(§8.2):add_book / list_books / get_chapter / remove_book。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from .store import BookStore

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

#: 可直接按"章节"切片阅读的文本格式;其余格式待解析管线(§8.4 AI 建图)
_TEXT_FORMATS = (".txt", ".md", ".markdown")


@dataclass
class BookDeps:
    store: BookStore
    workspace: Path


_deps: BookDeps | None = None


def init_deps(deps: BookDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> BookDeps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _require_book(bid: str) -> dict:
    book = _require_deps().store.get(bid)
    if book is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"书籍不存在: {bid}")
    return book


@capability(registry, name="add_book", description="登记书籍:文件副本入 workspace/books/", cost=2)
def add_book(title: str, file_path: str = "", author: str = "", note: str = "") -> dict:
    deps = _require_deps()
    local = ""
    fmt = ""
    if file_path:
        src = Path(file_path)
        if not src.is_file():
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"文件不存在: {file_path}")
        fmt = src.suffix.lower()
        dest_dir = Path(deps.workspace) / "books"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{title}{fmt}"
        shutil.copy2(src, dest)
        local = str(dest)
    bid = deps.store.add({"title": title, "author": author, "format": fmt,
                          "local_path": local, "note": note})
    return deps.store.get(bid)


@capability(registry, name="list_books", description="书籍列表(摘要)")
def list_books() -> list[dict]:
    return _require_deps().store.list()


@capability(registry, name="get_chapter", description="按需取书籍片段(txt/md 按字符区间)")
def get_chapter(book_id: str, start: int = 0, length: int = 8000) -> dict:
    book = _require_book(book_id)
    if book["format"] not in _TEXT_FORMATS:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"暂不支持直接读取 {book['format'] or '未知'} 格式",
            hint="txt/md 可直接读;PDF 等待解析管线(AI 建图,§8.4)",
        )
    if not book["local_path"]:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "该书籍没有本地文件")
    text = Path(book["local_path"]).read_text(encoding="utf-8", errors="replace")
    return {"book_id": book_id, "title": book["title"], "total_chars": len(text),
            "start": start, "text": text[start : start + length]}


@capability(registry, name="remove_book", description="删除书籍记录与本地副本", reversible=False)
def remove_book(book_id: str) -> dict:
    deps = _require_deps()
    book = _require_book(book_id)
    if book["local_path"]:
        Path(book["local_path"]).unlink(missing_ok=True)
    deps.store.remove(book_id)
    return {"removed": book_id, "title": book["title"]}
