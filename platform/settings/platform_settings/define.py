"""设置项定义与取值校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "settings"
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")  # <module>.<name>[.<sub>]


class SettingType(str, Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"
    JSON = "json"


@dataclass(frozen=True)
class SettingDef:
    """设置项声明(§7.9)。secret=True 的值永不进 list_schema / 事件 payload。"""

    key: str
    module: str
    type: SettingType
    default: Any = None
    description: str = ""
    secret: bool = False
    choices: tuple[Any, ...] = ()
    min: float | None = None
    max: float | None = None

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.key):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"设置键必须为 <module>.<name> 点分小写: {self.key!r}",
            )


def validate(d: SettingDef, value: Any) -> Any:
    """按定义校验并返回规范化值;不合法抛 SETTINGS.INVALID_INPUT。"""
    t = d.type
    ok = True
    if t is SettingType.BOOL:
        ok = isinstance(value, bool)
    elif t is SettingType.INT:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif t is SettingType.FLOAT:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if ok:
            value = float(value)
    elif t in (SettingType.STR, SettingType.CHOICE):
        ok = isinstance(value, str)
    elif t is SettingType.JSON:
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            ok = False
    if not ok:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, f"设置 {d.key} 应为 {t.value} 类型"
        )
    if t is SettingType.CHOICE and value not in d.choices:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"设置 {d.key} 取值须属于 {list(d.choices)}",
        )
    if t in (SettingType.INT, SettingType.FLOAT):
        if d.min is not None and value < d.min:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, f"设置 {d.key} 不能小于 {d.min}"
            )
        if d.max is not None and value > d.max:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, f"设置 {d.key} 不能大于 {d.max}"
            )
    return value
