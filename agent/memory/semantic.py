"""语义记忆(§9.11):事实三元组,可关联图谱节点(与 graph 联动)。"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    subject  TEXT NOT NULL,
    relation TEXT NOT NULL,
    object   TEXT NOT NULL,
    source   TEXT NOT NULL DEFAULT '',
    node_id  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
"""


class SemanticMemory:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(
        self,
        subject: str,
        relation: str,
        obj: str,
        *,
        source: str = "",
        node_id: str = "",
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO facts (ts, subject, relation, object, source, node_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), subject, relation, obj, source, node_id),
            )
            self._conn.commit()
        return int(cur.lastrowid)

    def query(
        self,
        *,
        subject: str | None = None,
        relation: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = "SELECT id, ts, subject, relation, object, source, node_id FROM facts"
        conds, params = [], []
        if subject:
            conds.append("subject = ?")
            params.append(subject)
        if relation:
            conds.append("relation = ?")
            params.append(relation)
        if keyword:
            # %/_ 按 ESCAPE 规则转义为字面量
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conds.append("(subject LIKE ? ESCAPE '\\' OR object LIKE ? ESCAPE '\\')")
            params.extend([pattern, pattern])
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [
            dict(zip(("id", "ts", "subject", "relation", "object", "source", "node_id"), r))
            for r in self._conn.execute(sql, params).fetchall()
        ]

    def purge(self, older_than_days: int) -> int:
        """保留策略(§9.11):清理超期事实,返回删除条数。"""
        cutoff = time.time() - older_than_days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM facts WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount

    def clear(self) -> int:
        """清空全部事实三元组(§10.11 设置页清空动作),返回删除条数。"""
        with self._lock:
            cur = self._conn.execute("DELETE FROM facts")
            self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
