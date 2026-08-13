"""LLM 配置 —— 从用户 settings_json 构建（支持多供应商）。"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from py_shared.models.app_state import AppState
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _key_material() -> str:
    """与 api_backend Settings 同源的密钥材料（SECRETS_ENCRYPTION_KEY 优先，回退 SECRET_KEY）。

    阶段 2 过渡：优先环境变量，兜底仓库根 .env（与 Settings.env_file 同源），
    避免 .env-only 部署下 agent 侧拿到空密钥导致 LLM Key 解密失败；
    进程启动时一次性加载并缓存（lru_cache），避免运行时 .env 被篡改影响解密；
    阶段 4 由 Contract 注入统一管理。
    """

    def _pick(secret_key: str | None, enc_key: str | None) -> str:
        custom = (enc_key or "").strip()
        if custom:
            return custom
        return (secret_key or "").strip()

    material = _pick(os.environ.get("SECRET_KEY"), os.environ.get("SECRETS_ENCRYPTION_KEY"))
    if material:
        return material
    # 兜底：仓库根 .env（Settings 的 env_file 之一）；不覆盖环境变量
    try:
        from dotenv import dotenv_values

        repo_root = Path(__file__).resolve().parents[4]  # llm/config.py -> 仓库根
        vals = dotenv_values(repo_root / ".env")
        return _pick(vals.get("SECRET_KEY"), vals.get("SECRETS_ENCRYPTION_KEY"))
    except Exception:
        return ""


@dataclass
class LLMConfig:
    """运行时 LLM 配置（含真实 api_key，仅服务端内部使用）"""

    provider: str
    model: str
    api_key: str
    api_base: str | None = None
    api_format: str = "openai"
    provider_id: str | None = None
    max_context_tokens: int = 128_000
    max_output_tokens: int = 4096
    temperature: float = 0.7

    @property
    def has_llm(self) -> bool:
        return bool(self.api_key)

    @property
    def supports_tools(self) -> bool:
        if not self.has_llm:
            return False
        blocked = {"gpt-3.5-turbo-0301", "text-davinci-003"}
        return self.model not in blocked

    def normalized_api_base(self) -> str | None:
        """规范化 api_base：去掉末尾斜杠与多余 messages 路径。"""
        if not self.api_base:
            return None
        base = self.api_base.strip().rstrip("/")
        for suffix in (
            "/v1/messages",
            "/messages",
            "/v1/chat/completions",
            "/chat/completions",
        ):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return base or None

    def litellm_model(self) -> str:
        """
        转换为 litellm model 字符串。

        - Anthropic 兼容（含 MiniMax）：anthropic/<model>
        - Google：gemini/<model>
        - Ollama：ollama/<model>
        - OpenAI 兼容自定义 base：openai/<model>
        """
        m = (self.model or "").strip()
        if not m:
            m = "gpt-4o"
        known = (
            "openai/",
            "anthropic/",
            "deepseek/",
            "gemini/",
            "ollama/",
            "minimax/",
        )
        if m.startswith(known):
            return m

        fmt = (self.api_format or "openai").lower()
        p = (self.provider or "openai").lower()
        base = (self.normalized_api_base() or "").lower()

        if "minimax" in p or "minimax" in base or "minimaxi" in base:
            if fmt in ("anthropic", "custom", "") or "anthropic" in base:
                return f"anthropic/{m}"
            return f"openai/{m}"

        if fmt == "anthropic" or p == "anthropic":
            return f"anthropic/{m}"
        if fmt == "google" or p in ("google", "gemini"):
            return f"gemini/{m}"
        if fmt == "ollama" or p == "ollama":
            return f"ollama/{m}"
        if p == "deepseek":
            return f"deepseek/{m}"
        if self.api_base and p not in ("openai",):
            return f"openai/{m}"
        if self.api_base and fmt in ("openai", "custom"):
            return f"openai/{m}"
        return m


def _load_settings_dict(state: AppState) -> dict[str, Any]:
    try:
        data = json.loads(state.settings_json or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _decrypt_key(stored: Any) -> str:
    from py_shared.security.crypto import decrypt_secret

    return (decrypt_secret(stored, _key_material()) or "").strip()


def _providers_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from agent_core import services as _agent_svc

        _agent_svc.settings().ensure_providers(raw)
    except Exception:
        pass
    providers = raw.get("llm_providers")
    if isinstance(providers, list):
        return [p for p in providers if isinstance(p, dict)]
    return []


def _pick_provider(
    raw: dict[str, Any],
    *,
    provider_id: str | None = None,
) -> dict[str, Any] | None:
    providers = _providers_from_raw(raw)
    if not providers:
        return None

    if provider_id:
        for p in providers:
            if p.get("id") == provider_id and p.get("enabled", True):
                return p
        for p in providers:
            if p.get("id") == provider_id:
                return p

    default_id = raw.get("llm_default_provider_id")
    if default_id:
        for p in providers:
            if p.get("id") == default_id and p.get("enabled", True):
                return p

    for p in providers:
        if p.get("enabled", True) and _decrypt_key(p.get("api_key")):
            return p
    for p in providers:
        if p.get("enabled", True):
            return p
    return providers[0]


def _config_from_provider(
    p: dict[str, Any],
    *,
    model_override: str | None = None,
) -> LLMConfig | None:
    from py_shared.security.crypto import is_encrypted_secret

    stored = p.get("api_key")
    api_key = _decrypt_key(stored)
    if not api_key:
        if stored and is_encrypted_secret(str(stored)):
            logger.warning(
                "供应商 %s API Key 解密失败，请重新保存密钥",
                p.get("display_name") or p.get("id"),
            )
        return None
    models = p.get("available_models") or []
    model = (
        (model_override or "").strip()
        or str(p.get("default_model") or "")
        or (models[0] if models else "gpt-4o")
    )
    preset = str(p.get("preset_id") or "custom")
    return LLMConfig(
        provider=preset,
        model=model,
        api_key=api_key,
        api_base=p.get("api_base") or None,
        api_format=str(p.get("api_format") or "openai"),
        provider_id=str(p.get("id") or "") or None,
    )


def build_llm_config_from_settings(
    raw: dict[str, Any],
    *,
    provider_id: str | None = None,
    model_override: str | None = None,
    agent_id: str | None = None,
) -> LLMConfig | None:
    """从 settings 字典构建配置；无 key 时返回 None。"""
    # Agent 级覆盖
    resolved_provider_id = provider_id
    resolved_model = model_override
    if agent_id:
        if not resolved_provider_id:
            resolved_provider_id = get_agent_provider_id(raw, agent_id)
        if not resolved_model:
            resolved_model = get_agent_model_override(raw, agent_id)

    p = _pick_provider(raw, provider_id=resolved_provider_id)
    if p is not None:
        cfg = _config_from_provider(p, model_override=resolved_model)
        if cfg is not None:
            return cfg

    # 兼容：仅有顶层扁平 key
    from py_shared.security.crypto import is_encrypted_secret

    stored = raw.get("llm_api_key")
    api_key = _decrypt_key(stored)
    if not api_key:
        if stored and is_encrypted_secret(str(stored)):
            logger.warning(
                "llm_api_key 解密失败（enc:v1 密文存在但无法解密），"
                "请用户在设置页重新保存 API Key"
            )
        return None
    model = (
        (resolved_model or "").strip()
        or raw.get("llm_model")
        or raw.get("llm_default_model")
        or "gpt-4o"
    )
    return LLMConfig(
        provider=raw.get("llm_provider") or "openai",
        model=model,
        api_key=api_key,
        api_base=raw.get("llm_api_base") or None,
        api_format=raw.get("llm_api_format") or "openai",
    )


def llm_config_status(raw: dict[str, Any]) -> str:
    """诊断用：ok | missing | decrypt_failed。"""
    from py_shared.security.crypto import is_encrypted_secret

    p = _pick_provider(raw)
    stored = (p or {}).get("api_key") if p else raw.get("llm_api_key")
    if not stored:
        stored = raw.get("llm_api_key")
    if not stored:
        return "missing"
    plain = _decrypt_key(stored)
    if plain:
        return "ok"
    if is_encrypted_secret(str(stored)):
        return "decrypt_failed"
    return "missing"


async def load_user_settings_dict(
    db: AsyncSession,
) -> dict[str, Any]:
    """与 LLM 配置同源：强制刷新 AppState.settings_json。"""
    from agent_core import services as _agent_svc

    state = await _agent_svc.app_state().get_or_create_app_state(db)
    await db.refresh(state, attribute_names=["settings_json", "agent_permissions"])
    raw = _load_settings_dict(state)
    try:
        from agent_core import services as _agent_svc

        _agent_svc.settings().ensure_providers(raw)
    except Exception:
        pass
    return raw


async def build_llm_config_from_user(
    db: AsyncSession,
    *,
    provider_id: str | None = None,
    model_override: str | None = None,
    agent_id: str | None = None,
) -> LLMConfig | None:
    """始终重新读取 AppState，避免 session expire 后拿到空 settings_json。"""
    raw = await load_user_settings_dict(db)
    return build_llm_config_from_settings(
        raw,
        provider_id=provider_id,
        model_override=model_override,
        agent_id=agent_id,
    )


async def build_llm_bundle_from_app(
    db: AsyncSession,
) -> tuple[LLMConfig | None, str, dict[str, Any]]:
    """一次查库返回 (config, status, settings_dict)，诊断与构建同源。"""
    raw = await load_user_settings_dict(db)
    cfg = build_llm_config_from_settings(raw)
    return cfg, llm_config_status(raw), raw


# 兼容旧名
build_llm_bundle_from_user = build_llm_bundle_from_app


def get_agent_provider_id(raw: dict[str, Any], agent_id: str) -> str | None:
    configs = raw.get("agent_llm_configs") or []
    if isinstance(configs, list):
        for c in configs:
            if isinstance(c, dict) and c.get("agent_id") == agent_id:
                return c.get("provider_id") or None
    return None


def get_agent_model_override(raw: dict[str, Any], agent_id: str) -> str | None:
    configs = raw.get("agent_llm_configs") or []
    if isinstance(configs, list):
        for c in configs:
            if isinstance(c, dict) and c.get("agent_id") == agent_id:
                return c.get("model_override") or None
    return None


def get_agent_speaking_style(raw: dict[str, Any], agent_id: str) -> str:
    configs = raw.get("agent_llm_configs") or []
    if isinstance(configs, list):
        for c in configs:
            if isinstance(c, dict) and c.get("agent_id") == agent_id:
                return c.get("speaking_style") or "default"
    return "default"


def get_agent_code_of_conduct(raw: dict[str, Any]) -> str:
    """读取全局行为准则（截断至 4000）。"""
    return str(raw.get("agent_code_of_conduct") or "").strip()[:4000]


def get_agent_guideline(raw: dict[str, Any], agent_id: str) -> str:
    """读取指定 Agent 的专属行为准则（截断至 2000）。"""
    items = raw.get("agent_guidelines") or []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("agent_id") == agent_id:
                return str(item.get("guideline") or "").strip()[:2000]
    return ""
