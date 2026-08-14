"""工作记忆(§9.11):当前会话,进程内存,有界。"""

from __future__ import annotations

from collections import deque
from typing import Any


class WorkingMemory:
    def __init__(self, maxlen: int = 200) -> None:
        self._messages: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self.current_task: str | None = None

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})

    def recent(self, n: int = 20) -> list[dict[str, Any]]:
        items = list(self._messages)
        return items[-n:]

    def clear(self) -> None:
        self._messages.clear()
        self.current_task = None
