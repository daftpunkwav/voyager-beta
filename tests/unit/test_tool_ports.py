"""ToolPorts SQLAlchemy 适配器冒烟测试。"""
from __future__ import annotations

import os

import pytest
from api_backend.config import get_settings
from api_backend.database import get_session_factory, init_db, reset_database
from api_backend.models.project import Project
from api_backend.ports.sqlalchemy_adapters import build_tool_ports


@pytest.fixture
async def ports_db(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'ports.db'}"
    get_settings.cache_clear()
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        project = Project(
            name="owner/demo",
            url="https://github.com/owner/demo",
            source="github",
            progress="learning",
            language="Python",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        yield build_tool_ports(session), project


@pytest.mark.asyncio
async def test_project_search_and_owned(ports_db):
    ports, project = ports_db
    rows = await ports.projects.search(query="demo", language="Python")
    assert len(rows) == 1
    assert rows[0].id == project.id
    owned = await ports.projects.get_owned(project.id)
    assert owned is not None
    by_name = await ports.projects.get_by_name("owner/demo")
    assert by_name is not None


@pytest.mark.asyncio
async def test_notes_create_list_count(ports_db):
    ports, project = ports_db
    note = await ports.notes.create(
        project_id=project.id,
        title="t",
        content="body",
    )
    await ports.commit()
    listed = await ports.notes.list_for_user(project_id=project.id)
    assert len(listed) == 1
    assert listed[0].id == note.id
    assert await ports.notes.count_for_user() == 1


@pytest.mark.asyncio
async def test_category_ensure_and_tags(ports_db):
    ports, project = ports_db
    cat, created = await ports.categories.ensure("学习")
    assert created is True
    await ports.commit()
    cat2, created2 = await ports.categories.ensure("学习")
    assert created2 is False
    assert cat2.id == cat.id

    tags = await ports.tags.ensure_many(["a", "b"])
    await ports.commit()
    assert len(tags) == 2
    result = await ports.tags.set_on_project(project.id, [t.id for t in tags])
    assert result is not None
    assert set(result.tag_ids) == {t.id for t in tags}
