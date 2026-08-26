"""行为上报与活动流(§6.3 / §7.2 / §10.8)。

- POST /api/activity:前端上报用户行为(页面/指针/选区,前端按类别白名单
  与节流,§7.2),gateway 只投递 user.activity 事件,不做业务解释;
- POST /api/user/online:上线事件(agent 主动问候的触发源之一,§9);
- GET /api/activity/feed:活动页数据源——从事件日志按类型过滤重建,
  不建任何业务表。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from platform_contracts import LOCAL_USER, ActorRef, DomainEvent, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus

from .ratelimit import RateLimiter

_DOMAIN = "gateway"
_ACTIVITY_KINDS = ("page_view", "pointer", "selection", "manual")  # 上报类别初始集


def build_activity_router(bus: EventBus, limiter: RateLimiter) -> APIRouter:
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

    @router.post("/api/activity")
    async def report_activity(request: Request) -> dict:
        body = await _json_body(request)
        kind = str(body.get("kind") or "")
        if kind not in _ACTIVITY_KINDS:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT,
                f"未知行为类别: {kind!r}", hint=f"允许: {list(_ACTIVITY_KINDS)}",
            )
        actor = _actor(request)
        limiter.check(actor.id)
        seq = await bus.publish(Event(
            type=DomainEvent.USER_ACTIVITY, actor=actor,
            payload={
                "kind": kind,
                "page": str(body.get("page") or ""),
                "detail": dict(body.get("detail") or {}),
            },
        ))
        return {"seq": seq}

    @router.post("/api/user/online")
    async def user_online(request: Request) -> dict:
        actor = _actor(request)
        seq = await bus.publish(Event(type=DomainEvent.USER_ONLINE, actor=actor,
                                      payload={}))
        return {"seq": seq}

    @router.get("/api/activity/feed")
    async def activity_feed(after_seq: int = 0, types: str = "",
                            limit: int = 200) -> dict:
        type_list = tuple(t for t in types.split(",") if t) or None
        rows = bus.log.read_after(after_seq=after_seq, types=type_list, limit=limit)
        return {"events": [{"seq": seq, **e.to_dict()} for seq, e in rows]}

    return router
