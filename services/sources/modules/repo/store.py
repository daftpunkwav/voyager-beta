"""repo 子模块数据访问(修订自旧 Project 模型,§8.2)。

修订点:category 由外键表简化为字符串字段(list_categories 取 distinct),
tags 由 m2m 简化为 json 数组;readme 导入时缓存,不再每次请求回源;
status 承载导入生命周期(importing/ready/failed)。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id          TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    stars       INTEGER NOT NULL DEFAULT 0,
    language    TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    progress    TEXT NOT NULL DEFAULT 'none',
    note        TEXT NOT NULL DEFAULT '',
    local_path  TEXT NOT NULL DEFAULT '',
    readme      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'importing',
    error       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',
    added_ts    REAL NOT NULL,
    updated_ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repos_status ON repos(status);
"""

_COLS = ("id", "owner", "name", "url", "description", "stars", "language",
         "category", "tags", "progress", "note", "local_path", "readme",
         "status", "error", "source", "added_ts", "updated_ts")

#: 列表默认只回摘要(§9.20);readme 正文经 get_readme 按需取
_SUMMARY_COLS = tuple(c for c in _COLS if c != "readme")

_SORTABLE = {"name": "name", "stars": "stars", "added": "added_ts", "updated": "updated_ts"}


class RepoStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, repo: dict[str, Any]) -> str:
        rid = repo.get("id") or uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO repos (id, owner, name, url, description, stars,"
                " language, category, tags, progress, note, local_path, readme, status,"
                " error, source, added_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rid, repo.get("owner", ""), repo["name"], repo["url"],
                    repo.get("description", ""), int(repo.get("stars", 0)),
                    repo.get("language", ""), repo.get("category", ""),
                    json.dumps(repo.get("tags", []), ensure_ascii=False),
                    repo.get("progress", "none"), repo.get("note", ""),
                    repo.get("local_path", ""), repo.get("readme", ""),
                    repo.get("status", "importing"), repo.get("error", ""),
                    repo.get("source", "manual"), now, now,
                ),
            )
            self._conn.commit()
        return rid

    def _fetch(self, where: str = "", params: tuple = (), cols=_SUMMARY_COLS,
               order: str = "added_ts DESC") -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(cols)} FROM repos"
        if where:
            sql += f" WHERE {where}"
        rows = self._conn.execute(f"{sql} ORDER BY {order}", params).fetchall()
        return [_row(cols, r) for r in rows]

    def get(self, rid: str, *, with_readme: bool = True) -> dict[str, Any] | None:
        cols = _COLS if with_readme else _SUMMARY_COLS
        rows = self._fetch("id = ?", (rid,), cols=cols)
        return rows[0] if rows else None

    def get_by_url(self, url: str) -> dict[str, Any] | None:
        rows = self._fetch("url = ?", (url,))
        return rows[0] if rows else None

    def list(self, *, sort: str = "added", desc: bool = True,
             category: str = "") -> list[dict[str, Any]]:
        col = _SORTABLE.get(sort, "added_ts")
        where, params = ("category = ?", (category,)) if category else ("", ())
        return self._fetch(where, params, order=f"{col} {'DESC' if desc else 'ASC'}")

    def categories(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT category FROM repos WHERE category != '' ORDER BY category"
        ).fetchall()
        return [r[0] for r in rows]

    def set_meta(self, rid: str, **fields: Any) -> None:
        allowed = {"category", "tags", "progress", "note"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        sets, params = [], []
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
        params += [time.time(), rid]
        with self._lock:
            self._conn.execute(
                f"UPDATE repos SET {', '.join(sets)}, updated_ts = ? WHERE id = ?", params,
            )
            self._conn.commit()

    def set_status(self, rid: str, status: str, *, local_path: str = "",
                   error: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE repos SET status = ?, local_path = COALESCE(NULLIF(?, ''),"
                " local_path), error = ?, updated_ts = ? WHERE id = ?",
                (status, local_path, error, time.time(), rid),
            )
            self._conn.commit()

    def remove(self, rid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM repos WHERE id = ?", (rid,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d
