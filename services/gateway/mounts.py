"""服务挂载(§6.3):把各服务注册表生成的 router 挂到 /api/<domain>/。

gateway 自身不 import 任何领域服务——挂载清单(MountSpec)由部署入口
(composition root)装配注入;单体进程内挂内存注册表,微服务形态由
部署入口换成 HTTP 反代挂载,gateway 代码不变。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI
from platform_capability import build_router
from platform_capability.registry import Registry

from .health import HealthProbe, ProbeFn


@dataclass(frozen=True)
class MountSpec:
    """一个下游服务的挂载描述。"""

    domain: str           # URL 段:/api/<domain>/capabilities/...
    registry: Registry    # 该服务的能力注册表(单体进程内)
    probe: ProbeFn | None = None  # 健康探测函数(省略则只做被动感知)


def mount_services(
    app: FastAPI,
    mounts: list[MountSpec],
    probe: HealthProbe,
    *,
    issuer=None,
    auth: list[Callable] | None = None,
    quota: list[Callable] | None = None,
    audit: list | None = None,
) -> None:
    """统一挂载:REST 前缀 /api/<domain>;健康探测注册;鉴权/配额/审计逐路由共享。"""
    for spec in mounts:
        router = build_router(
            spec.registry, issuer=issuer, auth=auth, quota=quota, audit=audit,
        )
        app.include_router(router, prefix=f"/api/{spec.domain}")
        if spec.probe is not None:
            probe.register(spec.domain, spec.probe)
