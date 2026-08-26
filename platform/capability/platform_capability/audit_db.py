"""审计落库(§7.6):SQLite 持久 AuditSink。

guards.InMemoryAuditSink 是开发/测试占位;生产装配根(deploy/)默认接入本
sink——进程重启审计不丢,可按 trace_id/时间/能力名回查。写入走同步 sqlite
(单条 insert,微秒级),不拖慢能力调用路径。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from platform_capability.guards import AuditEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    actor_id     TEXT NOT NULL,
    actor_kind   TEXT NOT NULL,
    capability   TEXT NOT NULL,
    args_summary TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    error_code   TEXT NOT NULL DEFAULT '',
    trace_id     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_capability ON audit(capability);
"""

_COLS = ("id", "ts", "actor_id", "actor_kind", "capability",
         "args_summary", "ok", "error_code", "trace_id")


class SqliteAuditSink:
    """审计入库:守卫链无论成败都会 record;单连接 + 锁串行写。"""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def record(self, entry: AuditEntry) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit (ts, actor_id, actor_kind, capability,"
                " args_summary, ok, error_code, trace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entry.ts, entry.actor_id, entry.actor_kind, entry.capability,
                 entry.args_summary, int(entry.ok), entry.error_code, entry.trace_id),
            )
            self._conn.commit()

    def recent(self, *, limit: int = 100, capability: str = "",
               trace_id: str = "", ok: bool | None = None) -> list[dict[str, Any]]:
        """审计回查(调试/活动页用):按时间倒序,可按能力/trace/成败过滤。"""
        sql = f"SELECT {','.join(_COLS)} FROM audit"
        conds: list[str] = []
        params: list[Any] = []
        if capability:
            conds.append("capability = ?")
            params.append(capability)
        if trace_id:
            conds.append("trace_id = ?")
            params.append(trace_id)
        if ok is not None:
            conds.append("ok = ?")
            params.append(int(ok))
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        out = [dict(zip(_COLS, r)) for r in rows]
        for item in out:
            item["ok"] = bool(item["ok"])
        return out

    def close(self) -> None:
        self._conn.close()
