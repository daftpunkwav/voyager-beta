"""LLM 用量解析与 settings 多供应商迁移单元测试。"""
from __future__ import annotations

from api_backend.models.app_state import AppState
from api_backend.services.llm_usage_parse import parse_usage_details
from api_backend.services.settings_service import ensure_providers, settings_to_out


def test_parse_usage_openai_cached_details():
    raw = {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "total_tokens": 1200,
        "prompt_tokens_details": {"cached_tokens": 400},
    }
    out = parse_usage_details(raw)
    assert out["prompt_tokens"] == 1000
    assert out["prompt_cached_tokens"] == 400
    assert out["prompt_uncached_tokens"] == 600
    assert out["completion_tokens"] == 200
    assert out["total_tokens"] == 1200


def test_parse_usage_anthropic_cache_read():
    raw = {
        "prompt_tokens": 800,
        "completion_tokens": 100,
        "cache_read_input_tokens": 300,
        "cache_creation_input_tokens": 50,
    }
    out = parse_usage_details(raw)
    assert out["prompt_cached_tokens"] == 300
    assert out["prompt_uncached_tokens"] == 500


def test_parse_usage_empty():
    out = parse_usage_details(None)
    assert out["prompt_tokens"] == 0
    assert out["total_tokens"] == 0


def test_ensure_providers_migrates_flat_settings():
    raw = {
        "llm_provider": "deepseek",
        "llm_provider_display_name": "DeepSeek",
        "llm_api_base": "https://api.deepseek.com/v1",
        "llm_api_format": "openai",
        "llm_available_models": ["deepseek-chat"],
        "llm_default_model": "deepseek-chat",
        "llm_api_key": "sk-test-key-12345678",
    }
    providers = ensure_providers(raw)
    assert len(providers) == 1
    assert providers[0]["preset_id"] == "deepseek"
    assert providers[0]["default_model"] == "deepseek-chat"
    assert raw["llm_default_provider_id"] == providers[0]["id"]


def test_build_llm_config_resolves_agent_provider():
    from agent_core.llm.config import build_llm_config_from_settings

    raw = {
        "llm_providers": [
            {
                "id": "p-a",
                "preset_id": "openai",
                "display_name": "A",
                "enabled": True,
                "api_base": "https://api.openai.com/v1",
                "api_format": "openai",
                "available_models": ["gpt-4o"],
                "default_model": "gpt-4o",
                "api_key": "sk-aaaaaaaaaaaaaaaa",
            },
            {
                "id": "p-b",
                "preset_id": "deepseek",
                "display_name": "B",
                "enabled": True,
                "api_base": "https://api.deepseek.com/v1",
                "api_format": "openai",
                "available_models": ["deepseek-chat"],
                "default_model": "deepseek-chat",
                "api_key": "sk-bbbbbbbbbbbbbbbb",
            },
        ],
        "llm_default_provider_id": "p-a",
        "agent_llm_configs": [
            {
                "agent_id": "scout",
                "provider_id": "p-b",
                "model_override": "deepseek-chat",
                "speaking_style": "default",
            }
        ],
    }
    cfg = build_llm_config_from_settings(raw, agent_id="scout")
    assert cfg is not None
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.provider_id == "p-b"


def test_settings_to_out_exposes_providers():
    import json

    raw = {
        "llm_providers": [
            {
                "id": "p1",
                "preset_id": "openai",
                "display_name": "OpenAI",
                "enabled": True,
                "api_base": "https://api.openai.com/v1",
                "api_format": "openai",
                "available_models": ["gpt-4o"],
                "default_model": "gpt-4o",
                "api_key": None,
            }
        ],
        "llm_default_provider_id": "p1",
    }
    state = AppState(id=1, display_name="u", settings_json=json.dumps(raw))
    out = settings_to_out(state)
    assert len(out.llm_providers) == 1
    assert out.llm_providers[0].id == "p1"
    assert out.llm_default_provider_id == "p1"
    assert out.llm_provider == "openai"
    assert out.llm_configured is False


def test_normalize_strips_api_format_prefix():
    from api_backend.services.llm_usage_service import (
        format_provider_model,
        normalize_model_name,
        normalize_provider_name,
    )

    assert normalize_model_name("anthropic/MiniMax-M3") == "MiniMax-M3"
    assert normalize_provider_name("litellm", model="anthropic/MiniMax-M3") == "minimax"
    assert normalize_provider_name("anthropic", model="MiniMax-M3") == "minimax"
    assert normalize_provider_name("minimax", model="MiniMax-M3") == "minimax"
    assert format_provider_model("litellm", "anthropic/MiniMax-M3") == "minimax/MiniMax-M3"
    assert format_provider_model("anthropic", "claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"
