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
from dataclasses import replace

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventBus

from agent.llm import LLMClient
from agent.master.arbiter import Arbiter, ArbiterMode
from agent.master.digest import DigestStore
from agent.master.settings_store_protocol import SettingsReader
from agent.personas import PERSONAS, resolve_persona
from agent.policy import NetworkPolicy, PolicyEngine, narrow_network
from agent.runtime.events import AGENT_MAIN
from agent.runtime.state import RunStatus
from agent.subagent import Mode, ModeLimits, Spawner, SubagentInstance, TaskBook
from agent.tools.base import Toolbelt

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
        """派单(§9.4):任务型 subagent 后台执行,完成/失败主动通报。

        persona 先查内置预设;查不到再查自建 subagent 注册表(§9.4.4,
        对 master 与预设同构:套用其 mode 与 allowed_tools 白名单)。
        """
        preset = resolve_persona(persona) if persona else None
        custom = self._load_custom(persona) if persona and preset is None else None
        if custom is not None:
            if mode is None:
                mode = custom.mode
            if allowed_tools is None:
                allowed_tools = custom.allowed_tools
            constraints = f"{constraints}\n{custom.description}".strip()
        elif preset is not None and preset.key == "orchestrator":
            mode = Mode.REACT.value  # 统筹者强制 ReAct(决策 §15)
        if allowed_tools is None and preset is not None:
            allowed_tools = preset.tool_allow
        limits = limits_from_settings(
            self._settings,
            max_rounds=custom.max_rounds if custom is not None else None,
            max_tool_calls=custom.max_tool_calls if custom is not None else None,
        )
        task = TaskBook(
            goal=goal,
            constraints=constraints,
            mode=Mode(mode) if mode else None,
            allowed_tools=allowed_tools,
            limits=limits,
        )
        spawn_key = preset.key if preset is not None else persona
        inst = self._spawner.spawn(task, persona=spawn_key, name=name or goal[:16])
        if custom is not None and custom.network_mode:
            inst.toolbelt = self._narrowed_toolbelt(inst.toolbelt, custom.network_mode)
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

    def _narrowed_toolbelt(self, belt: Toolbelt, requested_mode: str) -> Toolbelt:
        """自建 subagent 指定网络档位时的实例专属工具带(§9.9「派出再裁,只能更严」)。

        同一(已裁剪)工具表换一份新 PolicyEngine:fs/app 复用全局,网络档位取
        narrow_network(全局, 自建),域名用全局 agent.network.domains。
        拷贝不带 settings 句柄——任务中途全局放宽不回灌到已派出实例。
        """
        global_mode = str(self._settings.get("agent.network.mode") or "")
        domains = tuple(self._settings.get("agent.network.domains") or ())
        engine = PolicyEngine(
            network=NetworkPolicy(
                mode=narrow_network(global_mode, requested_mode), domains=domains
            ),
            fs=self._policy.fs if self._policy is not None else None,
            app=self._policy.app if self._policy is not None else None,
        )
        return belt.with_policy(engine)

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
        """observe 的"考虑事项"入口:留痕 + 发 agent.observe(phase-12);开 auto_index 才自动行动。"""
        if self._memory is not None:
            self._memory.episodic.log("consider", suggestion, {"source": source_event})
        acted = False
        if self._settings.get("agent.observe.auto_index") and "索引" in suggestion:
            await self.dispatch_task(suggestion, persona="graph_guide", name="auto-index")
            acted = True
        if self._bus is not None:
            # agent.observe ≠ agent.message:观察提示只入 Chat 观察行,不冒充对话
            await self._bus.publish(
                Event(
                    type="agent.observe",
                    actor=AGENT_MAIN,
                    payload={"content": suggestion, "source": source_event, "acted": acted},
                )
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
