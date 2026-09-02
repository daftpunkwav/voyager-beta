"""Meter token 用量持久化(phase-66,§9.9 资源维):当日累计落 sqlite。

按 (UTC 自然日, kind) 累加 token 合计,库文件 meter.db 与 events.db 同级;
日配额 / get_resource_quota / proactive 预检经 Meter 读同一份持久化源,
进程重启后当日累计不清零。只记合计不做逐条流水(配额只依赖当日总和,
审计流水如需另开阶段),且被配额拒绝的伪调用不落库(与内存口径一致)。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meter_tokens (
    day_utc       TEXT NOT NULL,   -- 'YYYY-MM-DD' UTC 自然日
    kind          TEXT NOT NULL,   -- 本刀只写 'llm';tool 不落库
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day_utc, kind)
);
"""


def _utc_day(ts: float) -> str:
    """epoch 秒 → 'YYYY-MM-DD'(UTC 切日,与 Meter.tokens_used_today 同口径)。"""
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


class MeterStore:
    """当日 token 合计的持久化句柄;线程锁 + check_same_thread=False 同 episodic。"""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(
        self, kind: str, input_tokens: int, output_tokens: int, *, ts: float | None = None
    ) -> None:
        """按 ts 所在 UTC 日累加;ts 不传取真实时钟(与 MeterRecord 默认同源)。"""
        day = _utc_day(time.time() if ts is None else ts)
        with self._lock:
            self._conn.execute(
                "INSERT INTO meter_tokens (day_utc, kind, input_tokens, output_tokens)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(day_utc, kind) DO UPDATE SET"
                " input_tokens = input_tokens + excluded.input_tokens,"
                " output_tokens = output_tokens + excluded.output_tokens",
                (day, kind, int(input_tokens), int(output_tokens)),
            )
            self._conn.commit()

    def tokens_used_today(self, *, now: float | None = None, kind: str = "llm") -> int:
        """当日 input+output 合计(默认只看 llm 行),与内存聚合语义一致。"""
        day = _utc_day(time.time() if now is None else now)
        with self._lock:
            row = self._conn.execute(
                "SELECT input_tokens, output_tokens FROM meter_tokens"
                " WHERE day_utc = ? AND kind = ?",
                (day, kind),
            ).fetchone()
        return (row[0] + row[1]) if row else 0

    def purge_older_than_days(self, days: int, *, now: float | None = None) -> int:
        """删除 today_utc - days 之前的日行(严格小于),返回删除行数。

        启动库维护(phase-68,§9.9):防 meter_tokens 随日期无限累积;
        切日与 tokens_used_today 同口径(time.gmtime,UTC 自然日)。
        """
        base = time.time() if now is None else now
        cutoff = time.strftime("%Y-%m-%d", time.gmtime(base - days * 86400))
        with self._lock:
            cur = self._conn.execute("DELETE FROM meter_tokens WHERE day_utc < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        self._conn.close()
