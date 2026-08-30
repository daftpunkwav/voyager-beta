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

from agent.llm import LLMClient
from agent.runtime.events import RuntimeEvents
from agent.runtime.state import RunState, RunStatus
from agent.subagent.modes import Mode, ModeLimits, run_mode
from agent.tools.activate import graded_toolbelt, infer_domains
from agent.tools.base import Toolbelt

#: 页面 → 预激活域(§9.20):用户停在这三个领域页时,对话开局即并入该域
#: 工具,省一轮 activate_tools;其他页(settings/usage…)不预激活。
_PAGE_PREACTIVATE: dict[str, str] = {
    "notes": "notes",
    "graph": "graph",
    "sources": "sources",
}


def page_preactivate(page: str) -> str | None:
    """当前页面对应的工具域;无映射返回 None(单测直测这个小函数)。"""
    return _PAGE_PREACTIVATE.get(page)


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

    @property
    def status(self) -> RunStatus:
        return self.state.status

    async def run_turn(self, user_text: str | None = None) -> str:
        """跑一轮(对话型=一轮问答;任务型=跑到完成)。"""
        self.state.status = RunStatus.RUNNING
        if user_text:
            self.history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": self.system_prompt}, *self.history]
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
        self.history.append({"role": "assistant", "content": result})
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

    def cancel(self) -> None:
        self.state.status = RunStatus.CANCELLED

    async def _on_step(self, kind: str, name: str, summary: str) -> None:
        self.state.add_step(kind, name, summary)
        # 步骤进事件流(gateway _STREAM_TYPES 的 agent.step):Chat 能看到
        # "正在调哪个工具";不进历史重建,只是实时进度。
        await self.events.emit(
            "agent.step",
            subagent=self.name or self.id,
            name=name,
            kind=kind,
            summary=(summary or "")[:120],
        )
