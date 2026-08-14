"""settings 服务自有设置项(§8.8):外观 / 交互 / 隐私三组。

模块名即设置页分组名;其余服务(notes/graph/llm/agent…)的 defs 由各自
settings.py 声明、注册进同一 platform SettingsStore,本服务按 module 聚合输出。
"""

from platform_settings import SettingDef, SettingType

THEMES = ("dark", "light", "system")

DEFS = [
    # 外观
    SettingDef(key="appearance.theme", module="appearance", type=SettingType.CHOICE,
               default="dark", choices=THEMES, description="界面主题"),
    SettingDef(key="appearance.font_scale", module="appearance", type=SettingType.FLOAT,
               default=1.0, min=0.8, max=1.5, description="全局字号缩放"),
    SettingDef(key="appearance.code_font", module="appearance", type=SettingType.STR,
               default="JetBrains Mono", description="代码字体"),
    # 交互(仲裁/安静时段/触达预算,§8.8)
    SettingDef(key="interaction.arbiter.mode", module="interaction",
               type=SettingType.CHOICE, default="queue",
               choices=("queue", "auto", "guide"),
               description="任务执行中新消息的处理模式:排队/自动/引导"),
    SettingDef(key="interaction.quiet_hours", module="interaction",
               type=SettingType.STR, default="",
               description="安静时段 HH:MM-HH:MM,空字符串为关闭"),
    SettingDef(key="interaction.touch_budget_per_day", module="interaction",
               type=SettingType.INT, default=3, min=0, max=20,
               description="agent 每日主动触达条数上限(0=不主动发消息)"),
    # 隐私
    SettingDef(key="privacy.activity_report", module="privacy", type=SettingType.BOOL,
               default=True, description="允许上报页面/焦点等活动信号供 agent 观察"),
]
