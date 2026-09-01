"""工具调用执行管线：把一次 ToolCall 跑过 policy、确认、hook、重试、熔断、计测。

本模块是 agent.tools.base.Toolbelt 的调用实现(phase-26)。
类型与名册仍保留在 base.py;此处只负责「一次 call 怎么执行」。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Any

from agent.llm import ToolCall
from agent.policy import Action, Level
from agent.runtime.observability import MeterRecord
from agent.runtime.recovery import CircuitBreaker, CircuitOpenError, with_retry
from agent.tools.base import AgentTool, Toolbelt


def _breaker_for(belt: Toolbelt, name: str) -> CircuitBreaker:
    """按工具名一把熔断器(phase-12):懒建;裁剪/收窄视图共享同一份,不因视图重建复位。"""
    cb = belt._breakers.get(name)
    if cb is None:
        cb = CircuitBreaker()  # 默认连续失败 3 次断开 30s(与 §9.17 建议一致)
        belt._breakers[name] = cb
    return cb


async def _invoke_with_recovery(belt: Toolbelt, tool: AgentTool, call: ToolCall) -> Any:
    """handler 执行包重试 + 熔断(§9.17,phase-12;计次与超时语义 phase-43)。

    - 只读/网络 GET 类可重试;write / irreversible 工具禁重试(重试会双写/重复删除);
    - 熔断按**每次 handler 执行**计失败(phase-43):with_retry 内的每一次尝试
      都单独过 breaker.call,连续 3 次 handler 失败即断开;不再按外层
      belt.call 计 1 次(旧结构 3 次 belt.call × 3 次 handler = 9 次才断);
    - TimeoutError / asyncio.TimeoutError 默认不重试(phase-43):MCP/shell
      超时 × 退避重试只会拖长等待,一次超时即失败,交给熔断/文本结果;
    - 熔断打开后的 CircuitOpenError 不进重试循环,直接冒泡(invoke_tool
      折成 [熔断] 文本结果);
    - policy 拒绝 / 用户未确认 / pre_tool 拦截在 invoke_tool() 更早返回,不进这里,
      因此不重试、不记熔断失败;
    - backoff 收在 belt 构造参数,单测注入 0 免真睡。
    """
    breaker = _breaker_for(belt, tool.name)
    retries = 0 if (tool.write or tool.irreversible) else belt._retries

    async def _attempt_once() -> Any:
        result = tool.handler(**call.arguments)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _attempt_with_breaker() -> Any:
        # 每次尝试都经熔断计数:成功复位、失败累计,open_after 次即断(phase-43)
        return await breaker.call(_attempt_once)

    return await with_retry(
        _attempt_with_breaker,
        retries=retries,
        backoff=belt._retry_backoff,
        no_retry_on=(CircuitOpenError, TimeoutError, asyncio.TimeoutError),
    )


async def invoke_tool(belt: Toolbelt, call: ToolCall) -> str:
    """执行一次工具调用,返回给 LLM 的字符串结果。

    顺序:找工具 → 拼 policy Action → 拒绝/L2 确认/L1 提示 → pre_tool →
    handler(重试+熔断) → meter → post_tool → 结果变字符串。
    """
    tool = belt._tools.get(call.name)
    if tool is None:
        return f"[未知工具] {call.name}(可能未授予本 subagent)"
    # app 维 target 必须是工具名(phase-19):桥工具参数里常有 url/path,
    # 拿它们去对 `notes__create_note` 白名单会永远失配。
    if tool.dimension == "app":
        target = tool.name
    else:
        target = str(
            call.arguments.get("path")
            or call.arguments.get("url")
            or call.arguments.get("command")
            or tool.name
        )
    decision = belt._policy.decide(
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
        if belt._confirm is None:
            return f"[需确认] {tool.name}({target})需用户确认,当前无可确认通道,已跳过"
        if not await belt._confirm(f"允许执行 {tool.name}({target})吗?"):
            return "[已取消] 用户未确认"
    elif decision.level == Level.L1_NOTIFY and belt._notify is not None:
        await belt._notify(f"{tool.name}: {target}")
    if belt._hooks is not None:
        # pre_tool(phase-11):任一 hook 返回 False 即拦截,handler 不执行
        pre = await belt._hooks.fire("pre_tool", name=tool.name, arguments=call.arguments)
        if any(r is False for r in pre):
            return f"[已拦截] {tool.name}({target})被 pre_tool hook 拦截"
    start = time.perf_counter()
    ok = True
    try:
        result = await _invoke_with_recovery(belt, tool, call)
    except CircuitOpenError:
        # 熔断不冒成未捕获异常打出 ReAct:折成文本结果回给 LLM(§9.17)
        ok = False
        result = f"[熔断] {tool.name} 连续失败已暂停,请稍后重试"
    except Exception as exc:  # noqa: BLE001  # 工具失败作为文本结果回给 LLM
        ok = False
        result = f"[工具失败] {tool.name}: {type(exc).__name__}: {exc}"
    finally:
        if belt._meter is not None:
            belt._meter.record(
                MeterRecord(
                    kind="tool",
                    name=tool.name,
                    ms=(time.perf_counter() - start) * 1000,
                    ok=ok,
                )
            )
    if belt._hooks is not None:
        # post_tool(phase-11):成功失败都要发,让 hook 看见调用结果
        await belt._hooks.fire("post_tool", name=tool.name, ok=ok, result=result)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
