"""agent_core 业务服务契约容器。

agent_core 只依赖 py-shared 的 Protocol（py_shared.contracts）；
宿主（agent_runtime 的 EmbeddedAgentRuntime / 独立进程入口 / 测试 conftest）
在启动时调用 register_agent_services() 注入 api_backend 的实现。
"""
from __future__ import annotations

from typing import Any

from py_shared.contracts.app_state import AppStateServicePort
from py_shared.contracts.github import GitHubClientPort
from py_shared.contracts.llm_usage import LLMUsagePort
from py_shared.contracts.profile import ProfileServicePort
from py_shared.contracts.session import SessionQueryPort
from py_shared.contracts.settings import SettingsServicePort


class AgentServices:
    """agent_core 访问宿主业务服务的统一入口（未注入时属性为 None）。"""

    def __init__(self) -> None:
        self.app_state: AppStateServicePort | None = None
        self.profile: ProfileServicePort | None = None
        self.settings: SettingsServicePort | None = None
        self.github: GitHubClientPort | None = None
        self.llm_usage: LLMUsagePort | None = None
        self.session_query: SessionQueryPort | None = None


_services = AgentServices()


def register_agent_services(services: AgentServices) -> None:
    """注入宿主实现（幂等；宿主 lifespan / agent_runtime 入口 / 测试 conftest）。"""
    global _services
    _services = services


def get_services() -> AgentServices:
    return _services


def _require(name: str) -> Any:
    svc = getattr(_services, name)
    if svc is None:
        raise RuntimeError(f"agent_core 宿主服务未注入: {name}（请先 register_agent_services）")
    return svc


def app_state() -> AppStateServicePort:
    return _require("app_state")


def profile() -> ProfileServicePort:
    return _require("profile")


def settings() -> SettingsServicePort:
    return _require("settings")


def github() -> GitHubClientPort:
    return _require("github")


def llm_usage() -> LLMUsagePort:
    return _require("llm_usage")


def session_query() -> SessionQueryPort:
    return _require("session_query")
