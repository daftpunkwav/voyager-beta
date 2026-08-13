"""Graph Runtime 依赖注入上下文。

graph_engine_runtime 保持零 api_backend 依赖：全部外部依赖（配置/DB 会话工厂/
GitHub token/AppState 服务）经 GraphRuntimeContext 由宿主（api_backend）注入。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from py_shared.contracts.app_state import AppStateServicePort

# services/graph_engine/graph_engine_runtime/context.py → parents[3] = 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[3]


class GraphSettings(Protocol):
    """graph 运行所需的配置子集（由宿主 api_backend 的 Settings 实现）。"""

    graph_allowed_root: str
    graph_engine_url: str
    graph_engine_bin: str
    graph_cache_dir: str
    graph_auto_start: bool
    repo_cache_quota_gb: float
    index_concurrency: int
    git_clone_timeout_sec: float
    graph_index_timeout_sec: float


class SessionFactoryProvider(Protocol):
    def __call__(self) -> Any:
        """返回 async_sessionmaker[AsyncSession]（宿主 api_backend.database）。"""


class GitHubTokenProvider(Protocol):
    def __call__(self, state: Any) -> tuple[str | None, str | None]:
        """从 AppState 读取首选 GitHub token，返回 (username, decrypted_pat)。"""


@dataclass(frozen=True)
class GraphRuntimeContext:
    """graph_engine_runtime 的全部外部依赖（EmbeddedGraphRuntime 构造时注入）。"""

    settings: GraphSettings
    repo_root: Path = _REPO_ROOT
    # 以下三项可空：host 未注入时，索引流水线跳过对应步骤（token 匿名 clone）
    get_session_factory: SessionFactoryProvider | None = None
    primary_token: GitHubTokenProvider | None = None
    app_state_service: AppStateServicePort | None = None


_global: GraphRuntimeContext | None = None


def set_runtime_context(ctx: GraphRuntimeContext) -> None:
    """EmbeddedGraphRuntime 构造时注册全局上下文（进程内单例，幂等）。"""
    global _global
    _global = ctx


def get_runtime_context() -> GraphRuntimeContext:
    if _global is None:
        raise RuntimeError(
            "graph_engine_runtime 未初始化：请先构造 EmbeddedGraphRuntime 注入上下文"
        )
    return _global
