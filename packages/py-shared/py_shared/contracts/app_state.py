"""业务服务契约 —— AppState 单例行访问。"""
from __future__ import annotations

from typing import Any, Protocol


class AppStateServicePort(Protocol):
    """api_backend.services.app_state_service 的契约。"""

    async def get_or_create_app_state(self, db: Any) -> Any: ...

    async def ensure_singleton_rows(self, db: Any) -> None: ...
