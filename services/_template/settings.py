"""本服务设置项声明(经 platform/settings 框架,§7.9)。

服务启动时把 DEFS 注册进 SettingsStore;设置页按 schema 动态渲染(§10.11)。
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="template.worker.concurrency",
        module="template",
        type=SettingType.INT,
        default=1,
        min=1,
        max=8,
        description="长任务 worker 并发数",
    ),
]
