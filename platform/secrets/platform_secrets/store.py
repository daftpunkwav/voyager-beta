"""密钥存储(§7.7):Fernet 加密落盘;读取只回明文给进程内调用方。

修订自旧 py_shared/security/crypto.py(保持加密格式兼容:同一密钥材料下,
旧库加密的值在新库可读):
- 存储从 api_backend settings_json 里的密文字段,独立为 secrets 命名空间表;
- 只存密文;`get` 返回 `None` 而非抛错,便于"未配置"语义;
- 密钥材料不进库、不进日志。
"""

from __future__ import annotations

import base64
import hashlib
import sqlite3
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from platform_secrets.key_material import load_key_material

_SCHEMA = """
CREATE TABLE IF NOT EXISTS secrets (
    key        TEXT PRIMARY KEY,
    ciphertext TEXT NOT NULL,
    updated_ts REAL NOT NULL DEFAULT (strftime('%s','now'))
);
"""


def _fernet_for(material: str) -> Fernet:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class SecretUnavailableError(RuntimeError):
    """未配置密钥材料:secret 功能不可用(BYOK 下应给出引导文案)。"""


class SecretStore:
    def __init__(self, db_path: str | Path, *, key_material: str | None = None) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._material = key_material if key_material is not None else load_key_material()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self._material)

    def _fernet(self) -> Fernet:
        if not self._material:
            raise SecretUnavailableError(
                "未配置密钥材料:请设置 SECRETS_ENCRYPTION_KEY(或 SECRET_KEY)"
            )
        return _fernet_for(self._material)

    def set(self, key: str, plain: str) -> None:
        ciphertext = self._fernet().encrypt(plain.encode("utf-8")).decode("ascii")
        with self._lock:
            self._conn.execute(
                "INSERT INTO secrets (key, ciphertext, updated_ts)"
                " VALUES (?, ?, strftime('%s','now'))"
                " ON CONFLICT(key) DO UPDATE SET ciphertext=excluded.ciphertext,"
                " updated_ts=excluded.updated_ts",
                (key, ciphertext),
            )
            self._conn.commit()

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT ciphertext FROM secrets WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        try:
            return self._fernet().decrypt(row[0].encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None  # 密钥材料已轮换:视为未配置,由用户重填

    def has(self, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM secrets WHERE key = ?", (key,)
        ).fetchone()
        return row is not None

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM secrets WHERE key = ?", (key,))
            self._conn.commit()

    def keys(self) -> list[str]:
        """只列键名,永不回值(审计/设置页 has_value 用)。"""
        return [
            r[0] for r in self._conn.execute("SELECT key FROM secrets ORDER BY key")
        ]

    def close(self) -> None:
        self._conn.close()
