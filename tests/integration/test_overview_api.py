"""总览 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_overview_endpoints(client: AsyncClient, auth_headers: dict):
    for path in (
        "/api/v1/overview/activities",
        "/api/v1/overview/recent-notes",
        "/api/v1/overview/recommended",
        "/api/v1/overview/trending",
    ):
        res = await client.get(path, headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json()["data"], list)
