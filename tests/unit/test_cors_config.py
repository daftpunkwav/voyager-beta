"""CORS 配置单元测试"""
from api_backend.config import Settings


def test_cors_origins_list_default_contains_dev_ports():
    s = Settings(secret_key="x" * 32)
    origins = s.cors_origins_list()
    assert "http://localhost:5173" in origins
    assert "http://localhost:5174" in origins
    assert "http://localhost:5175" in origins
    assert "http://localhost:4173" in origins
    assert "http://127.0.0.1:5173" in origins


def test_cors_origins_list_from_env_string():
    s = Settings(
        secret_key="x" * 32,
        cors_allow_origins="https://app.example.com, https://admin.example.com",
    )
    assert s.cors_origins_list() == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_cors_origins_list_ignores_empty_segments():
    s = Settings(secret_key="x" * 32, cors_allow_origins="https://a.com,, ,https://b.com")
    assert s.cors_origins_list() == ["https://a.com", "https://b.com"]
