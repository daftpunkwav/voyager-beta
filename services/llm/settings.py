"""llm 服务设置项(§8.8):默认提供商/模型、采样参数——非 secret,用户与 agent 同权。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="llm.default_provider", module="llm", type=SettingType.STR,
               default="", description="默认提供商 id(list_providers 查看)"),
    SettingDef(key="llm.default_model", module="llm", type=SettingType.STR,
               default="", description="默认模型(空 = 提供商 default_model)"),
    SettingDef(key="llm.temperature", module="llm", type=SettingType.FLOAT,
               default=0.7, min=0.0, max=2.0, description="采样温度(全局默认)"),
    SettingDef(key="llm.max_output_tokens", module="llm", type=SettingType.INT,
               default=4096, min=64, max=128000, description="输出 token 上限(全局默认)"),
]
