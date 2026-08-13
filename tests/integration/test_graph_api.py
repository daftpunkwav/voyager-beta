"""图谱 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_graph_empty(client: AsyncClient, auth_headers: dict):
    res = await client.get("/api/v1/graph/", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["nodes"] == []
    assert data["edges"] == []


@pytest.mark.asyncio
async def test_graph_with_edges(client: AsyncClient, auth_headers: dict):
    """同语言 + 领域词重叠应产生 similarity 边，并带 foundation/hubness/cluster 字段。"""
    for name, lang, desc in [
        (
            "org/go-runtime",
            "Go",
            "Go language runtime and framework for cloud services",
        ),
        (
            "org/go-sdk",
            "Go",
            "Go language SDK and framework toolkit for cloud services",
        ),
    ]:
        await client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json={
                "name": name,
                "url": f"https://github.com/{name}",
                "language": lang,
                "description": desc,
            },
        )
    res = await client.get(
        "/api/v1/graph/", headers=auth_headers, params={"min_similarity": 0.2}
    )
    assert res.status_code == 200
    payload = res.json()["data"]
    assert len(payload["edges"]) >= 1
    assert len(payload["nodes"]) == 2
    for n in payload["nodes"]:
        assert "foundation_score" in n
        assert "hubness" in n
        assert "cluster_id" in n
        assert "cluster_size" in n
