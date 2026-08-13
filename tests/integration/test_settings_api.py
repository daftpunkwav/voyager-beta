"""设置 API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_settings_roundtrip(client: AsyncClient, auth_headers: dict):
    get_res = await client.get("/api/v1/settings/", headers=auth_headers)
    assert get_res.status_code == 200
    data = get_res.json()["data"]
    assert isinstance(data["agent_llm_configs"], list)
    assert len(data["agent_llm_configs"]) >= 6
    assert "agent_code_of_conduct" in data
    assert isinstance(data["agent_guidelines"], list)
    assert len(data["agent_guidelines"]) >= 7

    put_res = await client.put(
        "/api/v1/settings/",
        headers=auth_headers,
        json={
            "theme": "dark",
            "font_scale": 1.1,
            "agent_code_of_conduct": "回答务必简洁",
            "agent_guidelines": [
                {"agent_id": "hub", "guideline": "优先调度 Mentor"},
            ],
        },
    )
    assert put_res.status_code == 200
    put_data = put_res.json()["data"]
    assert put_data["theme"] == "dark"
    assert put_data["font_scale"] == 1.1
    assert put_data["agent_code_of_conduct"] == "回答务必简洁"
    hub_g = next(g for g in put_data["agent_guidelines"] if g["agent_id"] == "hub")
    assert hub_g["guideline"] == "优先调度 Mentor"


@pytest.mark.asyncio
async def test_settings_rejects_localhost_api_base(client: AsyncClient, auth_headers: dict):
    res = await client.put(
        "/api/v1/settings/",
        headers=auth_headers,
        json={"llm_api_base": "https://localhost:11434/v1"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_settings_rejects_private_ip_api_base(client: AsyncClient, auth_headers: dict):
    res = await client.put(
        "/api/v1/settings/",
        headers=auth_headers,
        json={"llm_api_base": "https://192.168.1.1/v1"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_settings_rejects_http_api_base(client: AsyncClient, auth_headers: dict):
    res = await client.put(
        "/api/v1/settings/",
        headers=auth_headers,
        json={"llm_api_base": "http://api.openai.com/v1"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_settings_api_key_too_long_returns_422(client: AsyncClient, auth_headers: dict):
    res = await client.put(
        "/api/v1/settings/",
        headers=auth_headers,
        json={"llm_api_key": "x" * 1025},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_llm_api_key(client: AsyncClient, auth_headers: dict):
    real_key = "sk-realtest1234"
    res = await client.post(
        "/api/v1/settings/api-key",
        headers=auth_headers,
        json={"api_key": real_key},
    )
    assert res.status_code == 200
    masked = res.json()["data"]["masked"]
    assert masked.endswith(real_key[-4:])
    assert "****" in masked

    get_res = await client.get("/api/v1/settings/", headers=auth_headers)
    assert get_res.status_code == 200
    data = get_res.json()["data"]
    assert data["llm_api_key_masked"] == masked
    assert data["llm_configured"] is True
