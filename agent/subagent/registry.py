"""用户自建 subagent 的注册与加载(§9.4.4)。

定义存 runtime-data/subagents/*.json;master 派遣时按名取用。
用户可自定义:模式、人格、能力面(允许的工具)、权限档位(scopes)、触发方式。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from platform_contracts import ErrorSuffix, ServiceError

from agent.subagent.modes import Mode

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DOMAIN = "agent"


@dataclass(frozen=True)
class SubagentDef:
    name: str
    description: str
    mode: str = "react"
    persona: str = ""  # 人格预设 key(可空)
    allowed_tools: tuple[str, ...] | None = None  # None=不裁剪
    scopes: tuple[str, ...] = ()
    trigger: str = "manual"  # manual | event:<pattern>

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"名称须为小写 snake_case: {self.name}")
        valid_modes = {m.value for m in Mode}
        if self.mode not in valid_modes:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"未知模式: {self.mode}(可选: {sorted(valid_modes)})",
            )
        # json 往返后 list 归一化为 tuple(frozen dataclass 走 object.__setattr__)
        object.__setattr__(self, "scopes", tuple(self.scopes))
        if self.allowed_tools is not None:
            object.__setattr__(self, "allowed_tools", tuple(self.allowed_tools))


class SubagentRegistry:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, d: SubagentDef) -> Path:
        path = self._root / f"{d.name}.json"
        path.write_text(json.dumps(asdict(d), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, name: str) -> SubagentDef:
        path = self._root / f"{name}.json"
        if not path.exists():
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"未注册的 subagent: {name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return SubagentDef(**data)

    def list(self) -> list[SubagentDef]:
        return [
            SubagentDef(**json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self._root.glob("*.json"))
        ]

    def delete(self, name: str) -> None:
        (self._root / f"{name}.json").unlink(missing_ok=True)
