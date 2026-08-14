"""设置项存取:SQLite 持久化 + 校验 + secret 写保护 + 变更事件(§7.9 / §8.8)。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus

from platform_settings.define import SettingDef, SettingType, validate

_DOMAIN = "settings"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS setting_values (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    ts         REAL NOT NULL
);
"""


class SettingsStore:
    """设置项存取。defs 由各服务在启动时注册(代码侧),values 持久化(数据侧)。"""

    def __init__(self, db_path: str | Path, bus: EventBus | None = None) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._bus = bus
        self._defs: dict[str, SettingDef] = {}

    def register(self, defs: Iterable[SettingDef]) -> None:
        for d in defs:
            if d.key in self._defs:
                raise ServiceError(
                    _DOMAIN, ErrorSuffix.CONFLICT, f"设置项重复注册: {d.key}"
                )
            self._defs[d.key] = d

    def _def(self, key: str) -> SettingDef:
        try:
            return self._defs[key]
        except KeyError:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.NOT_FOUND, f"未知设置项: {key}"
            ) from None

    def get(self, key: str) -> Any:
        """读当前值(未设置 → 默认值)。内部调用可读 secret 的真实值。"""
        d = self._def(key)
        row = self._conn.execute(
            "SELECT value FROM setting_values WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else d.default

    async def set(self, key: str, value: Any, actor: ActorRef) -> None:
        """写设置:校验 → secret 写保护(仅 user,§8.8)→ 落库 → 发变更事件。"""
        d = self._def(key)
        if d.secret and actor.kind is not ActorKind.USER:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                f"secret 设置项仅用户本人可写: {key}",
                hint="请在设置页手动填写",
            )
        value = validate(d, value)
        with self._lock:
            self._conn.execute(
                "INSERT INTO setting_values (key, value, updated_by, ts) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                " updated_by = excluded.updated_by, ts = excluded.ts",
                (key, json.dumps(value, ensure_ascii=False), actor.id, time.time()),
            )
            self._conn.commit()
        if self._bus is not None:
            payload: dict[str, Any] = {"key": key, "module": d.module, "secret": d.secret}
            if not d.secret:
                payload["value"] = value
            await self._bus.publish(
                Event(type=DomainEvent.SETTINGS_CHANGED, actor=actor, payload=payload)
            )

    def list_schema(self) -> list[dict[str, Any]]:
        """全部设置项 schema(设置页动态渲染用,§10.11)。secret 项不回值,只回 has_value。"""
        out: list[dict[str, Any]] = []
        for key in sorted(self._defs):
            d = self._defs[key]
            row = self._conn.execute(
                "SELECT value FROM setting_values WHERE key = ?", (key,)
            ).fetchone()
            item: dict[str, Any] = {
                "key": key,
                "module": d.module,
                "type": d.type.value,
                "description": d.description,
                "secret": d.secret,
                "choices": list(d.choices),
                "min": d.min,
                "max": d.max,
                "has_value": row is not None,
            }
            if not d.secret:
                item["default"] = d.default
                item["value"] = json.loads(row[0]) if row else d.default
            out.append(item)
        return out

    def close(self) -> None:
        self._conn.close()


__all__ = ["SettingDef", "SettingType", "SettingsStore", "validate"]
