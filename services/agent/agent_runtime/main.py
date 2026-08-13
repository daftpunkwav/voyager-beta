"""
Agent 独立运行时入口。

核心实现位于 agent_core（agents/llm/tools/memory）；
共享持久化仍经 services/api 的 api_backend.database / models / agent_service。
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

# 最小引导：仅定位 py-shared（服务路径清单单一权威在 py_shared.repo_paths）。
# services/agent/agent_runtime/main.py → parents[3] = 仓库根
_PY_SHARED = Path(__file__).resolve().parents[3] / "packages" / "py-shared"
_PY_SHARED_STR = str(_PY_SHARED)
if _PY_SHARED_STR not in sys.path:
    sys.path.insert(0, _PY_SHARED_STR)

from py_shared.repo_paths import ensure_service_paths  # noqa: E402

# §4.2.1 TODO: agent_core 与 backend 的循环依赖（阶段 2 已下沉共享模型/端口/安全
# 工具到 packages/py-shared，A/B/C/G 类反向依赖清零；剩余 E/F 类业务服务与
# graph 客户端依赖仍经此 sys.path 注入）应通过 Contract 注入消除。参见
# docs/review/ARCHITECTURE_REFACTOR_REPORT/ARCHITECTURE_REFACTOR_REPORT.md 阶段 4。
# 注：services/graph_engine 必须包含（agent_core/tools/builtin.py 的图谱工具懒加载
# graph_engine_runtime），否则 AGENT_BASE_URL 独立进程模式下调用会 ModuleNotFoundError。
ensure_service_paths()

# 启动期 fail-fast：与主应用 api_backend.main 一致，禁止弱密钥 / 未配置密钥。
# 此前曾用 setdefault 注入固定开发密钥，会静默绕过校验并导致 Fernet 落库
# 密文可被公开密钥解密；删除后由调用方（scripts/dev.ps1 已自动生成）显式配置。
from api_backend.config import get_settings  # noqa: E402

_settings = get_settings()

# 产品名收敛到 app_name 配置（与 api_backend.main 一致），避免硬编码品牌名
app = FastAPI(title=_settings.app_name + " Agent Runtime", version="0.3.0")

_agent_secret = (_settings.secret_key or "").encode("utf-8")
if len(_agent_secret) < 32:
    raise ValueError("SECRET_KEY 长度必须至少为 32 字节，请设置足够强度的随机密钥")

# 注入 agent_core 业务服务契约（Embedded Adapter 由 api_backend 提供）
from agent_core import services as _agent_services  # noqa: E402
from api_backend.services.agent_services_bridge import build_agent_services  # noqa: E402

_agent_services.register_agent_services(build_agent_services())


def _require_internal_token(token: str | None) -> None:
    import hmac

    from api_backend.config import get_settings

    expected = (get_settings().agent_internal_token or "").strip()
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AGENT_TOKEN_UNSET", "message": "未配置 agent_internal_token"},
        )
    if not token or not hmac.compare_digest(token.strip(), expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AGENT_UNAUTHORIZED", "message": "无效内部令牌"},
        )


@app.get("/health")
async def health():
    # 验证 agent_core 本地可导入
    import agent_core  # noqa: F401
    from agent_core.agents.registry import get_registry

    return {
        "status": "ok",
        "service": "agent-runtime",
        "version": "0.3.0",
        "mode": "agent_core",
        "agents": sorted(d.id for d in get_registry().list_all()),
    }


@app.post("/v1/sessions/{session_id}/chat")
async def chat_session(
    session_id: UUID,
    request: Request,
    x_agent_internal_token: str | None = Header(default=None),
):
    """
    内部 SSE 入口：由 API 转发。
    Body: {message, project_id?}
    """
    _require_internal_token(x_agent_internal_token)
    body = await request.json()
    message = str(body.get("message") or "")
    if not message.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "message 不能为空"},
        )
    project_id = None
    raw_pid = body.get("project_id")
    if raw_pid:
        try:
            project_id = UUID(str(raw_pid))
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail={"code": "VALIDATION_ERROR", "message": "project_id 无效"},
            ) from exc

    from agent_core.agents.stream_events import encode_stream_item
    from api_backend.database import get_session_factory
    from api_backend.services.agent_service import stream_chat

    factory = get_session_factory()

    async def gen():
        async with factory() as db:
            async for chunk in stream_chat(
                db,
                session_id,
                message,
                project_id=project_id,
                force_local=True,
            ):
                yield encode_stream_item(chunk)

    return StreamingResponse(gen(), media_type="text/event-stream")