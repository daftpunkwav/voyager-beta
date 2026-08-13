"""本机身份与学习者画像 API（无认证）"""
from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.schemas.common import DataResponse
from api_backend.schemas.profile import UserProfileOut, UserProfileUpdate
from api_backend.schemas.user import UserOut
from api_backend.services.app_state_service import get_or_create_app_state
from api_backend.services.profile_service import (
    clear_user_memory,
    get_user_profile,
    update_user_profile,
)
from api_backend.services.user_service import app_state_to_out
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/me", response_model=DataResponse[UserOut])
async def get_me(db: AsyncSession = Depends(get_db)):
    """返回本机身份（从 AppState.display_name / GitHub 绑定状态）。"""
    state = await get_or_create_app_state(db)
    return wrap_data(app_state_to_out(state))


@router.get("/profile", response_model=DataResponse[UserProfileOut])
async def get_profile(db: AsyncSession = Depends(get_db)):
    profile = await get_user_profile(db)
    return wrap_data(profile)


@router.patch("/profile", response_model=DataResponse[UserProfileOut])
async def patch_profile(
    data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    profile = await update_user_profile(db, data)
    return wrap_data(profile)


@router.post("/profile/clear-memory", response_model=DataResponse[UserProfileOut])
async def clear_memory(db: AsyncSession = Depends(get_db)):
    """清除 Agent 关于学习者的画像记忆（不删除对话会话；保留自填 identity）。"""
    profile = await clear_user_memory(db)
    return wrap_data(profile)


@router.post(
    "/profile/memory-proposals/{proposal_id}/accept",
    response_model=DataResponse[UserProfileOut],
)
async def accept_memory_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
):
    """确认并写入一条待处理记忆提案。"""
    from agent_runtime.runtime import get_agent_runtime

    result = await get_agent_runtime().accept_memory_proposal(db, proposal_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MEMORY_PROPOSAL_NOT_FOUND",
                "message": result.get("error") or "记忆提案不存在",
            },
        )
    profile = await get_user_profile(db)
    return wrap_data(profile)


@router.post(
    "/profile/memory-proposals/{proposal_id}/reject",
    response_model=DataResponse[UserProfileOut],
)
async def reject_memory_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
):
    """拒绝一条待处理记忆提案。"""
    from agent_runtime.runtime import get_agent_runtime

    result = await get_agent_runtime().reject_memory_proposal(db, proposal_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MEMORY_PROPOSAL_NOT_FOUND",
                "message": result.get("error") or "记忆提案不存在",
            },
        )
    profile = await get_user_profile(db)
    return wrap_data(profile)
