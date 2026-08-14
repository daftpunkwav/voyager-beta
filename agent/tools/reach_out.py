"""reach_out 工具:主动发消息(fire-and-forget,§9.8),不等回复。"""

from __future__ import annotations

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventBus

from agent.runtime.events import AGENT_MAIN
from agent.tools.base import AgentTool


def reach_out_tool(bus: EventBus | None) -> dict[str, AgentTool]:
    async def reach_out(text: str) -> str:
        if bus is None:
            return "[未连接事件流]"
        await bus.publish(
            Event(
                type=DomainEvent.AGENT_MESSAGE,
                actor=AGENT_MAIN,
                payload={"content": text, "proactive": True},
            )
        )
        return "[已发送]"

    return {
        "reach_out": AgentTool(
            name="reach_out",
            description="主动给用户发一条消息(不阻塞等回复;受触达预算约束的主动行为用它)",
            handler=reach_out,
            schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    }
