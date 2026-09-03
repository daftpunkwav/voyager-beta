"""派出(§9.4.1):能力面裁剪 + 模式授予 + 上限装配。

"不能写文件"不是提示词约束,而是 trimmed() 之后工具表里真没有 write_file。
"""

from __future__ import annotations

from collections.abc import Callable

from platform_contracts import ErrorSuffix, ServiceError

from agent.llm import LLMClient
from agent.runtime.events import RuntimeEvents
from agent.runtime.scheduler import Scheduler
from agent.runtime.state import CheckpointStore, ResumeSnapshot, RunState, RunStatus
from agent.subagent.instance import Mode, ModeLimits, SubagentInstance, TaskBook
from agent.tools.base import Toolbelt

BuildSystemFn = Callable[[TaskBook, str], str]  # (任务书, 人格 key) → system prompt

#: 终态实例驻留上限(phase-76,§9.17 运行时卫生):COMPLETED / FAILED /
#: CANCELLED 实例超过该数时按插入序淘汰最旧,防长跑进程 instances 无界增长。
#: 硬编码常量不做 settings 键(本刀范围);alive / PENDING 永不淘汰——
#: PENDING 是调度队列里还没跑的实例,淘汰会弄丢待执行任务。
TERMINAL_INSTANCE_CAP = 32
_TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)


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
        sync_digest=None,  # 步骤发生时同步刷新 DigestStore(phase-20);duck type
    ) -> None:
        self._llm = llm
        self._toolbelt = toolbelt
        self._scheduler = scheduler
        self._events = events
        self._checkpoints = checkpoints
        self._build_system = build_system or (lambda task, persona: task.goal)
        self._pages = pages
        self._sync_digest = sync_digest
        self.instances: dict[str, SubagentInstance] = {}

    def _persist_checkpoint(self, inst: SubagentInstance) -> None:
        """checkpoint_persist 注入实现(phase-71):与 start() finally 同一 save 口径。"""
        if self._checkpoints is not None:
            self._checkpoints.save(inst.state)

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
            sync_digest=self._sync_digest,  # 步骤时刷新 DigestStore(phase-20)
            checkpoint_persist=self._persist_checkpoint,  # 中途存盘(phase-71)
        )
        self.instances[instance.id] = instance
        return instance

    async def start(self, instance: SubagentInstance, user_text: str | None = None) -> str:
        """在调度器并发上限内启动实例;turn 结束落边界快照(§9.17)。

        ReAct 中途的增量存盘由 instance._on_step 承担(phase-71);
        这里 finally 落的是 turn 终态(完成/失败/取消)的 turn 边界快照,
        覆盖中途快照,in_turn 复位为 False。
        """
        try:
            return await self._scheduler.run(
                instance.id, instance.run_turn(user_text)
            )
        finally:
            if self._checkpoints is not None:
                instance.state.resume = instance.build_resume_snapshot().to_dict()
                self._checkpoints.save(instance.state)
            # turn 已终态(成败皆然):终态驻留超上限时淘汰最旧(phase-76)
            self._trim_terminal_instances()

    def resume_from_checkpoint(self, run_id: str) -> SubagentInstance:
        """从 checkpoint 重建实例(phase-69,§9.17):任务型 REACT、非对话型。

        只重建不重跑:实例进 self.instances,状态保持盘上原样(boot 后为 PAUSED),
        等显式续跑(resume_run continue_run=true);原 run_id / steps / started_ts 保留。
        """
        if self._checkpoints is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, "未启用 checkpoint 存储")
        for inst in self.instances.values():
            if inst.state.run_id == run_id and inst.status.alive:
                raise ServiceError(
                    "agent", ErrorSuffix.INVALID_INPUT,
                    f"run {run_id} 已有存活实例,不可重复恢复",
                    hint="list_subagents 查看运行中实例",
                )
        try:
            state = self._checkpoints.load(run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND, f"checkpoint 不存在: {run_id}"
            ) from exc
        if state.resume is None:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND,
                f"checkpoint {run_id} 无恢复快照(legacy),不可恢复",
            )
        try:
            snap = ResumeSnapshot.from_dict(state.resume)
        except TypeError as exc:  # 快照缺键/多键/非 dict:坏数据走 ServiceError,不裸抛
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND,
                f"checkpoint {run_id} 恢复快照损坏,不可恢复",
            ) from exc
        if snap.conversational:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                "对话型实例不在恢复范围(主对话不 resume)",
            )
        if snap.mode != Mode.REACT.value:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                f"模式 {snap.mode} 不在恢复范围(仅 react)",
            )
        if state.status not in (RunStatus.PAUSED, RunStatus.WAITING_INPUT, RunStatus.RUNNING):
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                f"状态 {state.status.value} 不可恢复(已完成/失败/取消)",
            )
        limits = None
        if snap.max_rounds is not None or snap.max_tool_calls is not None:
            fallback = ModeLimits()
            limits = ModeLimits(
                max_rounds=snap.max_rounds if snap.max_rounds is not None else fallback.max_rounds,
                max_tool_calls=(
                    snap.max_tool_calls if snap.max_tool_calls is not None else fallback.max_tool_calls
                ),
            )
        task = TaskBook(
            goal=snap.goal,
            constraints=snap.constraints,
            done_when=snap.done_when,
            mode=Mode(snap.mode),
            allowed_tools=tuple(snap.allowed_tools) if snap.allowed_tools is not None else None,
            limits=limits,
            conversational=snap.conversational,
        )
        instance = SubagentInstance(
            task=task,
            toolbelt=self._toolbelt.trimmed(task.allowed_tools),
            llm=self._llm,
            system_prompt=self._build_system(task, snap.persona),
            events=self._events,
            state=state,  # 盘上原样:run_id / steps / started_ts / status 全保留
            reply_sink=None,
            name=snap.instance_name,
            pages=self._pages,
            persona=snap.persona,
            build_system=self._build_system,  # 续跑时每回合重算 system(与 spawn 同源)
            sync_digest=self._sync_digest,
        )
        instance.history = [dict(m) for m in snap.history]
        if snap.active_tools:
            instance.active = set(snap.active_tools)
        if snap.in_turn and snap.pending_messages:
            # mid-turn 续跑(phase-71):崩溃点在本 turn 的 ReAct 中途,
            # pending_messages 原样带回,run_turn 检测到即从下一 complete 继续;
            # 缺失/为空则退回 69 行为(history 重建 + 新开 turn)
            pending = snap.pending_messages
            if not isinstance(pending, list) or not all(
                isinstance(m, dict) for m in pending
            ):
                raise ServiceError(
                    "agent", ErrorSuffix.NOT_FOUND,
                    f"checkpoint {run_id} 恢复快照损坏,不可恢复",
                )
            instance.resume_messages = [dict(m) for m in pending]
        instance.id = snap.instance_id  # 强制还原 id,避免 instances 里换 id 重复
        self.instances[instance.id] = instance
        return instance

    def alive(self) -> list[SubagentInstance]:
        return [i for i in self.instances.values() if i.status.alive]

    def _trim_terminal_instances(self) -> list[str]:
        """终态实例超过 TERMINAL_INSTANCE_CAP 时按插入序淘汰最旧(phase-76)。

        只动 COMPLETED / FAILED / CANCELLED;alive(RUNNING/WAITING_INPUT/PAUSED)
        与 PENDING(排队未跑)永不淘汰。返回被淘汰的实例 id(供测试断言)。
        """
        terminal_ids = [
            iid for iid, inst in self.instances.items()
            if inst.status in _TERMINAL_STATUSES
        ]
        overflow = len(terminal_ids) - TERMINAL_INSTANCE_CAP
        evicted = terminal_ids[:overflow] if overflow > 0 else []
        for iid in evicted:
            self.instances.pop(iid, None)
        return evicted

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
        # 急停落 CANCELLED:终态驻留超上限时淘汰最旧(phase-76)
        self._trim_terminal_instances()
        return [i.id for i in hits]


__all__ = ["Mode", "Spawner", "SubagentInstance", "TaskBook"]
