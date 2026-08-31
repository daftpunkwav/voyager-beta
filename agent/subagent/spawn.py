"""派出(§9.4.1):能力面裁剪 + 模式授予 + 上限装配。

"不能写文件"不是提示词约束,而是 trimmed() 之后工具表里真没有 write_file。
"""

from __future__ import annotations

from collections.abc import Callable

from agent.llm import LLMClient
from agent.runtime.events import RuntimeEvents
from agent.runtime.scheduler import Scheduler
from agent.runtime.state import CheckpointStore, RunState
from agent.subagent.instance import Mode, SubagentInstance, TaskBook
from agent.tools.base import Toolbelt

BuildSystemFn = Callable[[TaskBook, str], str]  # (任务书, 人格 key) → system prompt


class Spawner:
    def __init__(
        self,
        *,
        llm: LLMClient,
        toolbelt: Toolbelt,
        scheduler: Scheduler,
        events: RuntimeEvents,
        checkpoints: CheckpointStore | None = None,
        build_system: BuildSystemFn | None = None,
        pages=None,  # PageContextRegistry:对话实例按当前页面预激活工具(phase-06)
    ) -> None:
        self._llm = llm
        self._toolbelt = toolbelt
        self._scheduler = scheduler
        self._events = events
        self._checkpoints = checkpoints
        self._build_system = build_system or (lambda task, persona: task.goal)
        self._pages = pages
        self.instances: dict[str, SubagentInstance] = {}

    def spawn(
        self,
        task: TaskBook,
        *,
        persona: str = "",
        name: str = "",
        reply_sink=None,
    ) -> SubagentInstance:
        instance = SubagentInstance(
            task=task,
            toolbelt=self._toolbelt.trimmed(task.allowed_tools),
            llm=self._llm,
            system_prompt=self._build_system(task, persona),
            events=self._events,
            state=RunState(task=task.goal),
            reply_sink=reply_sink,
            name=name or task.goal[:16],
            pages=self._pages,
            persona=persona,
            build_system=self._build_system,  # 每回合重算 system(phase-15)
        )
        self.instances[instance.id] = instance
        return instance

    async def start(self, instance: SubagentInstance, user_text: str | None = None) -> str:
        """在调度器并发上限内启动实例;每轮结束存 checkpoint(§9.17)。"""
        try:
            return await self._scheduler.run(
                instance.id, instance.run_turn(user_text)
            )
        finally:
            if self._checkpoints is not None:
                self._checkpoints.save(instance.state)

    def alive(self) -> list[SubagentInstance]:
        return [i for i in self.instances.values() if i.status.alive]

    async def cancel(self, id_or_name: str) -> list[str]:
        """急停(§9.2):按 id 或 name 取消存活实例(含对话型 chat)。

        先置 CANCELLED 状态再打断底层任务——run_turn 中 CancelledError
        属 BaseException,不会被 except Exception 吞掉改写状态;返回被
        停实例 id 列表,未命中返回空列表。
        """
        hits = [
            i for i in self.instances.values()
            if i.status.alive and id_or_name in (i.id, i.name)
        ]
        for inst in hits:
            inst.cancel()
            await self._events.emit("AgentCancelled",
                                    run_id=inst.state.run_id, subagent=inst.id,
                                    name=inst.name)
        for inst in hits:
            await self._scheduler.cancel(inst.id)
        return [i.id for i in hits]


__all__ = ["Mode", "Spawner", "SubagentInstance", "TaskBook"]
