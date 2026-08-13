"""SQLAlchemy 端口协议 —— 工具层不直接依赖 AsyncSession/ORM（无 user 维度）。"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class ProjectPort(Protocol):
    async def get_owned(self, project_id: UUID) -> Any | None: ...

    async def get_by_name(self, name: str) -> Any | None: ...

    async def list_for_user(self, *, limit: int = 50) -> list[Any]: ...

    async def search(
        self,
        *,
        query: str = "",
        language: str = "",
        progress: str = "",
        limit: int = 50,
    ) -> list[Any]: ...

    async def update_fields(self, project: Any, **fields: Any) -> Any: ...

    async def import_repos(self, items: list[Any]) -> Any: ...


class NotePort(Protocol):
    async def create(
        self,
        *,
        project_id: UUID | None,
        title: str,
        content: str,
    ) -> Any: ...

    async def update(self, note_id: UUID, **fields: Any) -> Any | None: ...

    async def list_for_project(
        self, project_id: UUID, *, limit: int = 20
    ) -> list[Any]: ...

    async def list_for_user(
        self,
        *,
        project_id: UUID | None = None,
        limit: int = 30,
    ) -> list[Any]: ...

    async def count_for_user(self) -> int: ...


class CategoryPort(Protocol):
    async def list_visible(self) -> list[Any]: ...

    async def get_visible(self, category_id: UUID) -> Any | None: ...

    async def ensure(
        self,
        name: str,
        *,
        icon: str | None = None,
        color: str | None = None,
    ) -> tuple[Any, bool]: ...


class TagPort(Protocol):
    async def list_for_user(self) -> list[Any]: ...

    async def list_with_counts(self) -> list[Any]: ...

    async def ensure_many(self, names: list[str]) -> list[Any]: ...

    async def validate_owned_ids(self, tag_ids: list[UUID]) -> list[UUID]: ...

    async def get_project_tag_ids(self, project_id: UUID) -> list[UUID]: ...

    async def set_on_project(
        self, project_id: UUID, tag_ids: list[UUID]
    ) -> Any | None: ...


class SessionPort(Protocol):
    async def get_owned(self, session_id: UUID) -> Any | None: ...

    async def mutate_projects(
        self,
        session: Any,
        action: str,
        project_ids: list[UUID],
    ) -> list[UUID]: ...


class GraphPort(Protocol):
    async def build(
        self,
        *,
        min_similarity: float = 0.3,
        max_edges: int = 20,
    ) -> dict[str, Any]: ...


class ToolPorts(Protocol):
    """一次 Agent 运行可注入的仓储端口集合。"""

    projects: ProjectPort
    notes: NotePort
    categories: CategoryPort
    tags: TagPort
    sessions: SessionPort
    graph: GraphPort

    async def commit(self) -> None: ...
