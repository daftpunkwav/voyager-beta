"""office 服务设置项(§8.6):导出目录等。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="office.export.dir",
        module="office",
        type=SettingType.STR,
        default="workspace/exports/",
        description="文档导出默认目录",
    ),
]
