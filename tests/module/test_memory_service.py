"""记忆服务单元测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_profile_memory_roundtrip(client: AsyncClient, auth_headers: dict):
    get1 = await client.get("/api/v1/user/profile", headers=auth_headers)
    assert get1.status_code == 200

    patch = await client.patch(
        "/api/v1/user/profile",
        headers=auth_headers,
        json={
            "history_summary": "喜欢通过源码学习",
            "tech_proficiency": {"Python": 80, "React": 60},
            "memory_items": [
                {
                    "id": "m1",
                    "category": "preference",
                    "content": "偏好代码优先讲解",
                    "created_at": "2026-07-16T00:00:00Z",
                }
            ],
        },
    )
    assert patch.status_code == 200
    data = patch.json()["data"]
    assert data["history_summary"] == "喜欢通过源码学习"
    assert data["tech_proficiency"]["Python"] == 80
    assert len(data["memory_items"]) >= 1

    get2 = await client.get("/api/v1/user/profile", headers=auth_headers)
    assert get2.status_code == 200
    assert get2.json()["data"]["history_summary"] == "喜欢通过源码学习"
