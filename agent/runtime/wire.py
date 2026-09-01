"""loop 装配表(phase-28):领域 handler 绑定与 hook relay,自 main.py 拆出。

只出数据与 relay,不装配:EventLoop(...) 仍由 build_agent 写,
cursors / subscriber 默认值留在装配根。组件按 duck type 引用方法,
不为拆文件建 ABC;本模块不得 import build_agent / AgentApp。
"""

from __future__ import annotations

from platform_contracts import DomainEvent

from agent.runtime.loop import Handler

__all__ = ["bind_event_loop"]


def bind_event_loop(master, proactive, observer, hooks):
    """返回 (handlers, relay, extra_patterns),供 build_agent 传给 EventLoop。

    - handlers:四条领域绑定(冻结,与原 main.py 一字不差;source.ready 是
      字面量,不是 DomainEvent 常量);
    - relay:凡进入 loop 的事件都转给 on_event(独立熔断在 EventLoop 侧);
    - extra_patterns:声明式 hook 声明过的领域事件类型,订阅据此精确化。
    """
    handlers: dict[str, Handler] = {
        DomainEvent.USER_MESSAGE: lambda ev: master.handle_user_message(
            ev.payload.get("content", ""), trace_id=ev.trace_id
        ),
        DomainEvent.USER_ONLINE: lambda ev: proactive.on_user_online(
            trace_id=ev.trace_id
        ),
        "source.ready": observer.handle,
        DomainEvent.USER_ACTIVITY: observer.handle,  # 行为上报(节流在网关侧,§7.2)
    }
    # 领域事件 → hook(phase-11):on_event 过滤器自行匹配事件类型;
    # 无 hook 时是一次空 fire(phase-28 起不再借 "*" 订阅全量事件)
    async def relay(ev):
        await hooks.fire("on_event", event=ev)

    return handlers, relay, hooks.event_patterns
