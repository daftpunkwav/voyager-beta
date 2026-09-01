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

from agent.policy.engine import NET_ALL, NET_OFF, NET_WHITELIST
from agent.subagent.modes import Mode

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DOMAIN = "agent"
_NETWORK_MODES = ("", NET_OFF, NET_WHITELIST, NET_ALL)  # 空 = 继承全局(§9.9)


def _safe_name(name: str) -> str:
    """name 会直接拼进文件路径,统一在此校验(防 ../ 穿越到 subagents 目录之外)。"""
    if not _NAME_RE.match(name):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"名称须为小写 snake_case: {name}")
    return name


@dataclass(frozen=True)
class SubagentDef:
    name: str
    description: str
    mode: str = "react"
    persona: str = ""  # 人格预设 key(可空)
    allowed_tools: tuple[str, ...] | None = None  # None=不裁剪
    scopes: tuple[str, ...] = ()
    trigger: str = "manual"  # manual | event:<pattern>
    max_rounds: int | None = None  # ReAct 轮数覆盖(§9.19);None=跟随全局
    max_tool_calls: int | None = None  # 工具调用轮数覆盖;None=跟随全局
    network_mode: str = ""  # 网络档位覆盖(§9.9);空=继承全局

    def __post_init__(self) -> None:
        _safe_name(self.name)
        valid_modes = {m.value for m in Mode}
        if self.mode not in valid_modes:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"未知模式: {self.mode}(可选: {sorted(valid_modes)})",
            )
        if self.network_mode not in _NETWORK_MODES:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"未知网络档位: {self.network_mode}(可选: off/whitelist/all,留空继承全局)",
            )
        for field_name in ("max_rounds", "max_tool_calls"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.INVALID_INPUT,
                    f"{field_name} 须为正整数或不设(跟随全局)",
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
        name = _safe_name(name)
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
        name = _safe_name(name)
        (self._root / f"{name}.json").unlink(missing_ok=True)
