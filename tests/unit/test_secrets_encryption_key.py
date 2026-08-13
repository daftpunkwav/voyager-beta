"""SECRETS_ENCRYPTION_KEY 与 JWT SECRET_KEY 分离测试"""
import os

import pytest
from api_backend.config import get_settings
from api_backend.core.security import decrypt_secret, encrypt_secret
from py_shared.security import crypto as shared_crypto


@pytest.fixture(autouse=True)
def _clear_caches():
    get_settings.cache_clear()
    shared_crypto._fernet_for.cache_clear()
    yield
    get_settings.cache_clear()
    shared_crypto._fernet_for.cache_clear()


def test_encrypt_uses_secrets_encryption_key_when_set(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "jwt-secret-key-at-least-32-bytes-long!!")
    monkeypatch.setenv(
        "SECRETS_ENCRYPTION_KEY", "dedicated-encryption-key-32bytes-min!"
    )
    get_settings.cache_clear()
    shared_crypto._fernet_for.cache_clear()

    cipher = encrypt_secret("sk-secret-value")
    assert cipher.startswith("enc:v1:")
    assert decrypt_secret(cipher) == "sk-secret-value"

    # 仅用 JWT 密钥无法解密（模拟泄露 JWT 但未泄露加密密钥）
    jwt_only = shared_crypto._fernet_for(
        "jwt-secret-key-at-least-32-bytes-long!!"
    )
    with pytest.raises(Exception):
        jwt_only.decrypt(cipher[len("enc:v1:") :].encode("ascii"))


def test_encrypt_falls_back_to_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "jwt-secret-key-at-least-32-bytes-long!!")
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
    # pydantic 可能已缓存；确保无自定义加密密钥
    os.environ.pop("SECRETS_ENCRYPTION_KEY", None)
    get_settings.cache_clear()
    shared_crypto._fernet_for.cache_clear()

    cfg = get_settings()
    assert not (cfg.secrets_encryption_key or "").strip()
    cipher = encrypt_secret("pat-token")
    assert decrypt_secret(cipher) == "pat-token"
