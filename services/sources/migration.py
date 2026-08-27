"""旧 books/news 库到 doc/web 的一次性迁移(仅旧库存在时执行,幂等)。

books 行 → documents(旧库无解析产物,status 全部置 stored);
news 行 → webpages(url 域名回填)。迁移完成后旧库改名 *.bak 保留
(不静默删除用户数据;人工验收后可清理)。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def migrate_legacy_books_news(data_dir: str | Path) -> None:
    data_dir = Path(data_dir)
    _migrate_books(data_dir / "books.db", data_dir / "doc.db")
    _migrate_news(data_dir / "news.db", data_dir / "web.db")


def _migrate_books(old_path: Path, new_path: Path) -> None:
    if not old_path.is_file():
        return
    conn = sqlite3.connect(str(old_path))
    try:
        rows = conn.execute(
            "SELECT id, title, author, format, local_path, note, added_ts"
            " FROM books").fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return
    conn.close()
    if not rows:
        old_path.rename(old_path.with_suffix(".db.bak"))
        return
    target = sqlite3.connect(str(new_path))
    target.executescript(
        "CREATE TABLE IF NOT EXISTS documents ("
        " id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL DEFAULT '',"
        " ext TEXT NOT NULL DEFAULT '', local_path TEXT NOT NULL DEFAULT '',"
        " category TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',"
        " progress TEXT NOT NULL DEFAULT 'none', note TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'importing', error TEXT NOT NULL DEFAULT '',"
        " source TEXT NOT NULL DEFAULT 'manual', added_ts REAL NOT NULL,"
        " updated_ts REAL NOT NULL);")
    now = _now()
    for bid, title, author, fmt, local_path, note, added_ts in rows:
        existing = target.execute(
            "SELECT 1 FROM documents WHERE id = ?", (bid,)).fetchone()
        if existing:
            continue
        target.execute(
            "INSERT OR IGNORE INTO documents (id, title, filename, ext,"
            " local_path, note, status, source, added_ts, updated_ts)"
            " VALUES (?, ?, ?, ?, ?, ?, 'stored', 'migrated', ?, ?)",
            (bid, title, Path(local_path).name if local_path else "",
             fmt or "", local_path or "", note or "", added_ts or now, now))
    target.commit()
    target.close()
    old_path.rename(old_path.with_suffix(".db.bak"))


def _migrate_news(old_path: Path, new_path: Path) -> None:
    if not old_path.is_file():
        return
    conn = sqlite3.connect(str(old_path))
    try:
        rows = conn.execute(
            "SELECT id, title, url, summary, content, added_ts"
            " FROM news").fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return
    conn.close()
    if not rows:
        old_path.rename(old_path.with_suffix(".db.bak"))
        return
    target = sqlite3.connect(str(new_path))
    target.executescript(
        "CREATE TABLE IF NOT EXISTS webpages ("
        " id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',"
        " domain TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',"
        " content TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',"
        " category TEXT NOT NULL DEFAULT '', meta TEXT NOT NULL DEFAULT '{}',"
        " added_ts REAL NOT NULL, updated_ts REAL NOT NULL);")
    now = _now()
    from urllib.parse import urlparse
    for nid, title, url, summary, content, added_ts in rows:
        existing = target.execute(
            "SELECT 1 FROM webpages WHERE id = ?", (nid,)).fetchone()
        if existing:
            continue
        domain = urlparse(url).hostname or "" if url else ""
        target.execute(
            "INSERT OR IGNORE INTO webpages (id, title, url, domain, summary,"
            " content, tags, category, meta, added_ts, updated_ts)"
            " VALUES (?, ?, ?, ?, ?, ?, '[]', '', ?, ?, ?)",
            (nid, title, url or "", domain, summary or "", content or "",
             json.dumps({"chars": len(content or "")}), added_ts or now, now))
    target.commit()
    target.close()
    old_path.rename(old_path.with_suffix(".db.bak"))


def _now() -> float:
    import time
    return time.time()
