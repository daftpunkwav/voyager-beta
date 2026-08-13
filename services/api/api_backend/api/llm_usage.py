"""LLM 用量统计 API —— 独立模块，加载失败不影响聊天。"""
from __future__ import annotations

from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.schemas.common import DataResponse
from api_backend.services import llm_usage_service as usage_svc
from api_backend.services.llm_usage_parse import parse_usage_details
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/usage", tags=["llm-usage"])


class UsageRecordBody(BaseModel):
    model: str = ""
    provider: str = ""
    session_id: str | None = None
    agent_id: str | None = None
    prompt_tokens: int = 0
    prompt_cached_tokens: int = 0
    prompt_uncached_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    meta: dict | None = None
    # 可选：直接传原始 usage，由服务端解析
    raw_usage: dict | None = None


@router.get("/llm", response_model=DataResponse[dict])
async def get_llm_usage(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await usage_svc.usage_summary(db, days=days))


@router.post("/llm/events", response_model=DataResponse[dict])
async def post_llm_usage_event(
    body: UsageRecordBody,
    db: AsyncSession = Depends(get_db),
):
    """内部/Agent 上报用量；失败由调用方忽略。"""
    try:
        if body.raw_usage:
            parsed = parse_usage_details(body.raw_usage)
            await usage_svc.record_usage(
                db,
                model=body.model,
                provider=body.provider,
                session_id=body.session_id,
                agent_id=body.agent_id,
                prompt_tokens=parsed["prompt_tokens"],
                prompt_cached_tokens=parsed["prompt_cached_tokens"],
                prompt_uncached_tokens=parsed["prompt_uncached_tokens"],
                completion_tokens=parsed["completion_tokens"],
                total_tokens=parsed["total_tokens"],
                meta=body.meta,
            )
        else:
            await usage_svc.record_usage(
                db,
                model=body.model,
                provider=body.provider,
                session_id=body.session_id,
                agent_id=body.agent_id,
                prompt_tokens=body.prompt_tokens,
                prompt_cached_tokens=body.prompt_cached_tokens,
                prompt_uncached_tokens=body.prompt_uncached_tokens,
                completion_tokens=body.completion_tokens,
                total_tokens=body.total_tokens,
                meta=body.meta,
            )
        return wrap_data({"ok": True})
    except Exception:
        return wrap_data({"ok": False})
