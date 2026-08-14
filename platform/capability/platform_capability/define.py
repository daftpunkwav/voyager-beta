"""能力定义与入参校验。

handler 约定:
- 提供 input_model(dataclass)时,handler 接收**一个**构造好的模型实例;
- 不提供时,handler 以 **kwargs 接收原始入参;
- 返回 dict / dataclass / JobRef(long_running 时必须)。
"""

from __future__ import annotations

import dataclasses
import re
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

Handler = Callable[..., Any]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Capability:
    """能力元数据(§7.3)。description 写给 LLM:何时用、返回什么。"""

    name: str
    description: str
    handler: Handler
    input_model: type | None = None
    cost: int = 1  # 配额扣减档(§7.5)
    reversible: bool = True
    scopes: frozenset[str] = frozenset()  # 所需权限;空 = 无额外要求
    long_running: bool = False  # True 时 handler 必须返回 JobRef(只入队,§7.3)


def capability(
    registry,
    *,
    name: str,
    description: str,
    input_model: type | None = None,
    cost: int = 1,
    reversible: bool = True,
    scopes: typing.Iterable[str] = (),
    long_running: bool = False,
) -> Callable[[Handler], Handler]:
    """装饰器:把函数注册为 registry 中的一个能力。"""
    if not _NAME_RE.match(name):
        raise ServiceError(
            registry.domain,
            ErrorSuffix.INVALID_INPUT,
            f"能力名必须为小写 snake_case: {name!r}",
        )

    def decorator(fn: Handler) -> Handler:
        registry.register(
            Capability(
                name=name,
                description=description,
                handler=fn,
                input_model=input_model,
                cost=cost,
                reversible=reversible,
                scopes=frozenset(scopes),
                long_running=long_running,
            )
        )
        return fn

    return decorator


def _type_name(expected: Any) -> str:
    return getattr(expected, "__name__", str(expected))


def _check_shallow(domain: str, name: str, value: Any, expected: Any) -> None:
    """浅层类型检查:只约束原始类型,复合/Optional/Any 交给 handler 自己。"""
    if expected is bool:
        ok = isinstance(value, bool)
    elif expected is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif expected is float:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected is str:
        ok = isinstance(value, str)
    elif expected is list:
        ok = isinstance(value, list)
    elif expected is dict:
        ok = isinstance(value, dict)
    else:
        return  # 非原始类型:不在框架层强校验
    if not ok:
        raise ServiceError(
            domain,
            ErrorSuffix.INVALID_INPUT,
            f"入参 {name} 应为 {_type_name(expected)},实为 {type(value).__name__}",
        )


def coerce_input(model: type | None, data: Any, *, domain: str) -> Any:
    """把入参 dict 校验并构造为 input_model 实例;无模型时原样返回。"""
    if model is None:
        return data if data is not None else {}
    if not isinstance(data, dict):
        raise ServiceError(domain, ErrorSuffix.INVALID_INPUT, "入参必须是 JSON 对象")
    hints = typing.get_type_hints(model)
    fields = {f.name: f for f in dataclasses.fields(model)}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ServiceError(
            domain, ErrorSuffix.INVALID_INPUT, f"未知入参: {', '.join(unknown)}"
        )
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, f in fields.items():
        if name in data:
            value = data[name]
            if name in hints:
                _check_shallow(domain, name, value, hints[name])
            kwargs[name] = value
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            missing.append(name)
    if missing:
        raise ServiceError(
            domain, ErrorSuffix.INVALID_INPUT, f"缺少必填入参: {', '.join(missing)}"
        )
    try:
        return model(**kwargs)
    except TypeError as exc:
        raise ServiceError(domain, ErrorSuffix.INVALID_INPUT, f"入参构造失败: {exc}") from exc
