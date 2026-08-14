"""agent.llm.LLMClient 协议 ← llm 服务 complete 能力(§5.3)。

agent 不直连任何 LLM 提供商:补全一律走 llm 服务能力,计量(usage)由服务侧
直写。聚合运行时经内存注册表调用,与 REST 消费走同一守卫链。
"""

from __future__ import annotations

from typing import Any

from platform_contracts import ServiceError

from agent.llm import LLMReply, ToolCall, ToolSpec, Usage

_DEGRADED = "（尚未配置可用的 LLM 提供商:请先添加提供商并填写 api key,我再继续。）"


class ServiceLLM:
    """complete 能力 → LLMReply。

    provider 解析:显式 provider_id 优先;否则取第一个启用且有 api key 的
    提供商(显式选择键属设置页阶段,本阶段自动选择)。
    调用失败(ServiceError,如网络/额度)降级为可读文本,不打断 agent 循环。
    """

    def __init__(self, call, *, provider_id: str = "", model: str = "") -> None:
        # call: async (domain, name, args) -> dict,经能力框架(鉴权/配额/审计)
        self._call = call
        self._provider_id = provider_id
        self._model = model

    async def _resolve_provider(self) -> dict[str, Any] | None:
        if self._provider_id:
            return {"id": self._provider_id, "default_model": self._model}
        providers = await self._call("llm", "list_providers", {})
        usable = [p for p in providers if p.get("enabled", True) and p.get("has_api_key")]
        return usable[0] if usable else None

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None
    ) -> LLMReply:
        provider = await self._resolve_provider()
        if provider is None:
            return LLMReply(text=_DEGRADED)
        try:
            out = await self._call("llm", "complete", {
                "provider_id": provider["id"],
                "model": self._model or provider.get("default_model", ""),
                "messages": messages,
                "tools": [
                    {"name": t.name, "description": t.description, "schema": t.schema}
                    for t in tools
                ] if tools else None,
            })
        except ServiceError as exc:
            return LLMReply(text=f"（LLM 调用失败:{exc.body.message}）")
        usage = out.get("usage") or {}
        return LLMReply(
            text=out.get("text") or None,
            tool_calls=tuple(
                ToolCall(id=tc.get("id", ""), name=tc["name"],
                         arguments=tc.get("arguments") or {})
                for tc in out.get("tool_calls") or ()
            ),
            usage=Usage(input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0)),
        )
