"""gateway 服务设置项(§7.5 入口限流层)。

gateway 进程无业务库;这些值由部署入口(composition root)从共享
SettingsStore 读出后经 create_app 参数注入,此处仅做 schema 声明,
让设置页能动态渲染"网关"分组。
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="gateway.rate_limit.per_minute", module="gateway",
               type=SettingType.INT, default=600, min=10, max=100000,
               description="每 actor 每分钟请求数上限"),
    SettingDef(key="gateway.sse.max_connections", module="gateway",
               type=SettingType.INT, default=8, min=1, max=128,
               description="SSE 长连接并发上限"),
    SettingDef(key="gateway.chat.history_page_size", module="gateway",
               type=SettingType.INT, default=200, min=20, max=2000,
               description="聊天历史单次拉取条数"),
]
