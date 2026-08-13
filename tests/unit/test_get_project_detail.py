"""get_project_detail：UUID / owner/repo 兼容与错误提示"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agent_core.tools.builtin import get_project_detail
from api_backend.config import get_settings
from api_backend.database import get_session_factory, init_db, reset_database
from api_backend.models.project import Project


@pytest.fixture
async def detail_ctx(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'get_project_detail.db'}"
    get_settings.cache_clear()
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        project = Project(
            name="langchain-ai/langgraph",
            url="https://github.com/langchain-ai/langgraph",
            source="github",
            progress="none",
            description="Agent orchestration",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        ctx = SimpleNamespace(
            db=session,
            session_id=uuid4(),
            agent_id="scout",
            permissions={"allow_github_api": True},
            memory=None,
            extra={},
        )
        yield ctx, project


@pytest.mark.asyncio
async def test_get_project_detail_by_uuid(detail_ctx):
    ctx, project = detail_ctx
    result = await get_project_detail(project_id=str(project.id), context=ctx)
    assert result["id"] == str(project.id)
    assert result["name"] == "langchain-ai/langgraph"


@pytest.mark.asyncio
async def test_get_project_detail_resolves_owner_repo_in_library(detail_ctx):
    ctx, project = detail_ctx
    result = await get_project_detail(
        project_id="langchain-ai/langgraph",
        context=ctx,
    )
    assert result["id"] == str(project.id)
    assert result["name"] == "langchain-ai/langgraph"


@pytest.mark.asyncio
async def test_get_project_detail_owner_repo_missing_gives_hint(detail_ctx):
    ctx, _project = detail_ctx
    result = await get_project_detail(
        project_id="crewAIInc/crewAI",
        context=ctx,
    )
    assert result["error"] == "无效 project_id"
    assert "fetch_github_repo" in result["hint"]
    assert result["full_name"] == "crewAIInc/crewAI"


@pytest.mark.asyncio
async def test_get_project_detail_rejects_garbage_id(detail_ctx):
    ctx, _project = detail_ctx
    result = await get_project_detail(project_id="not-a-uuid-or-repo", context=ctx)
    assert result["error"] == "无效 project_id"
    assert "UUID" in result["hint"]
