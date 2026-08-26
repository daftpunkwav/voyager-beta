"""主 agent(§9.2):统筹·仲裁·派单。

- 对话与任务双轨(§9.5):chat 实例常驻对话;任务经 dispatch_task 后台派单;
- 仲裁(§9.7):chat 正在跑时来新消息 → 按 agent.arbiter.mode 排队(默认)/并入/引导;
- 直聊模式(agent.direct_chat,默认关闭):简单问答由 Lucien 直接回复;
- Lucien 强制 ReAct(决策 §15),人格默认模式仅对派遣生效。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventBus

from agent.llm import LLMClient
from agent.master.arbiter import Arbiter, ArbiterMode
from agent.master.digest import DigestStore
from agent.master.settings_store_protocol import SettingsReader
from agent.personas import PERSONAS
from agent.runtime.events import AGENT_MAIN
from agent.runtime.state import RunStatus
from agent.subagent import Mode, ModeLimits, Spawner, SubagentInstance, TaskBook

log = logging.getLogger("agent.master")

CHAT_GOAL = (
    "与用户对话,理解并满足需求。需要动手做事时,用 spawn_subagent 派出任务型"
    " subagent 后台执行;不确定时经 ask_user 向用户提问。回复简洁有温度。"
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
        self._chat: SubagentInstance | None = None
        self._inbox: deque[str] = deque()
        self._lock = asyncio.Lock()
        # 后台派单任务持强引用:防 GC 在完成前回收 Task 导致通报静默丢失
        self._bg: set[asyncio.Task] = set()

    async def handle_user_message(self, text: str, *, trace_id: str = "") -> None:
        """用户消息入口(由事件循环分发)。"""
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

        async with self._lock:
            await self._turn(text, trace_id)
            while self._inbox:  # 排队的消息按序补处理
                queued = self._inbox.popleft()
                if self._memory is not None:
                    self._memory.working.add("user", queued)
                await self._turn(queued, trace_id)

    async def _turn(self, text: str, trace_id: str) -> None:
        if self._settings.get("agent.direct_chat"):  # 直聊:不派 subagent(默认关)
            reply = await self._llm.complete(
                [
                    {"role": "system", "content": PERSONAS["lucien"].system_prompt},
                    {"role": "user", "content": text},
                ]
            )
            await self._reply(reply.text or "", trace_id=trace_id)
            return
        if self._chat is None or not self._chat.status.alive:
            self._chat = self._spawner.spawn(
                TaskBook(goal=CHAT_GOAL, mode=Mode.REACT, conversational=True),
                persona="lucien",
                name="chat",
                reply_sink=self._reply,
            )
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
        """派单(§9.4):任务型 subagent 后台执行,完成/失败主动通报。

        persona 先查内置预设;查不到再查自建 subagent 注册表(§9.4.4,
        对 master 与预设同构:套用其 mode 与 allowed_tools 白名单)。
        """
        preset = PERSONAS.get(persona) if persona else None
        custom = self._load_custom(persona) if persona and preset is None else None
        if custom is not None:
            if mode is None:
                mode = custom.mode
            if allowed_tools is None:
                allowed_tools = custom.allowed_tools
            constraints = f"{constraints}\n{custom.description}".strip()
        elif preset is not None and preset.key == "lucien":
            mode = Mode.REACT.value  # Lucien 强制 ReAct(决策 §15)
        if allowed_tools is None and preset is not None:
            allowed_tools = preset.tool_allow
        limits = ModeLimits(
            max_rounds=int(self._settings.get("agent.rounds.max")),
            max_tool_calls=int(self._settings.get("agent.rounds.tool_max")),
        )
        task = TaskBook(
            goal=goal,
            constraints=constraints,
            mode=Mode(mode) if mode else None,
            allowed_tools=allowed_tools,
            limits=limits,
        )
        inst = self._spawner.spawn(task, persona=persona, name=name or goal[:16])
        self._digests.upsert(inst)
        if self._hooks is not None:
            await self._hooks.fire("on_subagent_start", subagent=inst.id, goal=goal)

        async def _run() -> None:
            try:
                result = await self._spawner.start(inst)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001  # run_turn 已落状态;这里只通报
                await self._reply(f"[失败] {inst.name}:{type(exc).__name__}: {exc}")
            else:
                await self._reply(f"[完成] {inst.name}:{result[:200]}")
            finally:
                self._digests.upsert(inst)
                if self._hooks is not None:
                    await self._hooks.fire("on_subagent_end", subagent=inst.id)

        task = asyncio.create_task(_run())
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)
        return inst

    def _load_custom(self, name: str):
        """按名取自建 subagent 定义;未注册返回 None(按普通无名任务处理)。"""
        from platform_contracts import ServiceError

        if self._subagents is None:
            return None
        try:
            return self._subagents.load(name)
        except ServiceError:
            return None

    async def consider(self, suggestion: str, *, source_event: str = "") -> None:
        """observe 的"考虑事项"入口:默认只留痕;开启 observe.auto_index 才自动行动。"""
        if self._memory is not None:
            self._memory.episodic.log("consider", suggestion, {"source": source_event})
        if self._settings.get("agent.observe.auto_index") and "索引" in suggestion:
            await self.dispatch_task(suggestion, persona="atlas", name="auto-index")

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
