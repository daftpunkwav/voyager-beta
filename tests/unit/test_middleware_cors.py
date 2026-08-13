"""middleware CORS 与配置一致性测试"""
from api_backend.config import Settings, get_settings
from api_backend.core.middleware import cors_allow_origins, setup_middleware
from fastapi import FastAPI


def test_cors_allow_origins_matches_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS", "https://app.example.com,https://admin.example.com"
    )
    get_settings.cache_clear()
    assert cors_allow_origins() == [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    get_settings.cache_clear()


def test_setup_middleware_uses_env_origins(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://only.example.com")
    get_settings.cache_clear()

    app = FastAPI()
    setup_middleware(app)
    # Starlette 将 CORSMiddleware 放在 user_middleware
    assert any(
        getattr(m, "cls", None).__name__ == "CORSMiddleware"
        or (
            hasattr(m, "cls")
            and m.cls.__name__ == "CORSMiddleware"
        )
        for m in app.user_middleware
    )
    # 校验 kwargs 中的 origins
    cors_m = next(
        m
        for m in app.user_middleware
        if getattr(m.cls, "__name__", "") == "CORSMiddleware"
    )
    assert cors_m.kwargs.get("allow_origins") == ["https://only.example.com"]
    get_settings.cache_clear()


def test_main_cors_origins_helper_default():
    """默认开发端口列表非空。"""
    s = Settings(secret_key="x" * 32)
    assert "http://localhost:5173" in s.cors_origins_list()
