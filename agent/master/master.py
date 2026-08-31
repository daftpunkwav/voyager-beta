"""主 agent(§9.2):统筹·仲裁·派单。

- 对话与任务双轨(§9.5):chat 实例常驻对话;任务经 dispatch_task 后台派单;
- 仲裁(§9.7):chat 正在跑时来新消息 → 按 agent.arbiter.mode 排队(默认)/并入/引导;
- 直聊模式(agent.direct_chat,默认关闭):简单问答由 Lucien 直接回复;
- Lucien 强制 ReAct(决策 §15),人格默认模式仅对派遣生效。

本文件只保留用户对话回合、仲裁与公开常量;派单实现拆到 dispatch.py,
consider 实现拆到 observe.py。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import replace

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventBus

from agent.llm import LLMClient
from agent.master.arbiter import Arbiter, ArbiterMode
from agent.master.digest import DigestStore
from agent.master.settings_store_protocol import SettingsReader
from agent.personas import PERSONAS
from agent.policy import PolicyEngine
from agent.runtime.events import AGENT_MAIN
from agent.runtime.state import RunStatus
from agent.subagent import Mode, ModeLimits, Spawner, SubagentInstance, TaskBook

log = logging.getLogger("agent.master")

CHAT_GOAL = (
    "与用户对话,理解并满足需求。需要动手做事时,用 spawn_subagent 派出任务型"
    " subagent 后台执行;不确定时经 ask_user 向用户提问。回复简洁有温度。"
)

_DEFAULT_LIMITS = ModeLimits()


def limits_from_settings(
    settings: SettingsReader,
    *,
    max_rounds: int | None = None,
    max_tool_calls: int | None = None,
) -> ModeLimits:
    """轮数上限装配(§9.19):全局默认从 settings 每次现读;覆盖值非法/≤0 当没填;
    生效值 = min(覆盖, 全局)——派出档位只能比全局更严。"""
    defaults = (_DEFAULT_LIMITS.max_rounds, _DEFAULT_LIMITS.max_tool_calls)

    def _cap(override: int | None, key: str, fallback: int) -> int:
        try:
            global_v = int(settings.get(key))
        except (TypeError, ValueError):
            global_v = 0
        if global_v <= 0:
            global_v = fallback
        if override is None or override <= 0:
            return global_v
        return min(override, global_v)

    return ModeLimits(
        max_rounds=_cap(max_rounds, "agent.rounds.max", defaults[0]),
        max_tool_calls=_cap(max_tool_calls, "agent.rounds.tool_max", defaults[1]),
    )


class Master:
    def __init__(
        self,
        *,
        llm: LLMClient,
        bus: EventBus | None,
        spawner: Spawner,
        arbiter: Arbiter,
        digests: DigestStore,
        settings: SettingsReader,
        proactive=None,
        hooks=None,
        memory=None,
        subagents=None,  # SubagentRegistry:自建定义按名派遣(§9.4.4)
        policy: PolicyEngine | None = None,  # 全局权限引擎:自建 subagent 网络收窄时拷贝(§9.9)
    ) -> None:
        self._llm = llm
        self._bus = bus
        self._spawner = spawner
        self._arbiter = arbiter
        self._digests = digests
        self._settings = settings
        self._proactive = proactive
        self._hooks = hooks
        self._memory = memory
        self._subagents = subagents
        self._policy = policy
        self._chat: SubagentInstance | None = None
        self._inbox: deque[str] = deque()
        self._lock = asyncio.Lock()
        # 后台派单任务持强引用:防 GC 在完成前回收 Task 导致通报静默丢失
        self._bg: set[asyncio.Task] = set()

    async def handle_user_message(self, text: str, *, trace_id: str = "") -> None:
        """用户消息入口(由事件循环分发)。

        回合后台化(phase-15):新回合的 _turn + 排队消息消化放进 asyncio.Task
        持在 _bg,入口在「已判定排队 / 已启动回合」后即返回——EventLoop 仍是
        串行 await dispatch,但 user.message 的 dispatch 立刻结束,第一句还在
        LLM 上跑时第二句就能进来走仲裁,不再等整轮 ReAct。
        """
        if self._proactive is not None:
            self._proactive.notify_user_reply()
        if self._hooks is not None:
            await self._hooks.fire("on_user_message", text=text)
        if self._memory is not None:
            self._memory.working.add("user", text)

        chat = self._chat
        if chat is not None and chat.status == RunStatus.RUNNING:
            mode = ArbiterMode(self._settings.get("agent.arbiter.mode"))
            decision = await self._arbiter.decide(text, chat.task.goal, mode=mode)
            if decision.action == "merge":
                chat.feed(text)  # 并入上下文,下一轮生效(§9.7)
            else:
                self._inbox.append(text)
                if decision.action == "enqueue_notify":
                    await self._reply(f"[已排队] {decision.reason}", trace_id=trace_id)
            return
        self._start_turn(text, trace_id)

    def _start_turn(self, text: str, trace_id: str) -> None:
        """把回合放后台跑:入口立即返回,锁保证同一时刻只有一轮在写 chat。"""

        async def _run() -> None:
            try:
                async with self._lock:
                    await self._turn(text, trace_id)
                    while self._inbox:  # 排队的消息按序补处理
                        queued = self._inbox.popleft()
                        if self._memory is not None:
                            self._memory.working.add("user", queued)
                        await self._turn(queued, trace_id)
            except Exception:
                # 回合已后台化:EventLoop 不再 await 整轮,失败不能变成
                # 「Task exception was never retrieved」;与 loop 隔离同语义
                log.exception("用户回合失败")

        task = asyncio.create_task(_run())
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    async def _turn(self, text: str, trace_id: str) -> None:
        if self._settings.get("agent.direct_chat"):  # 直聊:不派 subagent(默认关)
            reply = await self._llm.complete(
                [
                    {"role": "system", "content": PERSONAS["orchestrator"].system_prompt},
                    {"role": "user", "content": text},
                ]
            )
            await self._reply(reply.text or "", trace_id=trace_id)
            return
        if self._chat is None or not self._chat.status.alive:
            self._chat = self._spawner.spawn(
                TaskBook(goal=CHAT_GOAL, mode=Mode.REACT, conversational=True),
                persona="orchestrator",
                name="chat",
                reply_sink=self._reply,
            )
        # 每回合重读轮数上限(§9.19):设置页改小/改大后下一句生效,不必重启对话实例
        self._chat.task = replace(self._chat.task, limits=limits_from_settings(self._settings))
        await self._spawner.start(self._chat, text)
        self._digests.upsert(self._chat)

    async def dispatch_task(
        self,
        goal: str,
        *,
        persona: str = "",
        mode: str | None = None,
        allowed_tools: tuple[str, ...] | None = None,
        name: str = "",
        constraints: str = "",
    ) -> SubagentInstance:
        """派单(§9.4)薄包装:实现拆在 dispatch.py,保持 Master 为外部唯一入口。"""
        from agent.master.dispatch import dispatch_task

        return await dispatch_task(
            self,
            self._spawner,
            self._settings,
            self._policy,
            self._subagents,
            self._hooks,
            goal,
            persona=persona,
            mode=mode,
            allowed_tools=allowed_tools,
            name=name,
            constraints=constraints,
        )

    async def consider(self, suggestion: str, *, source_event: str = "") -> None:
        """observe 的"考虑事项"入口薄包装:实现拆在 observe.py。"""
        from agent.master.observe import consider

        await consider(
            self,
            self._settings,
            self._bus,
            self._memory,
            suggestion,
            source_event=source_event,
        )

    async def _reply(self, text: str, *, trace_id: str = "") -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(
                    type=DomainEvent.AGENT_MESSAGE,
                    actor=AGENT_MAIN,
                    payload={"content": text},
                    trace_id=trace_id,
                )
            )

    @property
    def chat(self) -> SubagentInstance | None:
        return self._chat

    @property
    def digests(self) -> DigestStore:
        """让拆出模块能读写摘要卡片(不暴露私有细节)。"""
        return self._digests

    @property
    def background(self) -> set[asyncio.Task]:
        """让拆出模块能注册后台任务并自动清理。"""
        return self._bg
