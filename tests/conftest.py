"""
全局 pytest 配置与 fixtures
"""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

# 确保 api_backend / agent_core / graph_engine_runtime / py_shared 均可导入（兼容不同 pytest rootdir）
_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _REPO_ROOT / "services" / "api",
    _REPO_ROOT / "services" / "agent",
    _REPO_ROOT / "services" / "graph_engine",
    _REPO_ROOT / "packages" / "py-shared",
):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

import pytest
from httpx import ASGITransport, AsyncClient

# 必须在导入 api_backend 之前设置；长度不少于 32 字节，满足启动校验
os.environ.setdefault("SECRET_KEY", "pytest-secret-key-do-not-use-in-prod")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# 注入 agent_core 业务服务契约(与 api_backend.main lifespan 一致；agent_core 只依赖 Protocol)
from agent_core import services as _agent_services  # noqa: E402
from api_backend.services.agent_services_bridge import build_agent_services  # noqa: E402

_agent_services.register_agent_services(build_agent_services())


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[AsyncClient]:
    """每个测试用例使用独立 SQLite 文件。"""
    from api_backend.config import get_settings
    from api_backend.database import get_session_factory, init_db, reset_database

    db_path = tmp_path / "pytest.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()
    reset_database()

    from api_backend.main import app
    from api_backend.services.app_state_service import ensure_singleton_rows
    from api_backend.services.seed_service import seed_preset_categories

    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await seed_preset_categories(session)
        await ensure_singleton_rows(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """本地单机无认证；保留 fixture 名以兼容既有测试。

    预热 /user/me，确保 AppState 单行可用。
    """
    res = await client.get("/api/v1/user/me")
    assert res.status_code == 200, res.text
    return {}
