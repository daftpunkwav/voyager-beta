"""能力注册表:服务的单一事实来源(§8.1)。

聚合服务(sources / office)的聚合注册表 = 各子模块注册表 merge 的结果,
聚合层零逻辑;冲突即冲突错误,不静默覆盖。
"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError

from platform_capability.define import Capability


class Registry:
    """一个服务(或子模块)的能力注册表。domain 用于错误码前缀(如 graph → GRAPH.*)。"""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._items: dict[str, Capability] = {}

    def register(self, cap: Capability) -> Capability:
        if cap.name in self._items:
            raise ServiceError(
                self.domain, ErrorSuffix.CONFLICT, f"能力重复注册: {cap.name}"
            )
        self._items[cap.name] = cap
        return cap

    def merge(self, *others: Registry) -> None:
        """合并子模块注册表(聚合服务用)。名称冲突立即报错。"""
        for other in others:
            for cap in other.all():
                self.register(cap)

    def get(self, name: str) -> Capability:
        try:
            return self._items[name]
        except KeyError:
            raise ServiceError(
                self.domain,
                ErrorSuffix.NOT_FOUND,
                f"未知能力: {name}",
                hint="GET /capabilities 查看本服务全部能力",
            ) from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def all(self) -> list[Capability]:
        return [self._items[n] for n in self.names()]

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)
