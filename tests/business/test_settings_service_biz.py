"""settings_service 业务测试

覆盖：默认设置、API Key 加解密、update 合并、mask 行为。
"""
import os

import pytest
from api_backend.config import get_settings as get_app_settings
from api_backend.database import get_session_factory, init_db, reset_database
from api_backend.schemas.settings import SettingsUpdate
from api_backend.services.app_state_service import get_or_create_app_state
from api_backend.services.settings_service import (
    AGENT_IDS,
    _mask_api_key,
    _normalize_agent_guidelines,
    _normalize_agent_llm_configs,
    get_settings,
    save_llm_api_key,
    update_settings,
)


@pytest.fixture
async def db_session(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'sett.db'}"
    get_app_settings.cache_clear()
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await get_or_create_app_state(session)
        yield session


@pytest.mark.asyncio
async def test_get_settings_default(db_session):
    """首次获取应返回默认 7 个 agent 配置。"""
    session = db_session
    s = await get_settings(session)
    assert len(s.agent_llm_configs) == len(AGENT_IDS)
    assert {c.agent_id for c in s.agent_llm_configs} == set(AGENT_IDS)
    assert s.llm_configured is False


@pytest.mark.asyncio
async def test_save_api_key_encrypts_and_masks(db_session):
    """save_llm_api_key 加密落库，输出仅是 mask。"""
    session = db_session
    mask, _provider_id = await save_llm_api_key(session, "sk-abc1234567890xyz")
    assert mask and "****" in mask
    assert "sk-abc1234567890xyz" not in mask
    import json as _json

    state = await get_or_create_app_state(session)
    raw = _json.loads(state.settings_json)
    assert raw["llm_api_key"].startswith("enc:v1:")


@pytest.mark.asyncio
async def test_get_settings_after_save_returns_masked(db_session):
    """保存后再 get_settings，应看到 mask 但不看到明文。"""
    session = db_session
    await save_llm_api_key(session, "sk-abcdef1234567890XY")
    s = await get_settings(session)
    assert s.llm_configured is True
    assert s.llm_api_key_masked and "****" in s.llm_api_key_masked
    assert "sk-abcdef1234567890XY" not in s.llm_api_key_masked


def test_mask_api_key_short_key_returns_mask():
    """短 key 一律返回 sk-****。"""
    assert _mask_api_key(None) is None
    assert _mask_api_key("") is None
    assert _mask_api_key("short") == "sk-****"
    assert _mask_api_key("sk-longerkey") == "sk-****rkey"


def test_normalize_llm_configs_merges_unknown_agent():
    """输入含未知 agent_id 时，未知被忽略，已知被保留。"""
    configs = [
        {"agent_id": "hub", "model_override": "gpt-4o", "speaking_style": "concise"},
        {"agent_id": "unknown", "model_override": "x"},
    ]
    out = _normalize_agent_llm_configs(configs)
    assert [c["agent_id"] for c in out] == list(AGENT_IDS)
    assert out[0]["model_override"] == "gpt-4o"


def test_normalize_guidelines_truncates_long():
    """单条 guideline 截断 2000 字符。"""
    long = "x" * 3000
    out = _normalize_agent_guidelines([{"agent_id": "hub", "guideline": long}])
    assert len(out[0]["guideline"]) == 2000


@pytest.mark.asyncio
async def test_update_settings_merges_payload(db_session):
    """update 不破坏既有 llm_api_key。"""
    session = db_session
    await save_llm_api_key(session, "sk-originalkey1234")
    payload = SettingsUpdate(theme="light")
    out = await update_settings(session, payload)
    assert out.llm_configured is True
    assert out.llm_api_key_masked and "****" in out.llm_api_key_masked
