"""设置读取协议:master/spawner 只依赖"读设置"这一最小面(脱耦)。"""

from __future__ import annotations

from typing import Any, Protocol


class SettingsReader(Protocol):
    def get(self, key: str) -> Any: ...
