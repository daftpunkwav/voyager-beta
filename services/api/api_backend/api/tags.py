"""标签 API（本地单机）"""
from uuid import UUID

from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.models.project import Tag
from api_backend.schemas.common import DataResponse
from api_backend.schemas.tag import SetProjectTagsBody, SetProjectTagsOut, TagCreate, TagOut
from api_backend.services.tag_service import (
    create_tag,
    delete_tag,
    list_user_tags,
    set_project_tags,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/", response_model=DataResponse[list[TagOut]])
async def list_tags(db: AsyncSession = Depends(get_db)):
    return wrap_data(await list_user_tags(db))


@router.post("/", response_model=DataResponse[TagOut])
async def create_tag_api(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
):
    taken = await db.execute(
        select(Tag.id)
        .where(func.lower(Tag.name) == data.name.strip().lower())
        .limit(1)
    )
    if taken.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "TAG_NAME_DUPLICATE", "message": "标签名已存在"},
        )
    tag = await create_tag(db, data.name)
    return wrap_data(tag)


@router.delete("/{tag_id}", response_model=DataResponse[dict])
async def delete_tag_api(
    tag_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_tag(db, tag_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "TAG_NOT_FOUND", "message": "标签不存在"},
        )
    return wrap_data({"success": True})


@router.put("/projects/{project_id}", response_model=DataResponse[SetProjectTagsOut])
async def set_project_tags_api(
    project_id: UUID,
    body: SetProjectTagsBody,
    db: AsyncSession = Depends(get_db),
):
    result = await set_project_tags(db, project_id, body.tag_ids)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        )
    return wrap_data(result)
