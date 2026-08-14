"""设置项框架:schema / 默认值 / secret 标记 / 变更事件。"""

from platform_settings.define import SettingDef, SettingType, validate
from platform_settings.store import SettingsStore

__all__ = ["SettingDef", "SettingType", "SettingsStore", "validate"]
