"""询问用户(§9.15):弹窗选型支持 文本/选择/滑块/确认;答案经 answer() 回投。

前端(global-widgets.tsx)订阅 agent.ask 事件渲染弹窗;
gateway 把用户答案回投到 AskUser.answer(见 agent/capabilities.py)。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from platform_contracts import Event
from platform_eventbus import EventBus

from agent.runtime.events import AGENT_MAIN

AGENT_ASK = "agent.ask"  # 事件类型(contracts 词汇表初始集之外的新增,按 §7.2 不封闭约定)


@dataclass(frozen=True)
class Question:
    prompt: str
    kind: str = "confirm"  # text | choice | slider | confirm
    options: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    timeout_s: float = 120.0


class AskUser:
    def __init__(self, bus: EventBus | None, *, actor=AGENT_MAIN) -> None:
        self._bus = bus
        self._actor = actor
        self._pending: dict[str, asyncio.Future] = {}

    async def ask(self, q: Question, *, trace_id: str = "") -> Any:
        """发问题并等答案;超时返回 None(由调用方决定继续或放弃)。"""
        qid = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[qid] = fut
        if self._bus is not None:
            await self._bus.publish(
                Event(
                    type=AGENT_ASK,
                    actor=self._actor,
                    trace_id=trace_id,
                    payload={
                        "question_id": qid,
                        "prompt": q.prompt,
                        "kind": q.kind,
                        "options": list(q.options),
                        "min": q.min,
                        "max": q.max,
                    },
                )
            )
        try:
            return await asyncio.wait_for(fut, q.timeout_s)
        except TimeoutError:
            return None
        finally:
            self._pending.pop(qid, None)

    def answer(self, question_id: str, value: Any) -> bool:
        """用户答案回投入口。返回是否命中等待中的问题。"""
        fut = self._pending.get(question_id)
        if fut is not None and not fut.done():
            fut.set_result(value)
            return True
        return False

    @property
    def pending_count(self) -> int:
        return len(self._pending)
