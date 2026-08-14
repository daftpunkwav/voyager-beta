"""用户画像与偏好(§9.11):key-value,render() 供上下文装配的画像摘要。"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ProfileMemory:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO profile (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM profile WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else default

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM profile WHERE key = ?", (key,))
            self._conn.commit()

    def all(self) -> dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM profile ORDER BY key").fetchall()
        return {k: json.loads(v) for k, v in rows}

    def render(self, max_chars: int = 800) -> str:
        """画像摘要(注入 system 的是摘要而非全量,§9.20)。"""
        data = self.all()
        if not data:
            return "(暂无用户画像)"
        text = "\n".join(f"- {k}: {v}" for k, v in data.items())
        return text if len(text) <= max_chars else text[:max_chars] + "…"

    def close(self) -> None:
        self._conn.close()
