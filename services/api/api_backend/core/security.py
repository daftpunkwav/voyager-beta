"""
安全工具 —— 敏感字段 at-rest 加密（Fernet）

本地单机已移除 JWT / 密码哈希；保留 encrypt/decrypt 供 GitHub PAT、LLM Key 使用。
权威实现已下沉到 py_shared.security.crypto（参数化 key_material），
此处为薄封装：注入 api_backend 配置的密钥材料。
"""
from api_backend.config import get_settings
from py_shared.security.crypto import (  # noqa: F401
    decrypt_secret as _shared_decrypt,
)
from py_shared.security.crypto import (  # noqa: F401
    encrypt_secret as _shared_encrypt,
)
from py_shared.security.crypto import (  # noqa: F401
    ensure_encrypted_secret as _shared_ensure,
)
from py_shared.security.crypto import is_encrypted_secret as _shared_is_enc


def _encryption_key_material() -> str:
    """优先 SECRETS_ENCRYPTION_KEY，否则回退 SECRET_KEY。"""
    cfg = get_settings()
    custom = (cfg.secrets_encryption_key or "").strip()
    if custom:
        return custom
    return cfg.secret_key


def is_encrypted_secret(value: str | None) -> bool:
    """判断存储值是否为加密密文（委托 shared 权威实现）。"""
    return _shared_is_enc(value)


def encrypt_secret(plain: str) -> str:
    """加密敏感字符串以便落库；空串原样返回。"""
    return _shared_encrypt(plain, _encryption_key_material())


def decrypt_secret(value: str | None) -> str | None:
    """解密落库敏感字段；兼容历史明文与解密失败时返回 None。"""
    return _shared_decrypt(value, _encryption_key_material())


def ensure_encrypted_secret(value: str | None) -> tuple[str | None, bool]:
    """若为历史明文则加密；返回 (存储值, 是否发生了迁移)。"""
    return _shared_ensure(value, _encryption_key_material())
