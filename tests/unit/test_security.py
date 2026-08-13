"""安全工具单元测试 —— at-rest 加密（已移除 JWT/密码哈希）。"""
from api_backend.core.security import decrypt_secret, encrypt_secret


def test_encrypt_decrypt_secret_roundtrip():
    plain = "sk-test-secret-key-value"
    cipher = encrypt_secret(plain)
    assert cipher != plain
    assert cipher.startswith("enc:v1:")
    assert decrypt_secret(cipher) == plain


def test_decrypt_secret_plaintext_compat():
    """历史明文应原样返回，保证迁移兼容。"""
    assert decrypt_secret("ghp_legacy_plain_token") == "ghp_legacy_plain_token"
    assert decrypt_secret(None) is None
    assert decrypt_secret("") == ""


def test_encrypt_empty_passthrough():
    assert encrypt_secret("") == ""
