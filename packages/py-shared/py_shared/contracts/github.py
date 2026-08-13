"""业务服务契约 —— GitHub 客户端。"""
from __future__ import annotations

from typing import Any, Protocol


class GitHubClientPort(Protocol):
    """api_backend.services.github_client 的契约。"""

    async def fetch_repo_info(
        self, owner: str, repo: str, token: str | None = None
    ) -> dict[str, Any]: ...

    async def fetch_readme_text(self, owner: str, repo: str) -> str | None: ...
