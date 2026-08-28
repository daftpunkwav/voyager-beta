"""notes 能力注册表(§8.3):装配入口。具体能力按职责分文件注册到同一 registry。

用户与 agent 同权(铁律 4)。公开符号保持 Deps / init_deps / registry,
独立运行与测试仍从本模块导入。
"""

from __future__ import annotations

from .runtime import Deps, init_deps, registry

from . import batch as _batch  # noqa: F401
from . import catalog as _catalog  # noqa: F401
from . import history as _history  # noqa: F401
from . import lifecycle as _lifecycle  # noqa: F401
from . import transfer as _transfer  # noqa: F401
from . import view as _view  # noqa: F401

__all__ = ["Deps", "init_deps", "registry"]
