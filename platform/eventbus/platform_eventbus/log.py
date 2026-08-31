"""持久化事件日志:SQLite 追加表。seq 自增,即事件的全序。"""

from __future__ import annotations

import fnmatch
import json
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from platform_contracts import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    id       TEXT NOT NULL UNIQUE,
    type     TEXT NOT NULL,
    actor    TEXT NOT NULL,
    payload  TEXT NOT NULL,
    ts       REAL NOT NULL,
    trace_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts);
"""

#: fnmatch 通配符(与 Subscription.matches 同语义:fnmatchcase)
_GLOB_CHARS = frozenset("*?[")


def _like_prefix(pattern: str) -> str:
    """glob 模式的字面前缀(LIKE 收窄用):截到第一个通配符前并转义 LIKE 元字符。"""
    prefix = pattern
    for ch in _GLOB_CHARS:
        prefix = prefix.split(ch, 1)[0]
    return (
        prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    )


class EventLog:
    """追加写、按序读。线程安全(单连接 + 写锁);跨进程共享同一 db 文件。"""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        """供 CursorStore 等共用同一连接(框架内约定;外部读请用公开查询方法)。"""
        return self._conn

    def latest_seq(self) -> int:
        """当前最大 seq(空表为 0)。SSE 续传等场景的公开读口,替代直连 conn。"""
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
        return int(row[0])

    def append(self, event: Event) -> int:
        """追加事件,返回全序 seq。"""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (id, type, actor, payload, ts, trace_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.type,
                    json.dumps(event.actor.to_dict(), ensure_ascii=False),
                    json.dumps(event.payload, ensure_ascii=False),
                    event.ts,
                    event.trace_id,
                ),
            )
            self._conn.commit()
        return int(cur.lastrowid)

    def read_after(
        self,
        after_seq: int = 0,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[tuple[int, Event]]:
        """读 seq > after_seq 的事件(可选按类型过滤),按 seq 升序。

        类型项与订阅同语义(phase-15):精确类型走 SQL IN;含 glob 通配符的项
        先用前缀 LIKE 收窄候选(超大日志不全表扫),再 fnmatch 精筛——
        字面量 'task.*' 经 IN 补不到 task.progress,补读才能与直推一致。
        """
        sql = "SELECT seq, id, type, actor, payload, ts, trace_id FROM events WHERE seq > ?"
        params: list[object] = [after_seq]
        exact: list[str] = []
        globs: list[str] = []
        if types:
            for t in types:
                (globs if _GLOB_CHARS & set(t) else exact).append(t)
            conds: list[str] = []
            if exact:
                placeholders = ",".join("?" for _ in exact)
                conds.append(f"type IN ({placeholders})")
                params.extend(exact)
            if globs:
                likes = []
                for g in globs:
                    likes.append("type LIKE ? ESCAPE '\\'")
                    params.append(_like_prefix(g) + "%")
                conds.append("(" + " OR ".join(likes) + ")")
            sql += " AND (" + " OR ".join(conds) + ")"
        sql += " ORDER BY seq ASC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        if globs:
            # 精筛只为剔除 LIKE 前缀多吐的候选;exact 的 IN 命中必须原样保留
            exact_set = set(exact)
            rows = [
                r for r in rows
                if r[2] in exact_set
                or any(fnmatch.fnmatchcase(r[2], g) for g in globs)
            ]
        return [(int(r[0]), _row_to_event(r)) for r in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _row_to_event(row: tuple) -> Event:
    from platform_contracts import ActorRef

    return Event(
        id=row[1],
        type=row[2],
        actor=ActorRef.from_dict(json.loads(row[3])),
        payload=json.loads(row[4]),
        ts=float(row[5]),
        trace_id=row[6],
    )
