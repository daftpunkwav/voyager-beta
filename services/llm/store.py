"""llm 服务数据访问(独立命名空间):提供商元数据 + 用量流水。

secret 边界(§8.8):本库**永不存 api key**——key 在 platform/secrets,
本表只记 has_key 之外的全部元数据。usage 表承接旧 llm_usage_service 的
计量职责(修订:不再是日志解析,而是调用点直写)。
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
CREATE TABLE IF NOT EXISTS providers (
    id           TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    preset_id    TEXT NOT NULL DEFAULT '',
    base_url     TEXT NOT NULL,
    api_format   TEXT NOT NULL,
    models       TEXT NOT NULL DEFAULT '[]',
    default_model TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    custom       INTEGER NOT NULL DEFAULT 0,
    created_ts   REAL NOT NULL,
    updated_ts   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL NOT NULL,
    provider_id   TEXT NOT NULL,
    model         TEXT NOT NULL,
    caller        TEXT NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    ok            INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
"""

_COLS = ("id", "display_name", "preset_id", "base_url", "api_format",
         "models", "default_model", "enabled", "custom", "created_ts", "updated_ts")


class ProviderStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def upsert(self, p: dict[str, Any]) -> str:
        pid = p.get("id") or uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO providers (id, display_name, preset_id, base_url, api_format,"
                " models, default_model, enabled, custom, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,"
                " base_url=excluded.base_url, api_format=excluded.api_format,"
                " models=excluded.models, default_model=excluded.default_model,"
                " enabled=excluded.enabled, updated_ts=excluded.updated_ts",
                (
                    pid, p["display_name"], p.get("preset_id", ""), p["base_url"],
                    p["api_format"], json.dumps(p.get("models", []), ensure_ascii=False),
                    p.get("default_model", ""), int(p.get("enabled", True)),
                    int(p.get("custom", False)), now, now,
                ),
            )
            self._conn.commit()
        return pid

    def get(self, pid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT {','.join(_COLS)} FROM providers WHERE id = ?", (pid,)
        ).fetchone()
        return _row(row) if row else None

    def list(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(_COLS)} FROM providers"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        return [_row(r) for r in self._conn.execute(sql + " ORDER BY created_ts")]

    def delete(self, pid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM providers WHERE id = ?", (pid,))
            self._conn.commit()

    def record_usage(
        self, provider_id: str, model: str, input_tokens: int, output_tokens: int,
        *, caller: str = "", ok: bool = True,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (ts, provider_id, model, caller, input_tokens,"
                " output_tokens, ok) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), provider_id, model, caller, input_tokens, output_tokens,
                 int(ok)),
            )
            self._conn.commit()

    def usage_stats(self, days: int = 30) -> dict[str, Any]:
        cutoff = time.time() - days * 86400
        total = self._conn.execute(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COUNT(*)"
            " FROM usage WHERE ts >= ?", (cutoff,),
        ).fetchone()
        by_model = [
            {"model": r[0], "input": r[1], "output": r[2], "calls": r[3]}
            for r in self._conn.execute(
                "SELECT model, SUM(input_tokens), SUM(output_tokens), COUNT(*)"
                " FROM usage WHERE ts >= ? GROUP BY model ORDER BY 4 DESC", (cutoff,),
            )
        ]
        return {
            "days": days,
            "input_tokens": int(total[0]),
            "output_tokens": int(total[1]),
            "calls": int(total[2]),
            "by_model": by_model,
        }

    def close(self) -> None:
        self._conn.close()


def _row(r: tuple) -> dict[str, Any]:
    d = dict(zip(_COLS, r))
    d["models"] = json.loads(d["models"])
    d["enabled"] = bool(d["enabled"])
    d["custom"] = bool(d["custom"])
    return d
