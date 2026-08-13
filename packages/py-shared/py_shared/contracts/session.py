"""业务服务契约 —— 会话项目绑定查询。"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class SessionQueryPort(Protocol):
    """api_backend.services.agent_service.get_session_project_ids 的契约。"""

    async def get_session_project_ids(
        self, db: Any, session_id: UUID
    ) -> list[UUID]: ...
