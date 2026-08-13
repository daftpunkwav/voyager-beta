"""AppState 读写辅助 —— 确保单行存在。"""
from api_backend.models.agent import LEARNER_PROFILE_ID, UserProfile
from api_backend.models.app_state import APP_STATE_ID, AppState
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_create_app_state(db: AsyncSession) -> AppState:
    """返回本机 AppState 单行；不存在则创建。"""
    state = await db.get(AppState, APP_STATE_ID)
    if state:
        return state
    state = AppState(id=APP_STATE_ID)
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


async def ensure_singleton_rows(db: AsyncSession) -> None:
    """启动时确保 AppState 与学习者画像各一行。"""
    await get_or_create_app_state(db)
    profile = await db.get(UserProfile, LEARNER_PROFILE_ID)
    if not profile:
        db.add(UserProfile(id=LEARNER_PROFILE_ID))
        await db.commit()
