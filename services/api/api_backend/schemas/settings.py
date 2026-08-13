"""Pydantic schemas —— 用户设置（对齐前端 Settings 子集）"""
from typing import Literal, Optional

from api_backend.core.url_safety import validate_public_https_url
from pydantic import BaseModel, Field, field_validator

LlmApiFormat = Literal["openai", "anthropic", "google", "ollama", "custom"]


class AgentLlmConfigOut(BaseModel):
    agent_id: str
    provider_id: str | None = None
    model_override: str | None = None
    speaking_style: str = "default"


class AgentGuidelineOut(BaseModel):
    """单个 Agent 的专属行为准则。"""

    agent_id: str
    guideline: str = Field(default="", max_length=2000)


class LlmProviderOut(BaseModel):
    """对外暴露的供应商配置（不含明文 Key）。"""

    id: str
    preset_id: str = "custom"
    display_name: str = ""
    enabled: bool = True
    api_base: str | None = None
    api_format: LlmApiFormat = "openai"
    available_models: list[str] = Field(default_factory=list)
    default_model: str = ""
    api_key_masked: str | None = None
    configured: bool = False


class LlmProviderUpdate(BaseModel):
    """写入/更新单个供应商；api_key 仅写不回读。"""

    id: str | None = None
    preset_id: str | None = None
    display_name: str | None = None
    enabled: bool | None = None
    api_format: str | None = None
    api_base: str | None = None
    available_models: list[str] | None = None
    default_model: str | None = None
    api_key: str | None = Field(None, max_length=1024)

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, v: Optional[str], info) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        fmt = ""
        if info.data:
            fmt = str(info.data.get("api_format") or "").lower()
        return _validate_provider_api_base(v, fmt)


def _validate_provider_api_base(url: str, api_format: str = "") -> str:
    """Ollama 允许本机 http；其余仍要求公开 HTTPS。"""
    raw = url.strip()
    fmt = (api_format or "").lower()
    if fmt == "ollama":
        from urllib.parse import urlparse

        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Ollama API 基础地址须为 http 或 https")
        if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
            return raw
        # 远程 Ollama 仍走 HTTPS 公开校验
        if parsed.scheme == "https":
            return validate_public_https_url(raw, resolve_dns=True)
        raise ValueError("远程 Ollama 请使用 https")
    return validate_public_https_url(raw, resolve_dns=True)


class SettingsOut(BaseModel):
    theme: Literal["dark", "light"] = "dark"
    font_scale: float = 1.0
    code_font: str = "JetBrains Mono"
    # —— 多供应商 ——
    llm_providers: list[LlmProviderOut] = Field(default_factory=list)
    llm_default_provider_id: str | None = None
    # —— 扁平派生字段（默认供应商，兼容旧前端）——
    llm_provider: str = "openai"
    llm_provider_display_name: str = "OpenAI"
    llm_default_model: str = "gpt-4o"
    llm_model: str = "gpt-4o"
    llm_api_base: Optional[str] = None
    llm_api_format: LlmApiFormat = "openai"
    llm_available_models: list[str] = Field(default_factory=lambda: ["gpt-4o"])
    llm_api_key_masked: Optional[str] = None
    llm_configured: bool = False
    llm_last_test: Optional[str] = None
    llm_latency_ms: Optional[int] = None
    agent_llm_configs: list[AgentLlmConfigOut] = Field(default_factory=list)
    agent_code_of_conduct: str = Field(default="", max_length=4000)
    agent_guidelines: list[AgentGuidelineOut] = Field(default_factory=list)


class SettingsUpdate(BaseModel):
    theme: Optional[Literal["dark", "light"]] = None
    font_scale: Optional[float] = None
    code_font: Optional[str] = None
    llm_providers: Optional[list[LlmProviderUpdate]] = None
    llm_default_provider_id: Optional[str] = None
    # 扁平字段：写入时同步到默认供应商（兼容）
    llm_provider: Optional[str] = None
    llm_provider_display_name: Optional[str] = None
    llm_default_model: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_format: Optional[str] = None
    llm_api_base: Optional[str] = None
    llm_available_models: Optional[list[str]] = None
    llm_api_key: Optional[str] = Field(None, max_length=1024)
    agent_llm_configs: Optional[list[AgentLlmConfigOut]] = None
    agent_code_of_conduct: Optional[str] = Field(None, max_length=4000)
    agent_guidelines: Optional[list[AgentGuidelineOut]] = None

    @field_validator("llm_api_base")
    @classmethod
    def _validate_llm_api_base(cls, v: Optional[str], info) -> Optional[str]:
        if v is None:
            return v
        fmt = ""
        if info.data:
            fmt = str(info.data.get("llm_api_format") or "").lower()
        return _validate_provider_api_base(v, fmt)


class ApiKeyIn(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=1024)
    provider_id: str | None = None


class ApiKeyOut(BaseModel):
    masked: str
    provider_id: str | None = None


class LlmTestOut(BaseModel):
    success: bool
    latency_ms: int
    model: str
    reply: str = ""
    error: str = ""
    litellm_model: str = ""
    provider_id: str | None = None


class LlmTestIn(BaseModel):
    """可选：指定供应商与模型；默认使用默认供应商的默认模型。"""

    model: Optional[str] = Field(None, max_length=128)
    provider_id: Optional[str] = Field(None, max_length=64)