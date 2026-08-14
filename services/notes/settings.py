"""notes 服务设置项(§8.8)。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="notes.sort.default", module="notes", type=SettingType.CHOICE,
               default="updated", choices=("updated", "created", "title"),
               description="笔记默认排序"),
    SettingDef(key="notes.list.page_size", module="notes", type=SettingType.INT,
               default=100, min=10, max=1000, description="列表默认条数"),
    SettingDef(key="notes.editor.autosave_s", module="notes", type=SettingType.INT,
               default=5, min=0, max=120, description="编辑器自动保存间隔(秒;0=关)"),
]
