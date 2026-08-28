"""本机会话签发:环回 GET 写入 HttpOnly Cookie,供浏览器后续带凭证访问。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from platform_actor.http_auth import COOKIE_NAME, is_loopback
from platform_actor.token import LocalTokenIssuer
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError

_TTL = 30 * 24 * 3600


def build_session_router(issuer: LocalTokenIssuer | None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/session/bootstrap")
    async def bootstrap(request: Request) -> JSONResponse:
        if issuer is None:
            return JSONResponse({"ok": True, "mode": "open"})
        if not is_loopback(request):
            raise ServiceError(
                "actor",
                ErrorSuffix.FORBIDDEN,
                "会话签发仅允许本机环回",
                hint="请通过 127.0.0.1 访问本应用",
            )
        token = issuer.issue(LOCAL_USER, ttl_seconds=_TTL)
        resp = JSONResponse({"ok": True, "mode": "cookie"})
        resp.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=_TTL,
            path="/",
        )
        return resp

    return router
