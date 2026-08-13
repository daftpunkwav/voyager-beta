"""业务服务契约 —— 用户设置（LLM 多供应商）。"""
from __future__ import annotations

from typing import Any, Protocol


class SettingsServicePort(Protocol):
    """api_backend.services.settings_service.ensure_providers 的契约。"""

    def ensure_providers(self, raw: dict[str, Any]) -> list[dict[str, Any]]: ...
