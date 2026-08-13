"""总览页数据聚合 —— 从真实数据库派生（本地单机）"""
from datetime import datetime

from api_backend.models.agent import AgentSession
from api_backend.models.note import Note
from api_backend.models.project import Project
from api_backend.schemas.overview import (
    ActivityItemOut,
    OverviewRecentNoteOut,
    RecommendedProjectOut,
    TrendingRepoOut,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _iso(dt: datetime | None) -> str:
    if not dt:
        return datetime.utcnow().isoformat() + "Z"
    return dt.isoformat() + ("Z" if not dt.tzinfo else "")


async def list_activities(db: AsyncSession, limit: int = 20) -> list[ActivityItemOut]:
    items: list[ActivityItemOut] = []

    projects = (
        await db.execute(
            select(Project).order_by(Project.imported_at.desc()).limit(limit)
        )
    ).scalars().all()
    for p in projects:
        items.append(
            ActivityItemOut(
                id=f"act_import_{p.id}",
                type="import",
                title=f"导入项目 {p.name}",
                description=p.description or "新项目已加入库",
                created_at=_iso(p.imported_at),
                project_id=str(p.id),
            )
        )

    notes = (
        await db.execute(
            select(Note).order_by(Note.updated_at.desc()).limit(limit)
        )
    ).scalars().all()
    for n in notes:
        items.append(
            ActivityItemOut(
                id=f"act_note_{n.id}",
                type="note",
                title=f"笔记：{n.title}",
                description=(n.content or "")[:80],
                created_at=_iso(n.updated_at or n.created_at),
                project_id=str(n.project_id),
            )
        )

    sessions = (
        await db.execute(
            select(AgentSession).order_by(AgentSession.updated_at.desc()).limit(limit)
        )
    ).scalars().all()
    for s in sessions:
        items.append(
            ActivityItemOut(
                id=f"act_agent_{s.id}",
                type="agent",
                title=f"Agent 对话：{s.title or '新对话'}",
                description=f"由 {s.active_agent or 'hub'} 处理",
                created_at=_iso(s.updated_at or s.created_at),
            )
        )

    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:limit]


async def list_recent_notes(
    db: AsyncSession, limit: int = 5
) -> list[OverviewRecentNoteOut]:
    result = await db.execute(
        select(Note, Project.name)
        .join(Project, Note.project_id == Project.id)
        .order_by(Note.updated_at.desc())
        .limit(limit)
    )
    out: list[OverviewRecentNoteOut] = []
    for note, project_name in result.all():
        out.append(
            OverviewRecentNoteOut(
                id=str(note.id),
                project_id=str(note.project_id),
                project_name=project_name,
                title=note.title,
                updated_at=_iso(note.updated_at or note.created_at),
            )
        )
    return out


async def list_recommended(
    db: AsyncSession, limit: int = 6
) -> list[RecommendedProjectOut]:
    result = await db.execute(
        select(Project)
        .where(Project.progress.in_(["none", "learning"]))
        .order_by(Project.stars.desc())
        .limit(limit)
    )
    items: list[RecommendedProjectOut] = []
    for p in result.scalars().all():
        items.append(
            RecommendedProjectOut(
                id=f"rec_{p.id}",
                project_id=str(p.id),
                name=p.name,
                url=p.url,
                description=p.description,
                language=p.language,
                stars=p.stars,
                reason="根据 Stars 与当前学习进度推荐",
                recommended_by="navigator",
            )
        )
    return items


async def list_trending(language: str = "", period: str = "weekly") -> list[TrendingRepoOut]:
    """通过 GitHub Search API 近似 trending。"""
    from api_backend.services.github_client import list_trending_approx

    _ = period
    raw = await list_trending_approx(language=language, limit=12)
    out: list[TrendingRepoOut] = []
    for i, r in enumerate(raw):
        full = r.get("name") or ""
        if "/" in full:
            owner, repo = full.split("/", 1)
        else:
            owner, repo = "unknown", full or "repo"
        out.append(
            TrendingRepoOut(
                owner=owner,
                repo=repo,
                url=r.get("url") or "",
                description=r.get("description"),
                language=r.get("language"),
                stars=int(r.get("stars") or 0),
                stars_today=None,
                rank=i + 1,
            )
        )
    return out
