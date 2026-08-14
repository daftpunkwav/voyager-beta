"""llm 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

聚合运行时装配根可传入共享 SecretStore(全系统唯一加密仓);共享实例由传入方
持有,wiring 不负责关闭。
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_secrets import SecretStore

from .capabilities import Deps, init_deps, registry
from .store import ProviderStore


def wire(
    data_dir: str | Path,
    *,
    secrets: SecretStore | None = None,
) -> Wiring:
    data_dir = Path(data_dir)
    store = ProviderStore(data_dir / "llm.db")
    owns_secrets = secrets is None
    secrets = secrets or SecretStore(data_dir / "secrets.db")
    init_deps(Deps(store=store, secrets=secrets))

    def close() -> None:
        store.close()
        if owns_secrets:
            secrets.close()

    return Wiring(registry=registry, probe=lambda: {"status": "up"}, close=close)
