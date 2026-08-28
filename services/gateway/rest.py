"""gateway 服务装配(§6.3 / §13.1):对人类的唯一聚合入口。

uvicorn services.gateway.rest:app_factory --factory --port 8000(独立运行=
空挂载,仅 chat/activity/health;挂载清单与生命周期由部署入口经 create_app 注入)。

错误约定:ServiceError → 统一错误体(§7.10),经全局 exception handler
兜底——能力路由内的错误由 build_router 已映射,这里兜住 chat/activity
等 gateway 自有端点与未预期异常。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from platform_actor import is_public_path, resolve_http_actor
from platform_contracts import (
    LOCAL_USER,
    HealthReport,
    HealthStatus,
    ServiceError,
)
from platform_eventbus import EventBus, EventLog

from .activity import build_activity_router
from .chat import build_chat_router
from .health import HealthProbe
from .mounts import MountSpec, mount_services
from .ratelimit import RateLimiter
from .session import build_session_router

_DEFAULT_DB = Path(__file__).parent / "data" / "events.db"


def create_app(
    mounts: list[MountSpec] | None = None,
    *,
    db_path: str | Path = _DEFAULT_DB,
    bus: EventBus | None = None,
    lifespan=None,
    issuer=None,
    auth: list | None = None,
    quota: list | None = None,
    audit: list | None = None,
    rate_limit_per_minute: int = 600,
    sse_max_connections: int = 8,
    history_page_size: int = 200,
    extra_routers: list | None = None,
) -> FastAPI:
    if bus is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        bus = EventBus(EventLog(db_path))
    limiter = RateLimiter(rate_limit_per_minute, sse_max_connections)
    probe = HealthProbe(bus)

    if lifespan is None:
        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            yield

    app = FastAPI(title="gateway", lifespan=lifespan)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'none'; default-src 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.exception_handler(ServiceError)
    async def _service_error(_req: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())

    @app.middleware("http")
    async def _actor_middleware(request: Request, call_next):
        # 身份解析(§7.4):合法 Bearer/Cookie → 对应 actor(失败 401,不静默降权);
        # 无令牌仅环回按本地单用户;非环回无令牌 401。探活与 bootstrap 放行。
        if is_public_path(request.url.path):
            request.state.actor = LOCAL_USER
            return await call_next(request)
        try:
            request.state.actor = resolve_http_actor(request, issuer)
        except ServiceError as exc:
            return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())
        return await call_next(request)

    mount_services(app, mounts or [], probe,
                   issuer=issuer, auth=auth, quota=quota, audit=audit)
    app.include_router(build_session_router(issuer))
    # 部署入口注入的横切路由(如文件上传端点;gateway 本身零业务逻辑)
    for router in extra_routers or []:
        app.include_router(router)
    app.include_router(build_chat_router(bus, limiter,
                                         history_page_size=history_page_size))
    app.include_router(build_activity_router(bus, limiter))

    @app.get("/health")
    async def health() -> dict:
        await probe.probe_all()
        return {
            **HealthReport(service="gateway",
                           status=HealthStatus(probe.overall())).to_dict(),
            "services": probe.snapshot(),
        }

    return app


def app_factory() -> FastAPI:
    return create_app()
