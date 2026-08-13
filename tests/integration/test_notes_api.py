"""笔记 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.fixture
async def note_project_id(client: AsyncClient, auth_headers: dict) -> str:
    """创建一个用于笔记测试的项目并返回其 ID。"""
    project = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "n/p", "url": "https://github.com/n/p"},
    )
    assert project.status_code == 200
    return project.json()["data"]["id"]


@pytest.mark.asyncio
async def test_notes_flow(client: AsyncClient, auth_headers: dict, note_project_id: str):
    pid = note_project_id

    create = await client.post(
        f"/api/v1/notes/projects/{pid}/notes",
        headers=auth_headers,
        json={"title": "笔记1", "content": "hello"},
    )
    assert create.status_code == 200
    note_id = create.json()["data"]["id"]

    listed = await client.get(
        f"/api/v1/notes/projects/{pid}/notes", headers=auth_headers
    )
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    all_notes = await client.get("/api/v1/notes/", headers=auth_headers)
    assert all_notes.status_code == 200
    assert len(all_notes.json()["data"]) >= 1

    updated = await client.put(
        f"/api/v1/notes/{note_id}",
        headers=auth_headers,
        json={"title": "更新"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "更新"


@pytest.mark.asyncio
async def test_create_note_empty_title_returns_422(
    client: AsyncClient, auth_headers: dict, note_project_id: str
):
    res = await client.post(
        f"/api/v1/notes/projects/{note_project_id}/notes",
        headers=auth_headers,
        json={"title": "", "content": "hello"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_note_content_too_long_returns_422(
    client: AsyncClient, auth_headers: dict, note_project_id: str
):
    res = await client.post(
        f"/api/v1/notes/projects/{note_project_id}/notes",
        headers=auth_headers,
        json={"title": "t", "content": "x" * 100_001},
    )
    assert res.status_code == 422
