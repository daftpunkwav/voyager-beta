"""总览聚合 API —— 从数据库派生真实数据"""
from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.schemas.common import DataResponse
from api_backend.schemas.overview import (
    ActivityItemOut,
    OverviewRecentNoteOut,
    RecommendedProjectOut,
    TrendingRepoOut,
)
from api_backend.services.overview_service import (
    list_activities,
    list_recent_notes,
    list_recommended,
    list_trending,
)
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/activities", response_model=DataResponse[list[ActivityItemOut]])
async def get_activities(db: AsyncSession = Depends(get_db)):
    return wrap_data(await list_activities(db))


@router.get("/recent-notes", response_model=DataResponse[list[OverviewRecentNoteOut]])
async def get_recent_notes(
    limit: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await list_recent_notes(db, limit=limit))


@router.get("/recommended", response_model=DataResponse[list[RecommendedProjectOut]])
async def get_recommended(
    limit: int = Query(6, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await list_recommended(db, limit=limit))


@router.get("/trending", response_model=DataResponse[list[TrendingRepoOut]])
async def get_trending(
    period: str = Query("weekly"),
    language: str = Query(""),
):
    return wrap_data(await list_trending(language=language, period=period))
