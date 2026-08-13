"""标签业务逻辑（本地单机，无 user 维度）"""
from uuid import UUID

from api_backend.models.project import Project, Tag, project_tags
from api_backend.schemas.tag import SetProjectTagsOut, TagOut
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_user_tags(db: AsyncSession) -> list[TagOut]:
    result = await db.execute(select(Tag))
    tags = result.scalars().all()
    items: list[TagOut] = []
    for tag in tags:
        count_q = select(func.count()).select_from(project_tags).where(
            project_tags.c.tag_id == tag.id
        )
        count = (await db.execute(count_q)).scalar_one()
        items.append(TagOut(id=tag.id, name=tag.name, count=count))
    return items


async def create_tag(db: AsyncSession, name: str) -> TagOut:
    tag = Tag(name=name)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagOut(id=tag.id, name=tag.name, count=0)


async def delete_tag(db: AsyncSession, tag_id: UUID) -> bool:
    tag = await db.get(Tag, tag_id)
    if not tag:
        return False
    await db.execute(delete(project_tags).where(project_tags.c.tag_id == tag_id))
    await db.delete(tag)
    await db.commit()
    return True


async def set_project_tags(
    db: AsyncSession, project_id: UUID, tag_ids: list[UUID]
) -> SetProjectTagsOut | None:
    project = await db.get(Project, project_id)
    if not project:
        return None
    if tag_ids:
        owned = await db.execute(select(Tag.id).where(Tag.id.in_(tag_ids)))
        valid_ids = {row[0] for row in owned.all()}
        tag_ids = [tid for tid in tag_ids if tid in valid_ids]
    await db.execute(delete(project_tags).where(project_tags.c.project_id == project_id))
    if tag_ids:
        await db.execute(
            insert(project_tags),
            [{"project_id": project_id, "tag_id": tid} for tid in tag_ids],
        )
    await db.commit()
    return SetProjectTagsOut(project_id=project_id, tag_ids=tag_ids)


async def get_project_tag_ids(db: AsyncSession, project_id: UUID) -> list[str]:
    result = await db.execute(
        select(project_tags.c.tag_id).where(project_tags.c.project_id == project_id)
    )
    return [str(row[0]) for row in result.all()]
