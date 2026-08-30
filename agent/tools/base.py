"""AgentTool 与 Toolbelt:agent 工具的统一封装。

关键设计(§9.4.1):派出 subagent 时经 trimmed() 做能力面裁剪——
"不能写文件"不是口头约束,而是真的不给 write 工具。
每次调用过 policy 四维判定;L1 提示、L2 经 confirm 回调询问用户(§9.15)。
"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from agent.hooks.triggers import HookRegistry
from agent.llm import ToolCall, ToolSpec
from agent.policy import Action, Level, PolicyEngine
from agent.runtime.observability import Meter, MeterRecord

ConfirmFn = Callable[[str], Awaitable[bool]]  # 确认问题 → 用户是否同意
NotifyFn = Callable[[str], Awaitable[None]]  # L1 提示出口


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any] = field(default_factory=dict)
    dimension: str = "none"  # fs | network | shell | app | none
    write: bool = False
    irreversible: bool = False


class Toolbelt:
    def __init__(
        self,
        tools: dict[str, AgentTool],
        policy: PolicyEngine,
        *,
        confirm: ConfirmFn | None = None,
        notify: NotifyFn | None = None,
        meter: Meter | None = None,
        active: set[str] | None = None,
        hooks: HookRegistry | None = None,
    ) -> None:
        self._tools = dict(tools)
        self._policy = policy
        self._confirm = confirm
        self._notify = notify
        self._meter = meter
        self._active = active  # 分级加载(§9.20):非 None 时 specs() 只回激活集
        self._hooks = hooks  # 工具生命周期 hook(phase-11):pre/post_tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def register(self, tools: dict[str, AgentTool]) -> None:
        """原地并入根名册(phase-11b 外接 MCP):对话实例每轮从根再拷名册,
        下一句对话即可见;已存在的同名工具被覆盖(批准重挂时先 unregister)。"""
        self._tools.update(tools)

    def unregister(self, names: Iterable[str]) -> None:
        """从根名册原地移除(移除 MCP server / 重挂前清理残名);缺名忽略。"""
        for n in names:
            self._tools.pop(n, None)

    def specs(self) -> list[ToolSpec]:
        names = self.names()
        if self._active is not None:
            # 激活集中不存在的名字自然缺席;call() 不受限(误点未激活名仍可执行,
            # 超时问题只来自 schema 体积,phase-06 决策)
            names = [n for n in names if n in self._active]
        return [
            ToolSpec(name=t.name, description=t.description, schema=t.schema)
            for t in (self._tools[n] for n in names)
        ]

    def trimmed(self, allow: Iterable[str] | None) -> Toolbelt:
        """能力面裁剪(§9.4.1):allow=None 原样;否则只保留白名单中的工具。

        白名单条目支持**前缀授予**(phase-06):以 `*` 结尾(如 `notes__*`)时,
        相对**当前名册**展开——人格模块 import 时桥工具尚未注册,禁止在
        persona 文件里写死展开结果;新挂载的领域能力自动进入裁剪后的工具面。
        """
        if allow is None:
            return self
        entries = list(allow)
        prefixes = tuple(a[:-1] for a in entries if a.endswith("*") and len(a) > 1)
        exact = {a for a in entries if not a.endswith("*")}
        keep = {
            n for n in self._tools
            if n in exact or any(n.startswith(p) for p in prefixes)
        }
        return Toolbelt(
            {n: t for n, t in self._tools.items() if n in keep},
            self._policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            hooks=self._hooks,
        )

    def with_active(self, active: set[str], extra: dict[str, AgentTool] | None = None) -> Toolbelt:
        """分级加载视图(phase-06):共享权限引擎/确认通道,specs() 只回激活集。

        active 是**共享引用**:activate_tools 的 handler 原地修改它,下一次
        specs() 即见新工具面;call() 不受限(全量可调)。extra 用于并入绑定
        该激活集的内部工具(activate_tools),不改全局 Toolbelt(多实例共享)。
        """
        tools = dict(self._tools)
        if extra:
            tools.update(extra)
        return Toolbelt(
            tools,
            self._policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            active=active,
            hooks=self._hooks,
        )

    def with_policy(self, policy: PolicyEngine) -> Toolbelt:
        """换权限引擎(§9.9 派出收窄):同一工具表、新判定引擎;通常在 trimmed() 之后套用,
        不经 _tools 私有字段从外面硬拆。"""
        return Toolbelt(
            self._tools,
            policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            active=self._active,
            hooks=self._hooks,
        )

    async def call(self, call: ToolCall) -> str:
        tool = self._tools.get(call.name)
        if tool is None:
            return f"[未知工具] {call.name}(可能未授予本 subagent)"
        target = str(
            call.arguments.get("path")
            or call.arguments.get("url")
            or call.arguments.get("command")
            or tool.name
        )
        decision = self._policy.decide(
            Action(
                dimension=tool.dimension,
                target=target,
                write=tool.write,
                irreversible=tool.irreversible,
            )
        )
        if not decision.allow:
            return f"[已拒绝] {decision.reason}"
        if decision.level >= Level.L2_CONFIRM:
            if self._confirm is None:
                return f"[需确认] {tool.name}({target})需用户确认,当前无可确认通道,已跳过"
            if not await self._confirm(f"允许执行 {tool.name}({target})吗?"):
                return "[已取消] 用户未确认"
        elif decision.level == Level.L1_NOTIFY and self._notify is not None:
            await self._notify(f"{tool.name}: {target}")
        if self._hooks is not None:
            # pre_tool(phase-11):任一 hook 返回 False 即拦截,handler 不执行
            pre = await self._hooks.fire("pre_tool", name=tool.name, arguments=call.arguments)
            if any(r is False for r in pre):
                return f"[已拦截] {tool.name}({target})被 pre_tool hook 拦截"
        start = time.perf_counter()
        ok = True
        try:
            result = tool.handler(**call.arguments)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001  # 工具失败作为文本结果回给 LLM
            ok = False
            result = f"[工具失败] {tool.name}: {type(exc).__name__}: {exc}"
        finally:
            if self._meter is not None:
                self._meter.record(
                    MeterRecord(
                        kind="tool",
                        name=tool.name,
                        ms=(time.perf_counter() - start) * 1000,
                        ok=ok,
                    )
                )
        if self._hooks is not None:
            # post_tool(phase-11):成功失败都要发,让 hook 看见调用结果
            await self._hooks.fire("post_tool", name=tool.name, ok=ok, result=result)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)
