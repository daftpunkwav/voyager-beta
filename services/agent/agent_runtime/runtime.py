"""Agent Runtime Interface + Embedded 实现。

api_backend 只依赖 AgentRuntimeInterface（经 get_agent_runtime() 获取）；
EmbeddedAgentRuntime 是无状态委托对象（委托到 agent_runtime.execution 与 agent_core），
宿主（api_backend.main lifespan / agent_runtime 入口 / 测试 conftest）在启动期
调用 register_agent_services() 注入 agent_core 业务服务容器。
"""
from __future__ import annotations

from typing import Any, Protocol


class AgentRuntimeInterface(Protocol):
    """Agent 运行层统一接口（api_backend 只依赖此接口）。

    注：SSE 流式入口（stream_chat 等）不在此接口——api/agent.py 经
    agent_service re-export 壳直达 execution，无需多态；此接口仅承载
    api_backend 需要注入/委托的非流式能力。
    """

    async def test_llm(
        self,
        db: Any,
        *,
        provider_id: str | None = None,
        model_override: str | None = None,
    ) -> dict[str, Any]: ...

    async def accept_memory_proposal(
        self, db: Any, proposal_id: str
    ) -> dict[str, Any]: ...

    async def reject_memory_proposal(
        self, db: Any, proposal_id: str
    ) -> dict[str, Any]: ...

    def list_agent_definitions(self) -> list[Any]: ...


class EmbeddedAgentRuntime:
    """Embedded 实现（默认，同进程）。无实例状态，仅委托；服务容器经
    register_agent_services() 全局注入（agent_core.services 承载状态）。"""

    # —— LLM 测试 / 画像记忆 / Agent 清单 ——
    async def test_llm(
        self,
        db: Any,
        *,
        provider_id: str | None = None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        from agent_core.llm.config import build_llm_config_from_user
        from agent_core.llm.provider import LLMProvider

        cfg = await build_llm_config_from_user(
            db, provider_id=provider_id, model_override=model_override
        )
        if not cfg:
            return {
                "ok": False,
                "latency_ms": 0,
                "model": model_override or "",
                "reply": "",
                "error": "未配置 API Key，请先保存密钥",
                "litellm_model": "",
                "provider_id": provider_id,
            }
        if model_override:
            cfg.model = model_override
        provider = LLMProvider(cfg)
        result = await provider.test_connection(model_override=model_override)
        return {
            "ok": result.success,
            "latency_ms": result.latency_ms,
            "model": result.model or model_override or cfg.model,
            "reply": result.reply,
            "error": result.error,
            "litellm_model": result.litellm_model,
            "provider_id": cfg.provider_id or provider_id,
        }

    async def accept_memory_proposal(
        self, db: Any, proposal_id: str
    ) -> dict[str, Any]:
        from agent_core.memory.service import MemoryService

        return await MemoryService(db).accept_memory_proposal(proposal_id)

    async def reject_memory_proposal(
        self, db: Any, proposal_id: str
    ) -> dict[str, Any]:
        from agent_core.memory.service import MemoryService

        return await MemoryService(db).reject_memory_proposal(proposal_id)

    def list_agent_definitions(self) -> list[Any]:
        from agent_core.agents.registry import get_registry

        return list(get_registry().list_all())


# 进程内单例（lazy）：无状态委托对象，构造即返回。
_agent_runtime: EmbeddedAgentRuntime | None = None


def get_agent_runtime() -> AgentRuntimeInterface:
    """返回运行时委托对象（无状态；服务容器由 register_agent_services 注入）。"""
    global _agent_runtime
    if _agent_runtime is None:
        _agent_runtime = EmbeddedAgentRuntime()
    return _agent_runtime
