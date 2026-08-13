"""分类 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_preset_categories(client: AsyncClient, auth_headers: dict):
    res = await client.get("/api/v1/categories/", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["data"]
    assert len(items) >= 5
    assert any(c["name"] == "前端" for c in items)


@pytest.mark.asyncio
async def test_create_custom_category(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/categories/",
        headers=auth_headers,
        json={"name": "自定义"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "自定义"


@pytest.mark.asyncio
async def test_create_category_empty_name_returns_422(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/categories/",
        headers=auth_headers,
        json={"name": ""},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_category_name_too_long_returns_422(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/categories/",
        headers=auth_headers,
        json={"name": "x" * 65},
    )
    assert res.status_code == 422
