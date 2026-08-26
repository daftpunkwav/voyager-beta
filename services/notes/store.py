"""notes 服务数据访问(§8.3):仅 Markdown;列表默认摘要,正文按需(§9.20)。

笔记可关联资源(source_id)与图谱节点(node_id);link_note 建立关联。
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
CREATE TABLE IF NOT EXISTS notes (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tags       TEXT NOT NULL DEFAULT '[]',
    source_id  TEXT NOT NULL DEFAULT '',
    node_id    TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_source ON notes(source_id);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_ts);
"""

_SUMMARY_COLS = ("id", "title", "tags", "source_id", "node_id",
                 "created_ts", "updated_ts", "excerpt")
_ALL_COLS = ("id", "title", "content", "tags", "source_id", "node_id",
             "created_ts", "updated_ts")

_EXCERPT_LEN = 120
_SORTABLE = {"updated_ts", "created_ts", "title"}


class NoteStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def create(self, note: dict[str, Any]) -> str:
        nid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO notes (id, title, content, tags, source_id, node_id,"
                " created_ts, updated_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (nid, note["title"], note.get("content", ""),
                 json.dumps(note.get("tags", []), ensure_ascii=False),
                 note.get("source_id", ""), note.get("node_id", ""), now, now),
            )
            self._conn.commit()
        return nid

    def get(self, nid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT {','.join(_ALL_COLS)} FROM notes WHERE id = ?", (nid,)
        ).fetchone()
        return _row(_ALL_COLS, row) if row else None

    def list(self, *, source_id: str | None = None, tag: str = "",
             limit: int = 100, order: str = "updated_ts") -> list[dict[str, Any]]:
        """摘要列表:正文截为 excerpt,不回全量(§9.20);排序列走白名单。"""
        col = order if order in _SORTABLE else "updated_ts"
        sql = ("SELECT id, title, tags, source_id, node_id, created_ts, updated_ts,"
               f" substr(content, 1, {_EXCERPT_LEN}) AS excerpt FROM notes")
        conds, params = [], []
        if source_id is not None:
            conds.append("source_id = ?")
            params.append(source_id)
        if tag:
            conds.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        # title 语义上取升序,时间列取倒序
        direction = "ASC" if col == "title" else "DESC"
        sql += f" ORDER BY {col} {direction} LIMIT ?"
        params.append(limit)
        return [_row(_SUMMARY_COLS, r) for r in self._conn.execute(sql, params)]

    def update(self, nid: str, **fields: Any) -> None:
        allowed = {"title", "content", "tags", "source_id", "node_id"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        sets, params = [], []
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
        params += [time.time(), nid]
        with self._lock:
            self._conn.execute(
                f"UPDATE notes SET {', '.join(sets)}, updated_ts = ? WHERE id = ?", params,
            )
            self._conn.commit()

    def delete(self, nid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d
