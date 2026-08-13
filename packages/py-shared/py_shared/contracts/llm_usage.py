"""业务服务契约 —— LLM 用量解析与记录。"""
from __future__ import annotations

from typing import Any, Protocol


class LLMUsagePort(Protocol):
    """api_backend llm_usage_parse / llm_usage_service 的契约。"""

    def parse_usage_details(self, raw: Any) -> dict[str, int]: ...

    def record_parsed_usage_fire_and_forget(
        self,
        usage: dict[str, Any],
        *,
        model: str,
        provider: str = "",
    ) -> None: ...
