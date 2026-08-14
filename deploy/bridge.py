"""领域能力 → agent AgentTool 桥(§5.4)。

名称 <domain>__<capability>;元数据透传(cost → write 档,reversible →
irreversible);execute() 走 capability 框架完整守卫链(鉴权/配额/审计),
actor 为 agent 主身。
"""

from __future__ import annotations

from typing import Any

from platform_actor import ActorContext
from platform_capability import execute
from platform_capability.gen_mcp import dataclass_to_json_schema
from platform_contracts import ActorKind, ActorRef

from agent.tools.base import AgentTool

AGENT_MAIN = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main",
                                         scopes=("domain:*",)))


def make_domain_tools(mounts: list) -> dict[str, AgentTool]:
    """挂载清单 → agent 工具集。handler 闭包绑定当次注册表与能力(默认参数)。"""
    tools: dict[str, AgentTool] = {}
    for m in mounts:
        for cap in m.registry.all():
            async def handler(_reg=m.registry, _cap=cap, **kw: Any):
                return await execute(_reg, _cap.name, AGENT_MAIN, kw)

            tools[f"{m.domain}__{cap.name}"] = AgentTool(
                name=f"{m.domain}__{cap.name}",
                description=f"[{m.domain}] {cap.description}",
                handler=handler,
                schema=dataclass_to_json_schema(cap.input_model) if cap.input_model else {},
                dimension="app", write=cap.cost > 0, irreversible=not cap.reversible,
            )
    return tools
