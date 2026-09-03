"""插件包(§9.13,phase-72 整包 / phase-74 分项):发现、批准、声明式装载 skill/hook。"""

from agent.plugins.manager import (
    APPROVALS_KEY,
    APPROVED_KEY,
    PluginManager,
    PluginManifest,
    discover,
    load_manifest,
)

__all__ = [
    "APPROVALS_KEY",
    "APPROVED_KEY",
    "PluginManager",
    "PluginManifest",
    "discover",
    "load_manifest",
]
