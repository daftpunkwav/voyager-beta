"""llm 能力注册表(§8.8):提供商目录、密钥边界、连接测试、用量。

secret 边界(场景 G):`add_provider` 不接受 api_key 字段;key 只能经
`set_api_key` 由**用户本人**写入 platform/secrets(_actor 注入,铁律 7
隐私例外在服务侧二次强制,不止靠框架层)。
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError
from platform_secrets import SecretStore, SecretUnavailableError

from .catalog import BUILTIN_PROVIDERS, get_preset, valid_format
from .client import complete as llm_complete
from .client import test_connection as llm_test
from .store import ProviderStore

_DOMAIN = "llm"
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    store: ProviderStore
    secrets: SecretStore


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _key_name(provider_id: str) -> str:
    return f"llm.provider.{provider_id}.api_key"


def _with_key_flag(p: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
    return {**p, "has_api_key": secrets.has(_key_name(p["id"]))}


def _require_provider(pid: str) -> dict[str, Any]:
    p = _require_deps().store.get(pid)
    if p is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"提供商不存在: {pid}")
    return p


def _host_is_nonglobal(host: str) -> bool:
    """环回/内网/链路本地/本机名。hostname 走字面判断,不在这里做 DNS(避免写入时阻塞)。"""
    h = (host or "").lower().rstrip(".")
    if h in {"localhost", "metadata.google.internal"} or h.endswith(".localhost"):
        return True
    try:
        addr = ipaddress.ip_address(h)
        mapped = getattr(addr, "ipv4_mapped", None)
        return not (mapped or addr).is_global
    except ValueError:
        return False


def _validate_base_url(base_url: str, actor: ActorRef | None) -> str:
    """仅 http(s)。内网/环回仅 USER 可写(本地 Ollama);agent 不能把密钥打到内网。"""
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            "base_url 须为 http(s) 且含主机名",
        )
    if _host_is_nonglobal(parsed.hostname):
        if actor is None or actor.kind is not ActorKind.USER:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.FORBIDDEN,
                "内网/环回 base_url 仅用户本人可配置",
                hint="本地 Ollama 等请在设置页填写;agent 不得把密钥打到内网",
            )
    return base_url.strip()


@capability(registry, name="list_builtin_providers", description="内置提供商目录(名称/base_url/格式/模型)")
def list_builtin_providers() -> list[dict]:
    return [dict(p) for p in BUILTIN_PROVIDERS]


@capability(registry, name="list_providers", description="已配置的提供商(含 has_api_key,不回 key)")
def list_providers() -> list[dict]:
    deps = _require_deps()
    return [_with_key_flag(p, deps.secrets) for p in deps.store.list(include_disabled=True)]


@capability(registry, name="get_provider_defaults", description="按内置 preset 取默认 base_url/格式/模型清单")
def get_provider_defaults(preset_id: str) -> dict:
    preset = get_preset(preset_id)
    if preset is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"未知内置提供商: {preset_id}")
    return preset


@capability(registry, name="add_provider", description="新增提供商(元数据;不接受 api_key)")
def add_provider(
    display_name: str,
    base_url: str,
    api_format: str,
    models: list[str] | None = None,
    default_model: str = "",
    preset_id: str = "",
    _actor: ActorRef = None,
) -> dict:
    if not valid_format(api_format):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"api_format 仅支持 chat / anthropic: {api_format}",
        )
    base_url = _validate_base_url(base_url, _actor)
    deps = _require_deps()
    pid = deps.store.upsert({
        "display_name": display_name,
        "preset_id": preset_id,
        "base_url": base_url,
        "api_format": api_format,
        "models": models or [],
        "default_model": default_model or (models[0] if models else ""),
        "custom": True,
    })
    return _with_key_flag(deps.store.get(pid), deps.secrets)


@capability(registry, name="update_provider", description="更新提供商元数据(不含 key)")
def update_provider(
    provider_id: str,
    display_name: str | None = None,
    base_url: str | None = None,
    models: list[str] | None = None,
    default_model: str | None = None,
    enabled: bool | None = None,
    _actor: ActorRef = None,
) -> dict:
    deps = _require_deps()
    current = _require_provider(provider_id)
    if base_url is not None:
        base_url = _validate_base_url(base_url, _actor)
    merged = {
        **current,
        **{k: v for k, v in {
            "display_name": display_name, "base_url": base_url, "models": models,
            "default_model": default_model, "enabled": enabled,
        }.items() if v is not None},
    }
    deps.store.upsert(merged)
    return _with_key_flag(deps.store.get(provider_id), deps.secrets)


@capability(registry, name="remove_provider", description="删除提供商并清除其 key")
def remove_provider(provider_id: str) -> dict:
    deps = _require_deps()
    _require_provider(provider_id)
    deps.store.delete(provider_id)
    deps.secrets.delete(_key_name(provider_id))
    return {"removed": provider_id}


@capability(registry, name="set_api_key", description="设置提供商 api key(secret:仅用户本人)")
def set_api_key(provider_id: str, api_key: str, _actor: ActorRef = None) -> dict:
    """铁律 7 隐私例外:框架层之外,服务侧再强制一次"仅用户可写"。"""
    if _actor is None or _actor.kind is not ActorKind.USER:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.FORBIDDEN,
            "api key 属隐私数据,只能由用户本人在设置页填写",
            hint="agent 可以填好其余字段,key 留给用户",
        )
    _require_provider(provider_id)
    deps = _require_deps()
    try:
        deps.secrets.set(_key_name(provider_id), api_key)
    except SecretUnavailableError:
        # BYOK:本机未配密钥材料时给出可读引导,而非 500
        raise ServiceError(
            _DOMAIN, ErrorSuffix.UNAVAILABLE, "加密仓不可用:本机未配置密钥材料",
            hint="在仓库根 .env 设置 SECRETS_ENCRYPTION_KEY 后重启",
        ) from None
    return {"provider_id": provider_id, "has_api_key": True}


@capability(registry, name="list_models", description="提供商的模型清单")
def list_models(provider_id: str) -> dict:
    p = _require_provider(provider_id)
    return {"provider_id": provider_id, "models": p["models"],
            "default_model": p["default_model"]}


@capability(registry, name="test_connection", description="真实发一次最小请求测连通,回延迟/错误",
            cost=5)
async def test_connection(provider_id: str, model: str = "") -> dict:
    deps = _require_deps()
    p = _require_provider(provider_id)
    key = deps.secrets.get(_key_name(provider_id))
    if not key:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, "该提供商未配置 api key",
            hint="请在设置页填写 api key 后再测试",
        )
    result = await llm_test(p, api_key=key, model=model or p["default_model"])
    return {"ok": result.ok, "latency_ms": round(result.latency_ms, 1),
            "model": result.model, "error": result.error}


@capability(registry, name="complete", description="LLM 对话补全(计量直写 usage;agent 经此消费)",
            cost=10)
async def complete(
    provider_id: str,
    messages: list[dict],
    model: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    tools: list[dict] | None = None,
    _actor: ActorRef = None,
) -> dict:
    deps = _require_deps()
    p = _require_provider(provider_id)
    key = deps.secrets.get(_key_name(provider_id))
    if not key:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "未配置 api key")
    use_model = model or p["default_model"]
    try:
        result = await llm_complete(
            p, api_key=key, model=use_model, messages=messages,
            max_tokens=max_tokens, temperature=temperature, tools=tools,
        )
    except Exception as exc:  # 失败也计量(ok=0)
        deps.store.record_usage(provider_id, use_model, 0, 0,
                                caller=_actor.id if _actor else "", ok=False)
        raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE, f"LLM 调用失败: {exc}") from exc
    deps.store.record_usage(
        provider_id, result.model or use_model, result.input_tokens,
        result.output_tokens, caller=_actor.id if _actor else "",
    )
    return {"text": result.text, "model": result.model,
            "tool_calls": [dict(tc) for tc in result.tool_calls],
            "usage": {"input_tokens": result.input_tokens,
                      "output_tokens": result.output_tokens}}


@capability(registry, name="get_usage_stats", description="用量统计(近 N 天,按模型分组;用量页数据源)")
def get_usage_stats(days: int = 30) -> dict:
    return _require_deps().store.usage_stats(days)
