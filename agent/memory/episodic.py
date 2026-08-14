"""情节记忆(§9.11):决策留痕——触发 → 观察 → 判定 → 调用 → 结果。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    run_id  TEXT NOT NULL DEFAULT '',
    kind    TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
CREATE INDEX IF NOT EXISTS idx_episodes_run ON episodes(run_id);
"""


class EpisodicMemory:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def log(
        self,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        *,
        run_id: str = "",
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO episodes (ts, run_id, kind, summary, detail) VALUES (?, ?, ?, ?, ?)",
                (time.time(), run_id, kind, summary, json.dumps(detail or {}, ensure_ascii=False)),
            )
            self._conn.commit()
        return int(cur.lastrowid)

    def recent(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, ts, run_id, kind, summary, detail FROM episodes"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [_row(r) for r in self._conn.execute(sql, params).fetchall()]

    def search(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, ts, run_id, kind, summary, detail FROM episodes"
            " WHERE summary LIKE ? OR detail LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        return [_row(r) for r in rows]

    def purge(self, older_than_days: int) -> int:
        """保留策略(§9.11/决策 §15):清理超期情节,返回清理条数。"""
        cutoff = time.time() - older_than_days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM episodes WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()


def _row(r: tuple) -> dict[str, Any]:
    return {
        "id": r[0],
        "ts": r[1],
        "run_id": r[2],
        "kind": r[3],
        "summary": r[4],
        "detail": json.loads(r[5]),
    }
