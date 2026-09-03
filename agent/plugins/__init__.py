"""插件包(§9.13,phase-72):发现、整包批准、声明式装载 skill/hook。"""

from agent.plugins.manager import (
    APPROVED_KEY,
    PluginManager,
    PluginManifest,
    discover,
    load_manifest,
)

__all__ = [
    "APPROVED_KEY",
    "PluginManager",
    "PluginManifest",
    "discover",
    "load_manifest",
]
