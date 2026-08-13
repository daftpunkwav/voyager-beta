"""本机设置 API —— 持久化到 AppState.settings_json"""
from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.schemas.common import DataResponse
from api_backend.schemas.settings import (
    ApiKeyIn,
    ApiKeyOut,
    LlmTestIn,
    LlmTestOut,
    SettingsOut,
    SettingsUpdate,
)
from api_backend.services.settings_service import get_settings, save_llm_api_key, update_settings
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=DataResponse[SettingsOut])
async def get_user_settings(db: AsyncSession = Depends(get_db)):
    return wrap_data(await get_settings(db))


@router.put("/", response_model=DataResponse[SettingsOut])
async def put_user_settings(
    data: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await update_settings(db, data))


@router.post("/test-llm", response_model=DataResponse[LlmTestOut])
async def test_llm(
    body: LlmTestIn | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    对指定供应商模型（或默认供应商默认模型）发起一次真实补全请求。
    模型返回非空文本 → success=true。
    """
    from api_backend.path_setup import ensure_service_paths
    from api_backend.services.settings_service import record_llm_test

    ensure_service_paths()

    settings = await get_settings(db)
    provider_id = body.provider_id if body else None
    model = (body.model if body else None) or None

    # 从供应商列表解析默认模型
    if not model:
        if provider_id:
            for p in settings.llm_providers:
                if p.id == provider_id:
                    model = p.default_model or (p.available_models[0] if p.available_models else None)
                    break
        model = model or settings.llm_model or settings.llm_default_model

    try:
        from agent_runtime.runtime import get_agent_runtime
    except ImportError as e:
        return wrap_data(
            LlmTestOut(
                success=False,
                latency_ms=0,
                model=model or "",
                error=f"LLM 模块不可用（{e}）。请确认以仓库根目录启动 API，且 services/agent 可导入。",
                provider_id=provider_id,
            )
        )

    try:
        result = await get_agent_runtime().test_llm(
            db, provider_id=provider_id, model_override=model
        )
    except Exception as e:
        return wrap_data(
            LlmTestOut(
                success=False,
                latency_ms=0,
                model=model or "",
                error=str(e) or e.__class__.__name__,
                provider_id=provider_id,
            )
        )

    await record_llm_test(
        db,
        success=result["ok"],
        latency_ms=result["latency_ms"],
        model=result["model"] or model or "",
    )
    return wrap_data(
        LlmTestOut(
            success=result["ok"],
            latency_ms=result["latency_ms"],
            model=result["model"] or model or "",
            reply=result.get("reply") or "",
            error=result.get("error") or "",
            litellm_model=result.get("litellm_model") or "",
            provider_id=result.get("provider_id") or provider_id,
        )
    )


@router.post("/api-key", response_model=DataResponse[ApiKeyOut])
async def save_api_key(
    data: ApiKeyIn,
    db: AsyncSession = Depends(get_db),
):
    """接收真实 LLM API Key，持久化后返回掩码。"""
    masked, pid = await save_llm_api_key(db, data.api_key, provider_id=data.provider_id)
    return wrap_data(ApiKeyOut(masked=masked, provider_id=pid))
