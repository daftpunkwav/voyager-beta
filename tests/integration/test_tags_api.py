"""标签 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tags_crud_and_project_tags(client: AsyncClient, auth_headers: dict):
    tag = await client.post(
        "/api/v1/tags/",
        headers=auth_headers,
        json={"name": "react"},
    )
    assert tag.status_code == 200
    tag_id = tag.json()["data"]["id"]

    project = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "a/b", "url": "https://github.com/a/b"},
    )
    pid = project.json()["data"]["id"]

    linked = await client.put(
        f"/api/v1/tags/projects/{pid}",
        headers=auth_headers,
        json={"tag_ids": [tag_id]},
    )
    assert linked.status_code == 200

    got = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert tag_id in got.json()["data"]["tags"]


@pytest.mark.asyncio
async def test_create_tag_name_too_long_returns_422(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/tags/",
        headers=auth_headers,
        json={"name": "x" * 65},
    )
    assert res.status_code == 422
