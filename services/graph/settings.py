"""graph 服务设置项(§8.8):引擎选择(决策 6)、队列并发与重试。"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="graph.engine.mode", module="graph", type=SettingType.CHOICE,
               default="auto", choices=("auto", "c", "python"),
               description="图谱引擎:auto=C 优先自动回退 Python;可强制"),
    SettingDef(key="graph.engine.c_url", module="graph", type=SettingType.STR,
               default="http://127.0.0.1:8123",
               description="C 引擎 sidecar 地址(engines/c/core 构建产物)"),
    SettingDef(key="graph.index.concurrency", module="graph", type=SettingType.INT,
               default=1, min=1, max=4, description="索引并发上限"),
    SettingDef(key="graph.index.max_attempts", module="graph", type=SettingType.INT,
               default=3, min=1, max=10, description="索引失败重试上限"),
    SettingDef(key="graph.query.default_limit", module="graph", type=SettingType.INT,
               default=200, min=10, max=10000, description="图查询默认条数"),
]
