"""office 数据访问:文档与演示稿内容,独立命名空间。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    blocks     TEXT NOT NULL DEFAULT '[]',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docs_kind ON documents(kind);
"""

_COLS = ("id", "title", "kind", "blocks", "created_ts", "updated_ts")


class DocumentStore:
    """文档/演示稿统一表;kind='doc'/'slides' 区分子领域。"""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def create(self, title: str, kind: str, blocks: list[dict] | None = None) -> dict[str, Any]:
        did = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (id, title, kind, blocks, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (did, title, kind, json.dumps(blocks or [], ensure_ascii=False), now, now),
            )
            self._conn.commit()
        return self.get(did)

    def get(self, did: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT {','.join(_COLS)} FROM documents WHERE id=?", (did,)
        ).fetchone()
        return _row(_COLS, row) if row else None

    def update(self, did: str, *, title: str | None = None,
               blocks: list[dict] | None = None) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if blocks is not None:
            fields["blocks"] = json.dumps(blocks, ensure_ascii=False)
        if not fields:
            existing = self.get(did)
            if existing is None:
                raise KeyError(did)
            return existing
        sets = ", ".join(f"{k}=?" for k in fields)
        params = list(fields.values()) + [time.time(), did]
        with self._lock:
            self._conn.execute(
                f"UPDATE documents SET {sets}, updated_ts=? WHERE id=?", params
            )
            self._conn.commit()
        return self.get(did)

    def list(self, kind: str = "", limit: int = 100) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(_COLS)} FROM documents"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind=?"
            params.append(kind)
        sql += " ORDER BY updated_ts DESC LIMIT ?"
        params.append(limit)
        return [_row(_COLS, r) for r in self._conn.execute(sql, params)]

    def delete(self, did: str) -> bool:
        with self._lock:
            n = self._conn.execute("DELETE FROM documents WHERE id=?", (did,)).rowcount
            self._conn.commit()
        return n > 0

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["blocks"] = json.loads(d.get("blocks") or "[]")
    return d
