"""项目 service 业务逻辑测试"""
import os

import pytest
from api_backend.config import get_settings
from api_backend.database import get_session_factory, init_db, reset_database
from api_backend.schemas.project import ImportRepoItem
from api_backend.services.project_service import import_repos, project_stats


@pytest.fixture
async def db_session(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'biz.db'}"
    get_settings.cache_clear()
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.mark.asyncio
async def test_import_repos_dedup(db_session):
    session = db_session
    repos = [
        ImportRepoItem(owner="a", repo="b", url="https://github.com/a/b"),
        ImportRepoItem(owner="a", repo="b", url="https://github.com/a/b"),
    ]
    result = await import_repos(session, repos)
    assert result.succeeded == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_project_stats_empty(db_session):
    session = db_session
    stats = await project_stats(session)
    assert stats.total == 0
    assert stats.by_progress == {}
