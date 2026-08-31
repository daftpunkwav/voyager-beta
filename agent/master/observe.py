"""观察处理(§9.2):consider 情节留痕与自动行动。

Master 的 consider 薄包装委托本模块,保持 observe 与派单的解耦。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from platform_contracts import Event
from platform_eventbus import EventBus

from agent.runtime.events import AGENT_MAIN

if TYPE_CHECKING:
    from agent.master.master import Master


async def consider(
    master: "Master",
    settings,
    bus: EventBus | None,
    memory,
    suggestion: str,
    *,
    source_event: str = "",
) -> None:
    """observe 的"考虑事项"入口:留痕 + 发 agent.observe(phase-12);开 auto_index 才自动行动。"""
    if memory is not None:
        memory.episodic.log("consider", suggestion, {"source": source_event})
    acted = False
    if settings.get("agent.observe.auto_index") and "索引" in suggestion:
        await master.dispatch_task(suggestion, persona="graph_guide", name="auto-index")
        acted = True
    if bus is not None:
        # agent.observe ≠ agent.message:观察提示只入 Chat 观察行,不冒充对话
        await bus.publish(
            Event(
                type="agent.observe",
                actor=AGENT_MAIN,
                payload={"content": suggestion, "source": source_event, "acted": acted},
            )
        )
