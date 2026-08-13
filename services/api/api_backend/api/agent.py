"""
Agent API —— 会话管理、对话 SSE、反问、分析、专用入口
"""
import json
from uuid import UUID

from api_backend.api.deps import get_db
from api_backend.config import get_settings
from api_backend.core.limiter import limiter
from api_backend.core.module_registry import is_module_available
from api_backend.core.responses import wrap_data
from api_backend.schemas.agent import (
    AgentChatBody,
    AgentChatRequest,
    AgentPermissionsOut,
    AgentPermissionsUpdate,
    AgentProfileOut,
    AgentQuestionAnswer,
    AgentSessionDetailOut,
    AgentSessionOut,
    AnalyzeBody,
    ClassifyBody,
    ContextWindowStatsOut,
    GraphGuideBody,
    ImportAssistBody,
    NoteGenerateBody,
    SessionUpdateBody,
    TrendingScoutBody,
)
from api_backend.schemas.common import DataResponse
from api_backend.services.agent_catalog import AGENT_PROFILES
from api_backend.services.agent_service import (
    create_session,
    delete_session,
    get_context_window,
    get_session_detail,
    list_sessions,
    stream_analyze,
    stream_chat,
    stream_classify_project,
    stream_generate_note,
    stream_graph_guide,
    stream_import_assist,
    stream_question_answer,
    stream_trending_scout,
    update_session,
)
from api_backend.services.project_service import get_project
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

# AGENT_DISABLED=1 时模块加载失败 → safe_load_router 捕获 → /api/v1/agent/* 返回 503
# （模块容错挂载设计：单域失败不阻塞 app 启动）
if get_settings().agent_disabled:
    raise RuntimeError("Agent 服务已禁用（AGENT_DISABLED=1）；agent 端点不可用")

router = APIRouter(prefix="/agent", tags=["agent"])
settings = get_settings()


def _agent_module_down_stream() -> StreamingResponse:
    """Agent 模块未就绪时返回结构化 SSE 错误。"""

    async def event_gen():
        payload = json.dumps(
            {"code": "AGENT_MODULE_DOWN", "message": "Agent 模块未就绪"},
            ensure_ascii=False,
        )
        yield "event: error\ndata: " + payload + "\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _require_agent_module() -> StreamingResponse | None:
    if not is_module_available("agent"):
        return _agent_module_down_stream()
    return None


def _agent_rate_key(request: Request) -> str:
    """Agent SSE 端点限流 key：本地单机按 IP。"""
    return get_remote_address(request)


@router.get("/sessions", response_model=DataResponse[list[AgentSessionOut]])
async def list_agent_sessions(
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await list_sessions(db))


@router.post("/sessions", response_model=DataResponse[AgentSessionOut])
async def create_agent_session(
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await create_session(db))


@router.get("/sessions/{session_id}", response_model=DataResponse[AgentSessionDetailOut])
async def get_agent_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    detail = await get_session_detail(db, session_id)
    if not detail:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_SESSION_NOT_FOUND", "message": "会话不存在"},
        )
    return wrap_data(detail)


@router.delete("/sessions/{session_id}", response_model=DataResponse[dict])
async def delete_agent_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_session(db, session_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_SESSION_NOT_FOUND", "message": "会话不存在"},
        )
    return wrap_data({"success": True})


@router.patch("/sessions/{session_id}", response_model=DataResponse[AgentSessionOut])
async def patch_agent_session(
    session_id: UUID,
    body: SessionUpdateBody,
    db: AsyncSession = Depends(get_db),
):
    # project_id / project_ids 显式 null 或空列表时清除
    clear_project = (
        ("project_id" in body.model_fields_set and body.project_id is None)
        or ("project_ids" in body.model_fields_set and body.project_ids is not None and len(body.project_ids) == 0)
    )
    try:
        updated = await update_session(
            db,
            session_id,
            title=body.title,
            project_id=body.project_id,
            project_ids=body.project_ids if not clear_project else None,
            clear_project=clear_project,
            active_agent=body.active_agent,
        )
    except ValueError as exc:
        if str(exc) == "PROJECT_NOT_OWNED":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "AGENT_SESSION_PROJECT_DENIED",
                    "message": "无权绑定该项目到会话",
                },
            ) from exc
        if str(exc) == "INVALID_ACTIVE_AGENT":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "AGENT_INVALID_ID",
                    "message": "未知的 active_agent",
                },
            ) from exc
        raise
    if not updated:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_SESSION_NOT_FOUND", "message": "会话不存在"},
        )
    return wrap_data(updated)


@router.post("/sessions/{session_id}/chat")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def chat_in_session(
    request: Request,
    response: Response,
    session_id: UUID,
    body: AgentChatBody,
    db: AsyncSession = Depends(get_db),
):
    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_chat(
            db,
            session_id,
            body.message,
            project_id=body.project_id,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/chat")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def chat_legacy(
    request: Request,
    response: Response,
    body: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.session_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "session_id is required"},
        )

    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_chat(
            db,
            body.session_id,
            body.message,
            project_id=body.project_id,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/question")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def answer_question(
    request: Request,
    response: Response,
    body: AgentQuestionAnswer,
    db: AsyncSession = Depends(get_db),
    session_id: UUID | None = Query(None, description="会话 ID（也可放 body）"),
):
    sid = body.session_id or session_id
    if not sid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "session_id is required"},
        )
    # 前端可能传 QuestionAnswer[]，统一转为 dict
    raw = body.answers
    answers: dict = {}
    if isinstance(raw, dict):
        answers = raw
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "question_id" in item:
                answers[item["question_id"]] = item
            elif isinstance(item, dict) and "id" in item:
                answers[item["id"]] = item
            else:
                answers[str(len(answers))] = item

    async def event_gen():
        async for chunk in stream_question_answer(
            db,
            sid,
            body.question_id,
            answers,
            skipped=body.skipped,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/analyze/{project_id}")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def analyze_project(
    request: Request,
    response: Response,
    project_id: UUID,
    body: AnalyzeBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        )
    depth = (body.depth if body else "quick") or "quick"
    agent_id = (body.agent_id if body else None) or None

    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_analyze(
            db,
            project_id,
            depth=depth,
            agent_id=agent_id,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/import-assist")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def import_assist(
    request: Request,
    response: Response,
    body: ImportAssistBody,
    db: AsyncSession = Depends(get_db),
):
    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_import_assist(
            db, body.message, body.context
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/graph-guide")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def graph_guide(
    request: Request,
    response: Response,
    body: GraphGuideBody,
    db: AsyncSession = Depends(get_db),
):
    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_graph_guide(
            db,
            body.message,
            selected_node_id=body.selected_node_id,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/trending-scout")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def trending_scout(
    request: Request,
    response: Response,
    body: TrendingScoutBody,
    db: AsyncSession = Depends(get_db),
):
    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_trending_scout(
            db, body.model_dump()
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/classify")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def classify_project(
    request: Request,
    response: Response,
    body: ClassifyBody,
    db: AsyncSession = Depends(get_db),
):
    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_classify_project(
            db,
            body.project_id,
            user_hint=body.user_hint,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/note/generate")
@limiter.limit(settings.rate_limit_agent, key_func=_agent_rate_key)
async def generate_note(
    request: Request,
    response: Response,
    body: NoteGenerateBody,
    db: AsyncSession = Depends(get_db),
):
    down = _require_agent_module()
    if down is not None:
        return down

    async def event_gen():
        async for chunk in stream_generate_note(
            db,
            body.project_id,
            mode=body.mode,
            topic=body.topic,
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/profiles", response_model=DataResponse[list[AgentProfileOut]])
async def list_profiles():
    return wrap_data(AGENT_PROFILES)


def _load_permissions(state) -> AgentPermissionsOut:
    import json

    try:
        raw = json.loads(state.agent_permissions or "{}")
    except json.JSONDecodeError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return AgentPermissionsOut.model_validate(
        {**AgentPermissionsOut().model_dump(), **raw}
    )


@router.get("/permissions", response_model=DataResponse[AgentPermissionsOut])
async def get_permissions(db: AsyncSession = Depends(get_db)):
    from api_backend.services.app_state_service import get_or_create_app_state

    state = await get_or_create_app_state(db)
    return wrap_data(_load_permissions(state))


@router.patch("/permissions", response_model=DataResponse[AgentPermissionsOut])
async def patch_permissions(
    body: AgentPermissionsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新本机 Agent 工具权限（敏感能力开关）。"""
    import json

    from api_backend.services.app_state_service import get_or_create_app_state

    state = await get_or_create_app_state(db)
    current = _load_permissions(state)
    updates = body.model_dump(exclude_unset=True)
    merged = current.model_dump()
    merged.update(updates)
    out = AgentPermissionsOut.model_validate(merged)
    state.agent_permissions = json.dumps(out.model_dump(), ensure_ascii=False)
    await db.commit()
    await db.refresh(state)
    return wrap_data(out)



@router.get("/context-window", response_model=DataResponse[ContextWindowStatsOut])
async def context_window(
    session_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_context_window(db, session_id)
    return wrap_data(stats)
