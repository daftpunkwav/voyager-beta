"""chat 通道(§6.3):投递 user.message;SSE 回推;历史从事件日志重建。

修订自旧 api 的多会话表:新架构是**单时间线**——聊天史即事件日志
(user.message / agent.message 按 seq 升序),多会话视图由 agent 的
episodic 记忆承担,gateway 不建会话表(零业务数据,§6.3)。

SSE 断线续传:客户端带 after_seq(最后收到的 seq),先补日志再跟直推;
订阅掉队(lagged)时自动从日志补齐,不丢消息。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from platform_contracts import (
    LOCAL_USER,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus, EventLog

from .ratelimit import RateLimiter

_DOMAIN = "gateway"
#: 人类时间线关心的事件(聊天 + 进度 + 弹窗 + 跳转指令 + 产物卡 + 设置热更新;
#: note.edited 不入流——编辑器自动保存会产生高频噪音;agent.observe 是观察结论,
#: 不是原始 source.ready 的重复推送)
_STREAM_TYPES = (
    DomainEvent.AGENT_MESSAGE, "agent.ask", DomainEvent.AGENT_NAVIGATE,
    "task.*", "agent.step", "agent.observe", "note.created", "source.added",
    "source.ready", "source.removed", DomainEvent.SETTINGS_CHANGED,
    "notes.ui.changed",
)
_HISTORY_TYPES = (DomainEvent.USER_MESSAGE, DomainEvent.AGENT_MESSAGE)


def build_chat_router(bus: EventBus, limiter: RateLimiter,
                      *, history_page_size: int = 200) -> APIRouter:
    log: EventLog = bus.log
    router = APIRouter()

    def _actor(request: Request) -> ActorRef:
        return getattr(request.state, "actor", None) or LOCAL_USER

    async def _json_body(request: Request) -> dict:
        """解析并校验请求体:非法 JSON / 非 JSON 对象统一 400,而非 500。"""
        try:
            body = await request.json()
        except Exception as exc:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, "请求体必须是合法 JSON"
            ) from exc
        if not isinstance(body, dict):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "请求体必须是 JSON 对象")
        return body

    @router.post("/api/chat/messages")
    async def post_message(request: Request) -> dict:
        body = await _json_body(request)
        content = str(body.get("content") or "").strip()
        if not content:
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "消息内容不能为空")
        actor = _actor(request)
        limiter.check(actor.id)
        seq = await bus.publish(Event(
            type=DomainEvent.USER_MESSAGE, actor=actor,
            payload={"content": content},
        ))
        return {"seq": seq}

    @router.get("/api/chat/messages")
    async def get_messages(after_seq: int = 0, limit: int = history_page_size) -> dict:
        rows = log.read_after(after_seq=after_seq, types=_HISTORY_TYPES, limit=limit)
        return {
            "messages": [
                {"seq": seq, **e.to_dict()} for seq, e in rows
            ],
        }

    @router.get("/api/chat/stream")
    async def stream(request: Request, after_seq: int = -1,
                     once: bool = False) -> StreamingResponse:
        """once=true:只补 after_seq 之后的存量事件即关闭(一次性追平,不保持长连)。"""
        actor = _actor(request)
        limiter.check(actor.id)
        limiter.acquire_sse()
        # 未显式给 after_seq → 从当前末尾开始(不补历史,历史走 GET messages)
        start_seq = log.latest_seq() if after_seq < 0 else after_seq

        async def gen() -> AsyncIterator[str]:
            cursor = start_seq
            sub = bus.subscribe(*_STREAM_TYPES)
            try:
                for seq, event in log.read_after(after_seq=cursor,
                                                 types=_STREAM_TYPES):
                    cursor = max(cursor, seq)
                    yield _frame(event, seq)
                if once:
                    return
                while not await request.is_disconnected():
                    if sub.lagged:  # 掉队:从日志补齐(§7.2)
                        for seq, event in log.read_after(after_seq=cursor,
                                                         types=_STREAM_TYPES):
                            cursor = max(cursor, seq)
                            yield _frame(event, seq)
                        sub.lagged = False
                    try:
                        event = await sub.get(timeout=15.0)
                    except TimeoutError:
                        yield ": ping\n\n"  # 心跳保活
                        continue
                    cursor = max(cursor, sub.last_seq)
                    yield _frame(event, cursor)
            finally:
                bus.unsubscribe(sub)
                limiter.release_sse()

        return StreamingResponse(gen(), media_type="text/event-stream")

    return router


def _frame(event: Event, seq: int) -> str:
    return f"id: {seq}\ndata: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
