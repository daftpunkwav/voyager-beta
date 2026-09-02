"""Subagent 实例:一次运行的状态机(§9.4.3)。

对话型(conversational):每轮 run_turn 回复后进入 WAITING_INPUT,等下一句话;
任务型:run 到完成。feed() 是仲裁"并入上下文"模式的入口(§9.7)。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.context.compressor import COMPRESS_BUDGET, compress
from agent.llm import LLMClient
from agent.runtime.events import RuntimeEvents
from agent.runtime.state import ResumeSnapshot, RunState, RunStatus
from agent.subagent.modes import Mode, ModeLimits, run_mode
from agent.tools.activate import (
    graded_toolbelt,
    infer_domains,
    page_preactivate,  # 页面→预激活域映射在 activate.py(phase-30);此处再导出兼容旧 import 路径
)
from agent.tools.base import Toolbelt

#: 跨轮 history 硬上限(条数,phase-15):长对话不无限涨。
#: history 里只有 user/assistant 行(本回合 tool 行只活在 messages),成对丢弃。
HISTORY_MAX = 60


def _paired_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """浅拷贝并把尾部回退到最后一处成对边界(§9.1 工具对不可拆散)。

    崩在多工具轮中途时,messages 尾部可能是「assistant 带 tool_calls 但
    tool 行未齐」的残组;端点要求成对,残组整体丢弃——这些调用本就没有
    可复用的结果,续跑时重新执行不算重复。与 compressor._prune_span 同口径:
    只数 assistant 之后**连续**的 tool 行。
    """
    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):
        m = out[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            j = i + 1
            while j < len(out) and out[j].get("role") == "tool":
                j += 1
            if j - i - 1 < len(m["tool_calls"]):
                del out[i:]
            break
    return out


class SubStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskBook:
    """任务书(§9.4.1):目标、约束、完成判定、模式、能力面、轮数上限。"""

    goal: str
    constraints: str = ""
    done_when: str = ""
    mode: Mode | None = None  # None → 人格默认 / REACT
    allowed_tools: tuple[str, ...] | None = None  # None=不裁剪;()=无工具
    limits: ModeLimits | None = None
    conversational: bool = False


@dataclass
class SubagentInstance:
    task: TaskBook
    toolbelt: Toolbelt
    llm: LLMClient
    system_prompt: str
    events: RuntimeEvents
    state: RunState
    reply_sink: Callable[[str], Awaitable[None]] | None = None
    name: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    history: list[dict[str, Any]] = field(default_factory=list)
    pages: Any | None = None  # PageContextRegistry:领域页预激活(notes/graph/sources)
    active: set[str] | None = None  # 对话实例的工具激活集(跨轮保留,§9.20)
    persona: str = ""  # spawn 时的人格 key:每回合重算 system 要用(phase-15)
    build_system: Callable[[TaskBook, str], str] | None = None
    # Spawner 注入的 system 重算函数(phase-15):每回合 run_turn 现调,
    # 风格/画像/页面/digest/skill 索引改动下一句即生效;不持有 builder 引用避免环导入
    sync_digest: Callable[..., None] | None = None
    # 步骤发生时同步刷新 DigestStore(phase-20);duck type,不 import digest.py
    checkpoint_persist: Callable[[SubagentInstance], None] | None = None
    # Spawner 注入的中途存盘(phase-71,§9.17):= checkpoints.save(state);
    # 未注入(直建实例 / 旧装配)则 _on_step 不做 mid-save
    resume_messages: list[dict[str, Any]] | None = None
    # mid-turn 续跑载荷(phase-71):resume_from_checkpoint 从快照带回,
    # run_turn 检测到即跳过 history 重建,从崩溃点的下一 complete 继续
    _turn_messages: list[dict[str, Any]] | None = field(
        default=None, init=False, repr=False
    )
    # 本回合 ReAct 进行中的 messages 活引用(run_mode 原地追加,§9.1);
    # _on_step 据此采集中途快照,turn 结束置 None

    @property
    def status(self) -> RunStatus:
        return self.state.status

    def build_resume_snapshot(
        self,
        *,
        in_turn: bool = False,
        pending_messages: list[dict[str, Any]] | None = None,
    ) -> ResumeSnapshot:
        """从当前实例采集恢复快照(phase-69/71,§9.17)。

        pending_messages=None 为 turn 边界快照(与 69 行为相同);传当前
        messages 则为 mid-turn 快照:先成对修复再按 compress 预算截断旧
        tool 文本(phase-15 同口径,只截断不剪枝),防超大结果无界写盘。
        """
        pending = (
            compress(
                _paired_messages(pending_messages),
                budget=COMPRESS_BUDGET,
                prune=False,
            )
            if pending_messages is not None
            else None
        )
        return ResumeSnapshot(
            instance_id=self.id,
            instance_name=self.name,
            persona=self.persona,
            goal=self.task.goal,
            constraints=self.task.constraints,
            done_when=self.task.done_when,
            mode=(self.task.mode or Mode.REACT).value,
            allowed_tools=(
                list(self.task.allowed_tools)
                if self.task.allowed_tools is not None
                else None
            ),
            max_rounds=self.task.limits.max_rounds if self.task.limits else None,
            max_tool_calls=self.task.limits.max_tool_calls if self.task.limits else None,
            conversational=self.task.conversational,
            history=[dict(m) for m in self.history],
            active_tools=sorted(self.active) if self.active else [],
            pending_messages=pending,
            in_turn=in_turn,
        )

    async def run_turn(self, user_text: str | None = None) -> str:
        """跑一轮(对话型=一轮问答;任务型=跑到完成)。"""
        self.state.status = RunStatus.RUNNING
        if self.build_system is not None:
            # 每回合重算 system(phase-15):跨回合后风格/画像/页面/digest 才不过期
            self.system_prompt = self.build_system(self.task, self.persona)
        if self.resume_messages:
            # mid-turn 续跑(phase-71):pending_messages 已含 system / history /
            # 本回合 tool 行,跳过 history 重建,从崩溃点的下一 complete 继续;
            # system 行仍按 phase-15 口径现算,风格/画像改动对续跑生效。
            # 续跑不带新输入:唯一入口 resume_run→start 不传 user_text
            messages = [dict(m) for m in self.resume_messages]
            self.resume_messages = None
            if messages and messages[0].get("role") == "system":
                messages[0] = {"role": "system", "content": self.system_prompt}
        else:
            if user_text:
                self.history.append({"role": "user", "content": user_text})
            messages = [{"role": "system", "content": self.system_prompt}, *self.history]
        self._turn_messages = messages  # 中途快照引用(_on_step 采集,phase-71)
        belt = self.toolbelt
        if self.task.allowed_tools is None and self.toolbelt.names():
            # 对话实例(Lucien / tool_allow=None):工具表全量可调,但每轮 complete
            # 只送已激活 schema(phase-06 域激活);激活集挂在实例上跨轮保留。
            if self.active is None:
                self.active = set()
            hinted = infer_domains(
                *(str(m.get("content") or "") for m in self.history[-12:])
            )
            preactivate = list(hinted)
            if self.pages is not None:
                cur = self.pages.current()
                if cur is not None:
                    domain = page_preactivate(cur.page)
                    if domain and domain not in preactivate:
                        preactivate.append(domain)  # 领域页对话预激活,省一轮 activate
            belt = graded_toolbelt(
                self.toolbelt, self.active, preactivate=tuple(preactivate),
            )
        await self.events.emit("RunStarted", run_id=self.state.run_id, subagent=self.id)
        try:
            result = await run_mode(
                self.task.mode or Mode.REACT,
                llm=self.llm,
                toolbelt=belt,
                messages=messages,
                limits=self.task.limits or ModeLimits(),
                on_step=self._on_step,
                continue_if_idle=self.task.conversational,
            )
        except Exception as exc:  # 失败落状态并上报,不炸调度器
            self.state.status = RunStatus.FAILED
            self.state.error = f"{type(exc).__name__}: {exc}"
            await self.events.emit("RunFailed", run_id=self.state.run_id, error=self.state.error)
            raise
        finally:
            # turn 已结束(成败皆然):盘上由 start() finally 落 turn 边界快照,
            # 此后再无步骤事件,_turn_messages 置空防误采
            self._turn_messages = None
        self.history.append({"role": "assistant", "content": result})
        self._bound_history()
        self.state.result = result
        if self.task.conversational:
            self.state.status = RunStatus.WAITING_INPUT
            if self.reply_sink is not None:
                await self.reply_sink(result)
        else:
            self.state.status = RunStatus.COMPLETED
            await self.events.emit(
                "AgentCompleted", run_id=self.state.run_id, subagent=self.id
            )
        return result

    def feed(self, text: str) -> None:
        """仲裁 merge 路径:新输入直接并入本实例上下文(§9.7)。"""
        self.history.append({"role": "user", "content": text})

    def _bound_history(self) -> None:
        """超 HISTORY_MAX 从头部成对丢最旧回合(phase-15)。

        history 里只有 user/assistant 交替行,向上取偶数条丢弃后头部仍是 user,
        不会把 assistant 开头的残回合留给下一轮。
        """
        over = len(self.history) - HISTORY_MAX
        if over > 0:
            del self.history[: (over + 1) // 2 * 2]

    def cancel(self) -> None:
        self.state.status = RunStatus.CANCELLED

    async def _on_step(self, kind: str, name: str, summary: str) -> None:
        self.state.add_step(kind, name, summary)
        # ReAct 轮数 / 工具调用计数(phase-71 同步;字段原先从未被写):
        # round- 步 = 一轮 complete,tool 步 = 一次调用,续跑从盘上值继续累加
        if kind == "llm" and name.startswith("round-"):
            self.state.rounds += 1
        elif kind == "tool":
            self.state.tool_calls += 1
        # 步骤进事件流(gateway _STREAM_TYPES 的 agent.step):Chat 能看到
        # "正在调哪个工具";不进历史重建,只是实时进度。
        await self.events.emit(
            "agent.step",
            subagent=self.name or self.id,
            name=name,
            kind=kind,
            summary=(summary or "")[:120],
        )
        # 同步刷新 DigestStore(phase-20):master 全局层 render 保持最新。
        if self.sync_digest is not None:
            self.sync_digest(self)
        self._mid_save_checkpoint()

    def _mid_save_checkpoint(self) -> None:
        """ReAct 中途增量存盘(phase-71,§9.17):每步刷新盘上快照,崩溃可从中途续。

        仅任务型 REACT(对话型 / 其它模式仍只 turn 结束存盘,本刀范围);
        persist 由 Spawner 注入(= checkpoints.save),未注入为 no-op。
        每步同步写单份 JSON 文件,正确性优先,不做 debounce。
        """
        if (
            self.checkpoint_persist is None
            or self._turn_messages is None
            or self.task.conversational
            or (self.task.mode or Mode.REACT) is not Mode.REACT
        ):
            return
        self.state.resume = self.build_resume_snapshot(
            in_turn=True, pending_messages=self._turn_messages,
        ).to_dict()
        self.checkpoint_persist(self)
