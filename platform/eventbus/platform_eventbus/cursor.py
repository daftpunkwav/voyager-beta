"""游标管理:订阅者的消费位置。重启从游标恢复,可重放任意区间(§7.2)。"""

from __future__ import annotations

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cursors (
    name     TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL
);
"""


class CursorStore:
    """订阅者游标表。与 EventLog 共用连接(同事务一致性)或独立 db 均可。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(_SCHEMA)

    def get(self, name: str) -> int:
        row = self._conn.execute(
            "SELECT last_seq FROM cursors WHERE name = ?", (name,)
        ).fetchone()
        return int(row[0]) if row else 0

    def set(self, name: str, last_seq: int) -> None:
        self._conn.execute(
            "INSERT INTO cursors (name, last_seq) VALUES (?, ?)"
            " ON CONFLICT(name) DO UPDATE SET last_seq = excluded.last_seq",
            (name, last_seq),
        )
        self._conn.commit()
