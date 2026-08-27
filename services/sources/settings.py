"""sources 服务设置项(§8.8):各服务自带设置,设置页按 schema 动态渲染。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="sources.sort.default", module="sources", type=SettingType.CHOICE,
               default="added", choices=("added", "name", "stars", "updated"),
               description="资源库默认排序字段"),
    SettingDef(key="sources.import.clone", module="sources", type=SettingType.BOOL,
               default=True, description="导入仓库时是否克隆到本地(否则只存元数据)"),
    SettingDef(key="sources.doc.max_file_mb", module="sources", type=SettingType.INT,
               default=200, min=1, max=2000,
               description="单文档导入大小上限(MB)"),
]
