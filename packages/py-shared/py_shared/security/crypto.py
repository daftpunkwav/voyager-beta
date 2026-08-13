"""共享安全工具 —— 敏感字段 at-rest 加密（Fernet）

参数化版本：key_material 由调用方注入（api_backend 注入 get_settings().secret_key），
避免 shared 层反向依赖业务配置。
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

# 落库密文前缀；无此前缀视为历史明文（兼容旧数据）
_SECRET_PREFIX = "enc:v1:"


@lru_cache(maxsize=8)
def _fernet_for(material: str) -> Fernet:
    """由密钥材料派生 Fernet 密钥（SHA-256 → urlsafe base64）。"""
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted_secret(value: str | None) -> bool:
    """判断存储值是否为加密密文（仅前缀判断，与密钥无关）。"""
    if not value:
        return False
    return value.startswith(_SECRET_PREFIX)


def encrypt_secret(plain: str, key_material: str) -> str:
    """加密敏感字符串以便落库；空串原样返回。"""
    if not plain:
        return plain
    token = _fernet_for(key_material).encrypt(plain.encode("utf-8")).decode("ascii")
    return f"{_SECRET_PREFIX}{token}"


def decrypt_secret(value: str | None, key_material: str) -> str | None:
    """解密落库敏感字段；兼容历史明文与解密失败时返回 None。"""
    if value is None:
        return None
    if not value:
        return value
    if not value.startswith(_SECRET_PREFIX):
        return value  # 历史明文
    cipher = value[len(_SECRET_PREFIX) :]
    try:
        return _fernet_for(key_material).decrypt(cipher.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def ensure_encrypted_secret(
    value: str | None, key_material: str
) -> tuple[str | None, bool]:
    """若为历史明文则加密；返回 (存储值, 是否发生了迁移)。"""
    if value is None or value == "":
        return value, False
    if is_encrypted_secret(value):
        return value, False
    return encrypt_secret(value, key_material), True
