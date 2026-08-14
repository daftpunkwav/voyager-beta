"""books 子模块(§8.2,初始最小集):书籍登记与章节读取。

书籍文件副本落 `workspace/books/`;txt/md 直接可读,PDF 等格式的解析
是后续演进(索引走 AI 管线,§8.4)。本子模块自包含,不 import 其他子模块。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    author     TEXT NOT NULL DEFAULT '',
    format     TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    added_ts   REAL NOT NULL
);
"""


class BookStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, book: dict[str, Any]) -> str:
        bid = uuid.uuid4().hex[:12]
        with self._lock:
            self._conn.execute(
                "INSERT INTO books (id, title, author, format, local_path, note, added_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (bid, book["title"], book.get("author", ""), book.get("format", ""),
                 book.get("local_path", ""), book.get("note", ""), time.time()),
            )
            self._conn.commit()
        return bid

    def get(self, bid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, title, author, format, local_path, note, added_ts"
            " FROM books WHERE id = ?", (bid,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("id", "title", "author", "format", "local_path",
                         "note", "added_ts"), row))

    def list(self) -> list[dict[str, Any]]:
        return [
            dict(zip(("id", "title", "author", "format", "added_ts"), r))
            for r in self._conn.execute(
                "SELECT id, title, author, format, added_ts FROM books"
                " ORDER BY added_ts DESC"
            )
        ]

    def remove(self, bid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM books WHERE id = ?", (bid,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
