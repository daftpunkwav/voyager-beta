"""装配协议:服务独立运行(rest.py)与聚合运行(deploy/)共用的接线产物形态。

每个服务提供一个 `wiring.py`,暴露 `wire(data_dir, ...) -> Wiring`:
- 独立运行:rest.py 调 wire() 拿注册表与生命周期句柄,不再自己拼 store/deps;
- 聚合运行:装配根调同一 wire(),把 registry 交给 gateway 挂载,
  start/stop/close 由装配根在统一 lifespan 里调用。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from platform_capability.registry import Registry

if TYPE_CHECKING:  # fastapi 是可选依赖(仅挂载方需要),运行时不导入
    from fastapi import APIRouter


@dataclass
class Wiring:
    """一个服务接线完成的产物。

    - registry:能力注册表(挂 REST / 生成 MCP / 桥接 agent 工具的唯一来源);
    - probe:健康探测(可同步可异步;None 表示只做被动感知);
    - start/stop:后台生命周期(worker、scheduler 等),装配根 lifespan 调用;
    - close:关闭自有资源(数据库连接等);外部传入的共享资源不在此关闭;
    - extra_router:领域自有路由(如文件只读下载)。wire 自己建好交给装配根
      透传给 gateway,装配根不必触碰领域内部 store(§13.1 走协议不读表)。
    """

    registry: Registry
    probe: Callable[[], dict | Awaitable[dict]] | None = None
    start: Callable[[], Awaitable[None]] | None = None
    stop: Callable[[], Awaitable[None]] | None = None
    close: Callable[[], None] | None = None
    extra_router: "APIRouter | None" = None
