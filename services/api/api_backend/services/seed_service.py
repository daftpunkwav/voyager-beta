"""
数据库种子数据
"""
from api_backend.models.category import Category
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PRESET_CATEGORIES = [
    {"name": "前端", "icon": "🎨", "color": "#3b82f6"},
    {"name": "后端", "icon": "⚙️", "color": "#10b981"},
    {"name": "AI/ML", "icon": "🤖", "color": "#8b5cf6"},
    {"name": "DevOps", "icon": "🔧", "color": "#f59e0b"},
    {"name": "其他", "icon": "📦", "color": "#6b7280"},
]


async def seed_preset_categories(db: AsyncSession) -> None:
    result = await db.execute(select(Category).where(Category.is_preset.is_(True)))
    if result.scalars().first():
        return
    for item in PRESET_CATEGORIES:
        db.add(Category(name=item["name"], icon=item["icon"], color=item["color"], is_preset=True))
    await db.commit()
