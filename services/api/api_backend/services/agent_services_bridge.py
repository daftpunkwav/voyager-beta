"""api_backend → agent_core 业务服务契约的 Embedded Adapter。

将 api_backend 各业务服务的模块级函数包装为 py_shared.contracts 的
Protocol 实现，由宿主（api_backend.main lifespan / agent_runtime 入口 / 测试）
经 register_agent_services() 注入 agent_core。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from agent_core.services import AgentServices


class _AppStateService:
    def __init__(self, get_or_create, ensure_singleton):
        self._get_or_create = get_or_create
        self._ensure_singleton = ensure_singleton

    async def get_or_create_app_state(self, db: Any) -> Any:
        return await self._get_or_create(db)

    async def ensure_singleton_rows(self, db: Any) -> None:
        return await self._ensure_singleton(db)


class _ProfileService:
    def __init__(
        self,
        get_or_create_profile,
        profile_to_out,
        get_user_profile,
        select_learner_info,
        learner_info_fields,
    ):
        self._get_or_create_profile = get_or_create_profile
        self._profile_to_out = profile_to_out
        self._get_user_profile = get_user_profile
        self._select_learner_info = select_learner_info
        self.LEARNER_INFO_FIELDS = learner_info_fields

    async def get_or_create_profile(self, db: Any) -> Any:
        return await self._get_or_create_profile(db)

    def profile_to_out(self, row: Any) -> Any:
        return self._profile_to_out(row)

    async def get_user_profile(self, db: Any) -> Any:
        return await self._get_user_profile(db)

    def select_learner_info(self, profile: Any, fields: list[str]) -> dict:
        return self._select_learner_info(profile, fields)


class _SettingsService:
    def __init__(self, ensure_providers):
        self._ensure_providers = ensure_providers

    def ensure_providers(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        return self._ensure_providers(raw)


class _GitHubService:
    def __init__(self, fetch_repo_info, fetch_readme_text):
        self._fetch_repo_info = fetch_repo_info
        self._fetch_readme_text = fetch_readme_text

    async def fetch_repo_info(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]:
        return await self._fetch_repo_info(owner, repo, token=token)

    async def fetch_readme_text(self, owner: str, repo: str) -> str | None:
        return await self._fetch_readme_text(owner, repo)


class _LLMUsageService:
    def __init__(self, parse_usage_details, record_parsed):
        self._parse = parse_usage_details
        self._record = record_parsed

    def parse_usage_details(self, raw: Any) -> dict[str, int]:
        return self._parse(raw)

    def record_parsed_usage_fire_and_forget(
        self, usage: dict[str, Any], *, model: str, provider: str = ""
    ) -> None:
        self._record(usage, model=model, provider=provider)


class _SessionQueryService:
    def __init__(self, fn):
        self._fn = fn

    async def get_session_project_ids(
        self, db: Any, session_id: UUID
    ) -> list[UUID]:
        return await self._fn(db, session_id)


def build_agent_services() -> AgentServices:
    """组装 api_backend 全部业务服务的 Embedded Adapter。"""
    from api_backend.services.agent_service import get_session_project_ids
    from api_backend.services.app_state_service import (
        ensure_singleton_rows,
        get_or_create_app_state,
    )
    from api_backend.services.github_client import (
        fetch_readme_text,
        fetch_repo_info,
    )
    from api_backend.services.llm_usage_parse import parse_usage_details
    from api_backend.services.llm_usage_service import (
        record_parsed_usage_fire_and_forget,
    )
    from api_backend.services.profile_service import (
        LEARNER_INFO_FIELDS,
        get_or_create_profile,
        get_user_profile,
        profile_to_out,
        select_learner_info,
    )
    from api_backend.services.settings_service import ensure_providers

    svc = AgentServices()
    svc.app_state = _AppStateService(get_or_create_app_state, ensure_singleton_rows)
    svc.profile = _ProfileService(
        get_or_create_profile,
        profile_to_out,
        get_user_profile,
        select_learner_info,
        LEARNER_INFO_FIELDS,
    )
    svc.settings = _SettingsService(ensure_providers)
    svc.github = _GitHubService(fetch_repo_info, fetch_readme_text)
    svc.llm_usage = _LLMUsageService(
        parse_usage_details, record_parsed_usage_fire_and_forget
    )
    svc.session_query = _SessionQueryService(get_session_project_ids)
    return svc
