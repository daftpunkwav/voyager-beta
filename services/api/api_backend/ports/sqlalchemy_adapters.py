"""ToolPorts 的 SQLAlchemy 适配器（本地单机，无 user 维度）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from api_backend.models.agent import AgentSession
from api_backend.models.category import Category
from api_backend.models.note import Note
from api_backend.models.project import Project, Tag
from api_backend.ports import (
    CategoryPort,
    GraphPort,
    NotePort,
    ProjectPort,
    SessionPort,
    TagPort,
    ToolPorts,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SqlAlchemyProjectPort:
    db: AsyncSession

    async def get_owned(self, project_id: UUID) -> Project | None:
        return await self.db.get(Project, project_id)

    async def get_by_name(self, name: str) -> Project | None:
        rows = await self.db.execute(
            select(Project).where(Project.name == name).limit(1)
        )
        return rows.scalars().first()

    async def list_for_user(self, *, limit: int = 50) -> list[Project]:
        rows = await self.db.execute(
            select(Project).order_by(Project.updated_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def search(
        self,
        *,
        query: str = "",
        language: str = "",
        progress: str = "",
        limit: int = 50,
    ) -> list[Project]:
        stmt = select(Project)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(Project.name.ilike(like), Project.description.ilike(like))
            )
        if language:
            stmt = stmt.where(Project.language == language)
        if progress:
            stmt = stmt.where(Project.progress == progress)
        stmt = stmt.limit(min(limit or 50, 50))
        rows = await self.db.execute(stmt)
        return list(rows.scalars().all())

    async def update_fields(self, project: Project, **fields: Any) -> Project:
        for k, v in fields.items():
            if hasattr(project, k):
                setattr(project, k, v)
        await self.db.flush()
        return project

    async def import_repos(self, items: list[Any]) -> Any:
        from api_backend.services.project_service import import_repos

        return await import_repos(self.db, items)


@dataclass
class SqlAlchemyNotePort:
    db: AsyncSession

    async def create(
        self,
        *,
        project_id: UUID | None,
        title: str,
        content: str,
    ) -> Note:
        if project_id is None:
            raise ValueError("project_id required")
        note = Note(
            project_id=project_id,
            title=title,
            content=content,
        )
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def update(self, note_id: UUID, **fields: Any) -> Note | None:
        note = await self.db.get(Note, note_id)
        if not note:
            return None
        for k, v in fields.items():
            if hasattr(note, k):
                setattr(note, k, v)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def list_for_project(
        self, project_id: UUID, *, limit: int = 20
    ) -> list[Note]:
        return await self.list_for_user(project_id=project_id, limit=limit)

    async def list_for_user(
        self,
        *,
        project_id: UUID | None = None,
        limit: int = 30,
    ) -> list[Note]:
        stmt = select(Note)
        if project_id is not None:
            stmt = stmt.where(Note.project_id == project_id)
        stmt = stmt.order_by(Note.updated_at.desc()).limit(limit)
        rows = await self.db.execute(stmt)
        return list(rows.scalars().all())

    async def count_for_user(self) -> int:
        from sqlalchemy import func

        result = await self.db.execute(select(func.count()).select_from(Note))
        return int(result.scalar_one() or 0)


@dataclass
class SqlAlchemyCategoryPort:
    db: AsyncSession

    async def list_visible(self) -> list[Category]:
        rows = await self.db.execute(select(Category))
        return list(rows.scalars().all())

    async def get_visible(self, category_id: UUID) -> Category | None:
        return await self.db.get(Category, category_id)

    async def ensure(
        self,
        name: str,
        *,
        icon: str | None = None,
        color: str | None = None,
    ) -> tuple[Category, bool]:
        name_s = (name or "").strip()[:64]
        rows = await self.db.execute(select(Category).where(Category.name == name_s))
        existing = rows.scalars().first()
        if existing:
            return existing, False
        cat = Category(
            name=name_s,
            icon=icon or None,
            color=color or None,
            is_preset=False,
        )
        self.db.add(cat)
        await self.db.flush()
        await self.db.refresh(cat)
        return cat, True


@dataclass
class SqlAlchemyTagPort:
    db: AsyncSession

    async def list_for_user(self) -> list[Tag]:
        rows = await self.db.execute(select(Tag))
        return list(rows.scalars().all())

    async def list_with_counts(self) -> list[Any]:
        from api_backend.services.tag_service import list_user_tags

        return await list_user_tags(self.db)

    async def ensure_many(self, names: list[str]) -> list[Tag]:
        out: list[Tag] = []
        for name in names:
            n = (name or "").strip()[:64]
            if not n:
                continue
            rows = await self.db.execute(select(Tag).where(Tag.name == n))
            tag = rows.scalars().first()
            if not tag:
                tag = Tag(name=n)
                self.db.add(tag)
                await self.db.flush()
            out.append(tag)
        return out

    async def validate_owned_ids(self, tag_ids: list[UUID]) -> list[UUID]:
        if not tag_ids:
            return []
        owned = await self.db.execute(select(Tag.id).where(Tag.id.in_(tag_ids)))
        valid = {row[0] for row in owned.all()}
        return [tid for tid in tag_ids if tid in valid]

    async def get_project_tag_ids(self, project_id: UUID) -> list[UUID]:
        from api_backend.services.tag_service import get_project_tag_ids

        raw = await get_project_tag_ids(self.db, project_id)
        return [UUID(s) for s in raw]

    async def set_on_project(
        self, project_id: UUID, tag_ids: list[UUID]
    ) -> Any | None:
        from api_backend.services.tag_service import set_project_tags

        return await set_project_tags(self.db, project_id, tag_ids)


@dataclass
class SqlAlchemySessionPort:
    db: AsyncSession

    async def get_owned(self, session_id: UUID) -> AgentSession | None:
        return await self.db.get(AgentSession, session_id)

    async def mutate_projects(
        self,
        session: AgentSession,
        action: str,
        project_ids: list[UUID],
    ) -> list[UUID]:
        from api_backend.services.agent_service import (
            add_session_project,
            get_session_project_ids,
            remove_session_project,
            set_session_projects,
        )

        act = (action or "add").strip().lower()
        if act == "set":
            return await set_session_projects(self.db, session, project_ids)
        if act == "remove":
            ids: list[UUID] = []
            for pid in project_ids:
                ids = await remove_session_project(self.db, session, pid)
            if not project_ids:
                ids = await get_session_project_ids(self.db, session.id)
            return ids
        ids = []
        for pid in project_ids:
            ids = await add_session_project(self.db, session, pid)
        if not project_ids:
            ids = await get_session_project_ids(self.db, session.id)
        return ids


@dataclass
class SqlAlchemyGraphPort:
    db: AsyncSession

    async def build(
        self,
        *,
        min_similarity: float = 0.3,
        max_edges: int = 20,
    ) -> dict[str, Any]:
        from api_backend.services.graph_service import build_graph

        return await build_graph(
            self.db,
            min_similarity=min_similarity,
            max_edges=max_edges,
        )


@dataclass
class SqlAlchemyToolPorts:
    db: AsyncSession

    def __post_init__(self) -> None:
        self.projects: ProjectPort = SqlAlchemyProjectPort(self.db)
        self.notes: NotePort = SqlAlchemyNotePort(self.db)
        self.categories: CategoryPort = SqlAlchemyCategoryPort(self.db)
        self.tags: TagPort = SqlAlchemyTagPort(self.db)
        self.sessions: SessionPort = SqlAlchemySessionPort(self.db)
        self.graph: GraphPort = SqlAlchemyGraphPort(self.db)

    async def commit(self) -> None:
        await self.db.commit()


def build_tool_ports(db: AsyncSession) -> ToolPorts:
    return SqlAlchemyToolPorts(db)
