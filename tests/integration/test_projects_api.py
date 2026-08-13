"""项目 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_project_crud(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={
            "name": "foo/bar",
            "url": "https://github.com/foo/bar",
            "language": "TypeScript",
        },
    )
    assert create.status_code == 200
    project = create.json()["data"]
    pid = project["id"]
    assert project["name"] == "foo/bar"

    listing = await client.get("/api/v1/projects/", headers=auth_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["data"]["total"] >= 1
    assert len(body["data"]["items"]) >= 1

    got = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert got.status_code == 200

    prog = await client.put(
        f"/api/v1/projects/{pid}/progress",
        headers=auth_headers,
        params={"progress": "learning"},
    )
    assert prog.status_code == 200
    assert prog.json()["data"]["progress"] == "learning"

    bad_prog = await client.put(
        f"/api/v1/projects/{pid}/progress",
        headers=auth_headers,
        params={"progress": "not-a-valid-status"},
    )
    assert bad_prog.status_code == 422

    delete = await client.delete(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert delete.status_code == 200


@pytest.mark.asyncio
async def test_import_projects(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/projects/import",
        headers=auth_headers,
        json={
            "repos": [
                {"owner": "a", "repo": "b", "url": "https://github.com/a/b"},
            ]
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["succeeded"] == 1


@pytest.mark.asyncio
async def test_project_stats(client: AsyncClient, auth_headers: dict):
    res = await client.get("/api/v1/projects/stats", headers=auth_headers)
    assert res.status_code == 200
    assert "total" in res.json()["data"]


@pytest.mark.asyncio
async def test_project_readme_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch):
    """README 按需拉取：mock GitHub 客户端，验证解析与返回结构。"""
    create = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={
            "name": "octocat/Hello-World",
            "url": "https://github.com/octocat/Hello-World",
        },
    )
    assert create.status_code == 200
    pid = create.json()["data"]["id"]

    async def fake_readme(owner: str, repo: str, token: str | None = None):
        assert owner == "octocat"
        assert repo == "Hello-World"
        return "# Hello\n\nWorld"

    monkeypatch.setattr(
        "api_backend.api.projects.fetch_readme_text",
        fake_readme,
    )

    res = await client.get(f"/api/v1/projects/{pid}/readme", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["source"] == "github"
    assert data["content"].startswith("# Hello")
    assert data["owner"] == "octocat"
    assert data["repo"] == "Hello-World"

    # 空 README
    async def empty_readme(*_a, **_k):
        return None

    monkeypatch.setattr("api_backend.api.projects.fetch_readme_text", empty_readme)
    res2 = await client.get(f"/api/v1/projects/{pid}/readme", headers=auth_headers)
    assert res2.status_code == 200
    assert res2.json()["data"]["source"] == "empty"


@pytest.mark.asyncio
async def test_create_project_name_too_long_returns_422(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "x" * 129, "url": "https://github.com/x/y"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_project_description_too_long_returns_422(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={
            "name": "x/y",
            "url": "https://github.com/x/y",
            "description": "x" * 2049,
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_import_projects_rejects_non_github_url(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/projects/import",
        headers=auth_headers,
        json={"repos": [{"owner": "a", "repo": "b", "url": "https://example.com/a/b"}]},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_import_projects_rejects_http_url(client: AsyncClient, auth_headers: dict):
    res = await client.post(
        "/api/v1/projects/import",
        headers=auth_headers,
        json={"repos": [{"owner": "a", "repo": "b", "url": "http://github.com/a/b"}]},
    )
    assert res.status_code == 422
