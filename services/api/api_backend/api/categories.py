"""
分类 API —— 预设 + 自定义分类管理（本地单机）
"""
from uuid import UUID

from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.models.category import Category
from api_backend.schemas.category import CategoryCreate, CategoryUpdate
from api_backend.schemas.common import DataResponse
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryOut(BaseModel):
    id: UUID
    name: str
    icon: str | None = None
    color: str | None = None
    is_preset: bool


async def _name_taken(
    db: AsyncSession, name: str, *, exclude_id: UUID | None = None
) -> bool:
    q = select(Category.id).where(func.lower(Category.name) == name.strip().lower())
    if exclude_id is not None:
        q = q.where(Category.id != exclude_id)
    return (await db.execute(q.limit(1))).scalar_one_or_none() is not None


@router.get("/", response_model=DataResponse[list[CategoryOut]])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category))
    items = [
        CategoryOut(
            id=c.id,
            name=c.name,
            icon=c.icon,
            color=c.color,
            is_preset=c.is_preset,
        )
        for c in result.scalars().all()
    ]
    return wrap_data(items)


@router.post("/", response_model=DataResponse[CategoryOut])
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
):
    if await _name_taken(db, data.name):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "CATEGORY_NAME_DUPLICATE", "message": "分类名已存在"},
        )
    category = Category(name=data.name, is_preset=False)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return wrap_data(
        CategoryOut(
            id=category.id,
            name=category.name,
            icon=category.icon,
            color=category.color,
            is_preset=category.is_preset,
        )
    )


@router.put("/{category_id}", response_model=DataResponse[CategoryOut])
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "分类不存在"},
        )
    if category.is_preset:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CATEGORY_PRESET_IMMUTABLE",
                "message": "预设分类不可重命名",
            },
        )
    if await _name_taken(db, data.name, exclude_id=category_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "CATEGORY_NAME_DUPLICATE", "message": "分类名已存在"},
        )
    category.name = data.name
    await db.commit()
    await db.refresh(category)
    return wrap_data(
        CategoryOut(
            id=category.id,
            name=category.name,
            icon=category.icon,
            color=category.color,
            is_preset=category.is_preset,
        )
    )


@router.delete("/{category_id}", response_model=DataResponse[dict])
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "分类不存在"},
        )
    if category.is_preset:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CATEGORY_PRESET_IMMUTABLE",
                "message": "预设分类不可删除",
            },
        )
    await db.delete(category)
    await db.commit()
    return wrap_data({"success": True})
