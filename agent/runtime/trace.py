"""当前调用链 trace 上下文(§7.8)。

master/事件循环处理带 trace 的事件时把 trace_id 放入 ContextVar;
桥接层(deploy/bridge)发起 capability 调用时读取,使 agent 的跨服务调用
与触发的 user.message 同链——审计/调试可整链回放。
asyncio.create_task 会拷贝当前上下文,故后台派单任务自动继承。
"""

from __future__ import annotations

from contextvars import ContextVar

_current: ContextVar[str] = ContextVar("agent_current_trace", default="")


def set_current_trace(trace_id: str) -> object:
    """设置当前 trace,返回 token 供 reset_current_trace 复位。"""
    return _current.set(trace_id)


def reset_current_trace(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


def current_trace_id() -> str:
    """当前链 trace;空串表示不在任何事件处理链上(由调用方决定兜底)。"""
    return _current.get()
