"""本领域数据访问(独立命名空间)。示例:任务表。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    result     TEXT,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
"""


class JobStore:
    """任务存取。各服务的 store 只操作自己的表,命名空间互不交叉(§13.2)。"""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def enqueue(self, job_id: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, status, result, created_ts, updated_ts)"
                " VALUES (?, 'queued', NULL, ?, ?)",
                (job_id, now, now),
            )
            self._conn.commit()

    def set_status(self, job_id: str, status: str, result: Any = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status = ?, result = ?, updated_ts = ? WHERE id = ?",
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    time.time(),
                    job_id,
                ),
            )
            self._conn.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, status, result, created_ts, updated_ts FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "status": row[1],
            "result": json.loads(row[2]) if row[2] else None,
            "created_ts": row[3],
            "updated_ts": row[4],
        }

    def close(self) -> None:
        self._conn.close()
