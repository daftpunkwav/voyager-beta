"""notes 服务设置项(§8.8)。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="notes.sort.default", module="notes", type=SettingType.CHOICE,
               default="updated", choices=("updated", "created", "title"),
               description="笔记默认排序"),
    SettingDef(key="notes.list.page_size", module="notes", type=SettingType.INT,
               default=100, min=10, max=500, description="列表默认条数上限"),
    SettingDef(key="notes.editor.autosave_s", module="notes", type=SettingType.INT,
               default=5, min=0, max=120, description="编辑器自动保存间隔(秒;0=关)"),
    SettingDef(key="notes.trash.retention_days", module="notes", type=SettingType.INT,
               default=30, min=0, max=365,
               description="回收站保留天数(0=永久保留;超期自动清理)"),
    SettingDef(key="notes.history.per_note", module="notes", type=SettingType.INT,
               default=20, min=0, max=100,
               description="每篇笔记保留的历史版本数(0=关闭版本历史)"),
    SettingDef(key="notes.export.dir", module="notes", type=SettingType.STR,
               default="workspace/notes-export",
               description="导出 Markdown 文件的目录"),
]
