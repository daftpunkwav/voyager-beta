"""依赖注入集成测试 —— 本地单机无认证。"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_me_without_auth_returns_local_user(client: AsyncClient):
    """无 Authorization 亦可访问 /user/me，返回本机身份。"""
    res = await client.get("/api/v1/user/me")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["username"] == "local"
    assert data["id"] == "local"


@pytest.mark.asyncio
async def test_user_me_is_singleton(client: AsyncClient):
    """多次请求返回同一本机身份。"""
    a = await client.get("/api/v1/user/me")
    b = await client.get("/api/v1/user/me")
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json()["data"]["id"] == b.json()["data"]["id"]
