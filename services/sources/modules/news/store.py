"""news 子模块(§8.2,初始最小集):抓取与登记新闻/资料条目。

fetch_news 抓 URL 正文(纯文本抽取,摘要级);聚合/去重/订阅源是后续演进。
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id        TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    url       TEXT NOT NULL DEFAULT '',
    summary   TEXT NOT NULL DEFAULT '',
    content   TEXT NOT NULL DEFAULT '',
    added_ts  REAL NOT NULL
);
"""


class NewsStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, item: dict[str, Any]) -> str:
        nid = uuid.uuid4().hex[:12]
        with self._lock:
            self._conn.execute(
                "INSERT INTO news (id, title, url, summary, content, added_ts)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (nid, item["title"], item.get("url", ""), item.get("summary", ""),
                 item.get("content", ""), time.time()),
            )
            self._conn.commit()
        return nid

    def get(self, nid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, title, url, summary, content, added_ts FROM news WHERE id = ?",
            (nid,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("id", "title", "url", "summary", "content", "added_ts"), row))

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        return [
            dict(zip(("id", "title", "url", "summary", "added_ts"), r))
            for r in self._conn.execute(
                "SELECT id, title, url, summary, added_ts FROM news"
                " ORDER BY added_ts DESC LIMIT ?", (limit,),
            )
        ]

    def remove(self, nid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM news WHERE id = ?", (nid,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def html_to_text(html: str, limit: int = 20000) -> tuple[str, str]:
    """粗粒度正文抽取:标题 + 去标签文本(摘要级,不追求完美解析)。"""
    m = _TITLE_RE.search(html)
    title = _TAG_RE.sub("", m.group(1)).strip() if m else ""
    text = _TAG_RE.sub(" ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text[:limit]
