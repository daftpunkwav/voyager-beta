"""Agent 写库工具：笔记 / 分类 / 标签 / 进度"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agent_core.agents.registry import AGENT_DEFINITIONS
from agent_core.tools.builtin import (
    create_note_tool,
    ensure_tools_loaded,
    set_project_category,
    set_project_tags_tool,
    update_project_progress,
)
from agent_core.tools.registry import global_registry
from api_backend.config import get_settings
from api_backend.database import get_session_factory, init_db, reset_database
from api_backend.models.project import Project


@pytest.fixture
async def tool_ctx(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'write_tools.db'}"
    get_settings.cache_clear()
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        project = Project(
            name="owner/demo",
            url="https://github.com/owner/demo",
            source="github",
            progress="none",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        ctx = SimpleNamespace(
            db=session,
            session_id=uuid4(),
            agent_id="scribe",
            permissions={
                "allow_note_write": True,
                "allow_project_write": True,
            },
            memory=None,
            extra={},
        )
        yield ctx, project


@pytest.mark.asyncio
async def test_create_note_persists(tool_ctx):
    ctx, project = tool_ctx
    ctx.agent_id = "scribe"
    result = await create_note_tool(
        context=ctx,
        project_id=str(project.id),
        title="对比学习笔记",
        content="## 要点\n\n- a\n- b\n",
        compare_project_ids=[],
    )
    assert result.get("ok") is True
    assert result.get("__action__") == "note_created"
    assert result["resource"]["title"] == "对比学习笔记"
    note_id = result["resource"]["id"]

    from uuid import UUID

    from api_backend.models.note import Note

    note = await ctx.db.get(Note, UUID(note_id))
    assert note is not None
    assert note.project_id == project.id
    assert "要点" in (note.content or "")


@pytest.mark.asyncio
async def test_set_category_and_tags_and_progress(tool_ctx):
    ctx, project = tool_ctx
    ctx.agent_id = "curator"

    cat = await set_project_category(
        context=ctx,
        project_id=str(project.id),
        category_name="游戏引擎",
    )
    assert cat.get("__action__") == "category_applied"
    assert cat["resource"]["category_name"] == "游戏引擎"

    tags = await set_project_tags_tool(
        context=ctx,
        project_id=str(project.id),
        tag_names=["引擎", "Godot"],
        mode="replace",
    )
    assert tags.get("__action__") == "tags_applied"
    assert len(tags["resource"]["tags"]) == 2

    prog = await update_project_progress(
        context=ctx,
        project_id=str(project.id),
        progress="mastered",
    )
    assert prog.get("__action__") == "progress_updated"
    await ctx.db.refresh(project)
    assert project.progress == "mastered"
    assert project.category_id is not None


@pytest.mark.asyncio
async def test_write_tools_permission_blocked(tool_ctx):
    ctx, project = tool_ctx
    ensure_tools_loaded()
    ctx.agent_id = "scribe"
    ctx.permissions = {"allow_note_write": False}
    result = await global_registry.execute(
        "create_note",
        {
            "project_id": str(project.id),
            "title": "x",
            "content": "y",
        },
        ctx,
    )
    assert "error" in result
    assert "allow_note_write" in result["error"]


@pytest.mark.asyncio
async def test_set_project_tags_rejects_foreign_tag_id(tool_ctx):
    ctx, project = tool_ctx
    ctx.agent_id = "curator"
    ok = await set_project_tags_tool(
        context=ctx,
        project_id=str(project.id),
        tag_names=["保留标签"],
        mode="replace",
    )
    assert ok.get("__action__") == "tags_applied"
    assert len(ok["resource"]["tags"]) == 1

    bad = await set_project_tags_tool(
        context=ctx,
        project_id=str(project.id),
        tag_ids=[str(uuid4())],
        mode="replace",
    )
    assert "error" in bad
    assert "未改动" in bad["error"]

    from api_backend.services.tag_service import get_project_tag_ids

    ids = await get_project_tag_ids(ctx.db, project.id)
    assert len(ids) == 1


def test_scribe_curator_whitelist_includes_write_tools():
    assert "create_note" in AGENT_DEFINITIONS["scribe"].tools
    assert "update_note" in AGENT_DEFINITIONS["scribe"].tools
    assert "set_project_category" in AGENT_DEFINITIONS["curator"].tools
    assert "set_project_tags" in AGENT_DEFINITIONS["curator"].tools
    assert "import_github_repos" in AGENT_DEFINITIONS["curator"].tools
    assert "update_project_progress" in AGENT_DEFINITIONS["navigator"].tools
    assert "create_note" not in AGENT_DEFINITIONS["hub"].tools
    assert "set_project_category" not in AGENT_DEFINITIONS["hub"].tools
