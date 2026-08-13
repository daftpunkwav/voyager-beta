"""本机设置持久化 —— 读写 AppState.settings_json（含多供应商）。"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from api_backend.core.security import decrypt_secret, encrypt_secret, ensure_encrypted_secret
from api_backend.models.app_state import AppState
from api_backend.schemas.settings import (
    AgentGuidelineOut,
    AgentLlmConfigOut,
    LlmProviderOut,
    LlmProviderUpdate,
    SettingsOut,
    SettingsUpdate,
)
from api_backend.services.app_state_service import get_or_create_app_state
from sqlalchemy.ext.asyncio import AsyncSession

AGENT_IDS = ("hub", "scout", "mentor", "navigator", "curator", "scribe", "atlas")


def derive_agent_ids() -> tuple[str, ...]:
    """优先从 agent_core registry 派生；不可用时回退到静态 AGENT_IDS。"""
    try:
        from agent_runtime.runtime import get_agent_runtime

        return tuple(d.id for d in get_agent_runtime().list_agent_definitions())
    except Exception:
        return AGENT_IDS


DEFAULT_AGENT_LLM_CONFIGS: list[dict[str, str | None]] = [
    {
        "agent_id": aid,
        "provider_id": None,
        "model_override": None,
        "speaking_style": "default",
    }
    for aid in AGENT_IDS
]

DEFAULT_AGENT_GUIDELINES: list[dict[str, str]] = [
    {"agent_id": aid, "guideline": ""} for aid in AGENT_IDS
]

DEFAULT_SETTINGS: dict[str, Any] = {
    **SettingsOut(
        agent_llm_configs=[AgentLlmConfigOut(**c) for c in DEFAULT_AGENT_LLM_CONFIGS],
        agent_guidelines=DEFAULT_AGENT_GUIDELINES,
    ).model_dump(),
}
MASK = "sk-****"


def _mask_api_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return MASK
    return f"{key[:3]}****{key[-4:]}"


def _load_raw(state: AppState) -> dict[str, Any]:
    try:
        data = json.loads(state.settings_json or "{}")
        if isinstance(data, dict):
            return {**DEFAULT_SETTINGS, **data}
    except json.JSONDecodeError:
        pass
    return dict(DEFAULT_SETTINGS)


def _normalize_agent_llm_configs(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list) and value:
        by_id = {
            str(item.get("agent_id")): item
            for item in value
            if isinstance(item, dict) and item.get("agent_id")
        }
        merged: list[dict[str, Any]] = []
        for aid in AGENT_IDS:
            if aid in by_id:
                src = by_id[aid]
                merged.append(
                    {
                        "agent_id": aid,
                        "provider_id": src.get("provider_id") or None,
                        "model_override": src.get("model_override") or None,
                        "speaking_style": src.get("speaking_style") or "default",
                    }
                )
            else:
                merged.append(
                    {
                        "agent_id": aid,
                        "provider_id": None,
                        "model_override": None,
                        "speaking_style": "default",
                    }
                )
        return merged
    return list(DEFAULT_AGENT_LLM_CONFIGS)


def _normalize_agent_guidelines(value: Any) -> list[dict[str, str]]:
    by_id: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("agent_id") or "").strip()
            if not aid:
                continue
            guideline = str(item.get("guideline") or "")[:2000]
            by_id[aid] = guideline
    return [{"agent_id": aid, "guideline": by_id.get(aid, "")} for aid in AGENT_IDS]


def _legacy_to_provider(raw: dict[str, Any]) -> dict[str, Any]:
    """从扁平字段合成一条供应商配置。"""
    pid = str(raw.get("llm_default_provider_id") or "") or str(uuid4())
    key = raw.get("llm_api_key")
    return {
        "id": pid,
        "preset_id": raw.get("llm_provider") or "openai",
        "display_name": raw.get("llm_provider_display_name") or "OpenAI",
        "enabled": True,
        "api_base": raw.get("llm_api_base"),
        "api_format": raw.get("llm_api_format") or "openai",
        "available_models": list(raw.get("llm_available_models") or ["gpt-4o"]),
        "default_model": raw.get("llm_default_model")
        or raw.get("llm_model")
        or "gpt-4o",
        "api_key": key,
    }


def ensure_providers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """保证 raw 含 llm_providers；必要时从扁平字段迁移。"""
    providers = raw.get("llm_providers")
    if isinstance(providers, list) and providers:
        normalized: list[dict[str, Any]] = []
        for p in providers:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or uuid4())
            models = p.get("available_models") or []
            if not isinstance(models, list):
                models = []
            default_model = str(p.get("default_model") or (models[0] if models else ""))
            if default_model and default_model not in models:
                models = [*models, default_model]
            normalized.append(
                {
                    "id": pid,
                    "preset_id": str(p.get("preset_id") or "custom"),
                    "display_name": str(p.get("display_name") or "自定义供应商"),
                    "enabled": bool(p.get("enabled", True)),
                    "api_base": p.get("api_base"),
                    "api_format": str(p.get("api_format") or "openai"),
                    "available_models": [str(m) for m in models if m],
                    "default_model": default_model,
                    "api_key": p.get("api_key"),
                }
            )
        if normalized:
            raw["llm_providers"] = normalized
            if not raw.get("llm_default_provider_id"):
                raw["llm_default_provider_id"] = normalized[0]["id"]
            return normalized

    # 迁移：扁平 → 单供应商
    legacy = _legacy_to_provider(raw)
    raw["llm_providers"] = [legacy]
    raw["llm_default_provider_id"] = legacy["id"]
    return [legacy]


def _find_provider(providers: list[dict[str, Any]], provider_id: str | None) -> dict[str, Any] | None:
    if not provider_id:
        return None
    for p in providers:
        if p.get("id") == provider_id:
            return p
    return None


def _default_provider(raw: dict[str, Any]) -> dict[str, Any] | None:
    providers = ensure_providers(raw)
    default_id = raw.get("llm_default_provider_id")
    p = _find_provider(providers, default_id)
    if p:
        return p
    for cand in providers:
        if cand.get("enabled"):
            return cand
    return providers[0] if providers else None


def _provider_to_out(p: dict[str, Any]) -> LlmProviderOut:
    plain = decrypt_secret(p.get("api_key"))
    return LlmProviderOut(
        id=str(p.get("id") or ""),
        preset_id=str(p.get("preset_id") or "custom"),
        display_name=str(p.get("display_name") or ""),
        enabled=bool(p.get("enabled", True)),
        api_base=p.get("api_base"),
        api_format=p.get("api_format") or "openai",  # type: ignore[arg-type]
        available_models=list(p.get("available_models") or []),
        default_model=str(p.get("default_model") or ""),
        api_key_masked=_mask_api_key(plain) if plain else None,
        configured=bool(plain),
    )


def _sync_flat_from_default(raw: dict[str, Any]) -> None:
    """用默认供应商回填扁平字段，供旧调用方读取。"""
    p = _default_provider(raw)
    if not p:
        raw["llm_configured"] = False
        return
    raw["llm_provider"] = p.get("preset_id") or "openai"
    raw["llm_provider_display_name"] = p.get("display_name") or ""
    raw["llm_api_base"] = p.get("api_base")
    raw["llm_api_format"] = p.get("api_format") or "openai"
    models = list(p.get("available_models") or [])
    default_model = p.get("default_model") or (models[0] if models else "gpt-4o")
    raw["llm_default_model"] = default_model
    raw["llm_model"] = default_model
    raw["llm_available_models"] = models
    # 顶层 key 与默认供应商对齐（兼容旧 build_llm_config）
    if p.get("api_key"):
        raw["llm_api_key"] = p.get("api_key")
    plain = decrypt_secret(p.get("api_key"))
    raw["llm_configured"] = bool(plain)


def settings_to_out(state: AppState) -> SettingsOut:
    raw = _load_raw(state)
    ensure_providers(raw)
    _sync_flat_from_default(raw)

    providers_out = [_provider_to_out(p) for p in raw.get("llm_providers") or []]
    default_id = raw.get("llm_default_provider_id")
    if default_id and not any(p.id == default_id for p in providers_out):
        default_id = providers_out[0].id if providers_out else None

    flat_key = decrypt_secret(raw.get("llm_api_key"))
    any_configured = any(p.configured for p in providers_out) or bool(flat_key)

    return SettingsOut(
        theme=raw.get("theme") or "dark",
        font_scale=float(raw.get("font_scale") or 1.0),
        code_font=str(raw.get("code_font") or "JetBrains Mono"),
        llm_providers=providers_out,
        llm_default_provider_id=default_id,
        llm_provider=str(raw.get("llm_provider") or "openai"),
        llm_provider_display_name=str(raw.get("llm_provider_display_name") or "OpenAI"),
        llm_default_model=str(raw.get("llm_default_model") or "gpt-4o"),
        llm_model=str(raw.get("llm_model") or raw.get("llm_default_model") or "gpt-4o"),
        llm_api_base=raw.get("llm_api_base"),
        llm_api_format=raw.get("llm_api_format") or "openai",  # type: ignore[arg-type]
        llm_available_models=list(raw.get("llm_available_models") or []),
        llm_api_key_masked=_mask_api_key(flat_key) if flat_key else None,
        llm_configured=any_configured,
        llm_last_test=raw.get("llm_last_test"),
        llm_latency_ms=raw.get("llm_latency_ms"),
        agent_llm_configs=[
            AgentLlmConfigOut(**c)
            for c in _normalize_agent_llm_configs(raw.get("agent_llm_configs"))
        ],
        agent_code_of_conduct=str(raw.get("agent_code_of_conduct") or "")[:4000],
        agent_guidelines=[
            AgentGuidelineOut(**g)
            for g in _normalize_agent_guidelines(raw.get("agent_guidelines"))
        ],
    )


async def _migrate_plaintext_keys(db: AsyncSession, state: AppState) -> None:
    """读路径将历史明文 Key 升级为 enc:v1。"""
    raw = _load_raw(state)
    changed = False

    stored, migrated = ensure_encrypted_secret(raw.get("llm_api_key"))
    if migrated:
        raw["llm_api_key"] = stored
        changed = True

    ensure_providers(raw)
    for p in raw.get("llm_providers") or []:
        if not isinstance(p, dict):
            continue
        stored_p, mig_p = ensure_encrypted_secret(p.get("api_key"))
        if mig_p:
            p["api_key"] = stored_p
            changed = True

    if not changed:
        return
    state.settings_json = json.dumps(raw, ensure_ascii=False)
    await db.commit()
    await db.refresh(state)


async def get_settings(db: AsyncSession) -> SettingsOut:
    state = await get_or_create_app_state(db)
    await _migrate_plaintext_keys(db, state)
    return settings_to_out(state)


def _apply_provider_updates(
    raw: dict[str, Any],
    updates: list[LlmProviderUpdate] | list[dict[str, Any]],
) -> None:
    """用客户端提交的供应商列表整体替换（保留未传的加密 key）。"""
    ensure_providers(raw)
    existing = {
        str(p.get("id")): p
        for p in (raw.get("llm_providers") or [])
        if isinstance(p, dict) and p.get("id")
    }
    next_list: list[dict[str, Any]] = []
    for item in updates:
        data = item.model_dump(exclude_unset=True) if isinstance(item, LlmProviderUpdate) else dict(item)
        pid = str(data.get("id") or uuid4())
        prev = existing.get(pid) or {}
        api_key = data.pop("api_key", None)
        merged = {
            "id": pid,
            "preset_id": data.get("preset_id", prev.get("preset_id") or "custom"),
            "display_name": data.get(
                "display_name", prev.get("display_name") or "自定义供应商"
            ),
            "enabled": data.get("enabled", prev.get("enabled", True)),
            "api_base": data.get("api_base", prev.get("api_base")),
            "api_format": data.get("api_format", prev.get("api_format") or "openai"),
            "available_models": data.get(
                "available_models", prev.get("available_models") or []
            ),
            "default_model": data.get(
                "default_model", prev.get("default_model") or ""
            ),
            "api_key": prev.get("api_key"),
        }
        if api_key is not None and str(api_key).strip():
            merged["api_key"] = encrypt_secret(str(api_key).strip())
        next_list.append(merged)
    raw["llm_providers"] = next_list
    default_id = raw.get("llm_default_provider_id")
    if default_id and not any(p["id"] == default_id for p in next_list):
        raw["llm_default_provider_id"] = next_list[0]["id"] if next_list else None
    if not raw.get("llm_default_provider_id") and next_list:
        raw["llm_default_provider_id"] = next_list[0]["id"]


async def save_llm_api_key(
    db: AsyncSession,
    api_key: str,
    *,
    provider_id: str | None = None,
) -> tuple[str, str | None]:
    """保存真实 LLM API Key（加密落库），返回 (掩码, provider_id)。"""
    state = await get_or_create_app_state(db)
    raw = _load_raw(state)
    ensure_providers(raw)
    providers = raw.get("llm_providers") or []
    target_id = provider_id or raw.get("llm_default_provider_id")
    target = _find_provider(providers, target_id)
    if target is None and providers:
        target = providers[0]
        target_id = target.get("id")
    enc = encrypt_secret(api_key)
    if target is not None:
        target["api_key"] = enc
    raw["llm_api_key"] = enc  # 兼容扁平
    _sync_flat_from_default(raw)
    state.settings_json = json.dumps(raw, ensure_ascii=False)
    await db.commit()
    await db.refresh(state)
    return _mask_api_key(api_key) or "", str(target_id) if target_id else None


async def update_settings(db: AsyncSession, data: SettingsUpdate) -> SettingsOut:
    state = await get_or_create_app_state(db)
    raw = _load_raw(state)
    ensure_providers(raw)
    payload = data.model_dump(exclude_unset=True)

    # 多供应商整体替换
    if "llm_providers" in payload and data.llm_providers is not None:
        _apply_provider_updates(raw, data.llm_providers)
        payload.pop("llm_providers", None)

    if "llm_default_provider_id" in payload:
        raw["llm_default_provider_id"] = payload.pop("llm_default_provider_id")

    # 扁平写入 → 同步到默认供应商
    flat_key = payload.pop("llm_api_key", None)
    flat_touch = any(
        k in payload
        for k in (
            "llm_provider",
            "llm_provider_display_name",
            "llm_api_base",
            "llm_api_format",
            "llm_available_models",
            "llm_default_model",
            "llm_model",
        )
    )
    if flat_touch or flat_key is not None:
        p = _default_provider(raw)
        if p is None:
            p = _legacy_to_provider(raw)
            raw["llm_providers"] = [p]
            raw["llm_default_provider_id"] = p["id"]
        if "llm_provider" in payload:
            p["preset_id"] = payload.pop("llm_provider")
        if "llm_provider_display_name" in payload:
            p["display_name"] = payload.pop("llm_provider_display_name")
        if "llm_api_base" in payload:
            p["api_base"] = payload.pop("llm_api_base")
        if "llm_api_format" in payload:
            p["api_format"] = payload.pop("llm_api_format")
        if "llm_available_models" in payload:
            p["available_models"] = payload.pop("llm_available_models")
        model = payload.pop("llm_default_model", None)
        if model is None:
            model = payload.pop("llm_model", None)
        else:
            payload.pop("llm_model", None)
        if model is not None:
            p["default_model"] = model
        if flat_key is not None:
            p["api_key"] = encrypt_secret(flat_key)
            raw["llm_api_key"] = p["api_key"]

    # 其余顶层字段
    for k, v in payload.items():
        if k in ("llm_providers",):
            continue
        raw[k] = v

    if data.agent_llm_configs is not None:
        raw["agent_llm_configs"] = _normalize_agent_llm_configs(
            [c.model_dump() for c in data.agent_llm_configs]
        )
    if data.agent_guidelines is not None:
        raw["agent_guidelines"] = _normalize_agent_guidelines(
            [g.model_dump() for g in data.agent_guidelines]
        )

    _sync_flat_from_default(raw)
    state.settings_json = json.dumps(raw, ensure_ascii=False)
    await db.commit()
    await db.refresh(state)
    return settings_to_out(state)


async def record_llm_test(
    db: AsyncSession,
    *,
    success: bool,
    latency_ms: int,
    model: str,
) -> None:
    from datetime import datetime

    state = await get_or_create_app_state(db)
    raw = _load_raw(state)
    raw["llm_last_test"] = datetime.utcnow().isoformat() + "Z"
    raw["llm_latency_ms"] = latency_ms
    if model:
        raw["llm_model"] = model
    raw["llm_test_success"] = success
    state.settings_json = json.dumps(raw, ensure_ascii=False)
    await db.commit()


def get_raw_settings_dict(state: AppState) -> dict[str, Any]:
    """供 LLM config 解析：含加密 key 的原始 dict。"""
    raw = _load_raw(state)
    ensure_providers(raw)
    return raw
