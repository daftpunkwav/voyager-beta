"""agent 自身设置项(§8.8):用户能改的 agent 也能改(secret / user_only 除外,框架层强制)。

轮数上限(§9.19)、仲裁模式(§9.7)、触达预算(§9.8)、记忆保留(§9.11)、
观察开关(§9.2)——非 secret 且非 user_only,用户与 agent 同权修改,入审计。
网络/工作目录/外接 MCP/应用内能力白名单(§9.9/§9.10/§9.13)是安全边界,标 user_only:
仅用户可写(提示注入经 agent 写不进),但值照常回显(设置页要显示当前档位)。
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(key="agent.rounds.max", module="agent", type=SettingType.INT,
               default=20, min=1, max=200, description="ReAct 轮数上限(全局默认)"),
    SettingDef(key="agent.rounds.tool_max", module="agent", type=SettingType.INT,
               default=40, min=1, max=500, description="工具调用轮数上限(全局默认)"),
    SettingDef(key="agent.arbiter.mode", module="agent", type=SettingType.CHOICE,
               default="queue", choices=("auto", "queue", "guide"),
               description="任务执行中来新消息的处理模式(§9.7)"),
    SettingDef(key="agent.direct_chat", module="agent", type=SettingType.BOOL,
               default=False, description="直聊模式:简单问答由主 agent 直接回复(默认关)"),
    SettingDef(key="agent.style", module="agent", type=SettingType.STR,
               default="热心", description="人格风格(毒舌/热心/严谨…)"),
    # 行为准则(phase-29,§9.14):用户在设置页写的规则,每回合注入 system。
    # user_only:准则属于用户给 agent 立的规矩,提示注入经 agent 写不进来。
    SettingDef(key="agent.conduct", module="agent", type=SettingType.STR,
               default="", user_only=True,
               description="通用行为准则,对所有 Agent 生效,注入每次对话 system(仅用户可改)"),
    SettingDef(key="agent.guidelines", module="agent", type=SettingType.JSON,
               default={}, user_only=True,
               description="分 Agent 行为准则 {<人格结构ID>: 文本},叠加在通用准则上(仅用户可改)"),
    SettingDef(key="agent.proactive.per_session", module="agent", type=SettingType.INT,
               default=3, min=0, max=20, description="主动触达:每会话上限"),
    SettingDef(key="agent.proactive.per_day", module="agent", type=SettingType.INT,
               default=10, min=0, max=100, description="主动触达:每日上限"),
    SettingDef(key="agent.proactive.follow_up_max", module="agent", type=SettingType.INT,
               default=2, min=0, max=5, description="追问链上限"),
    SettingDef(key="agent.proactive.quiet_start", module="agent", type=SettingType.INT,
               default=23, min=0, max=23, description="安静时段开始(小时)"),
    SettingDef(key="agent.proactive.quiet_end", module="agent", type=SettingType.INT,
               default=7, min=0, max=23, description="安静时段结束(小时)"),
    SettingDef(key="agent.workspace.dir", module="agent", type=SettingType.STR,
               default="workspace", user_only=True,
               description="agent 默认工作目录(§9.10;仅用户可改)"),
    SettingDef(key="agent.network.mode", module="agent", type=SettingType.CHOICE,
               default="whitelist", choices=("off", "whitelist", "all"), user_only=True,
               description="网络权限模式(§9.9;仅用户可改)"),
    SettingDef(key="agent.network.domains", module="agent", type=SettingType.JSON,
               default=["github.com", "arxiv.org"], user_only=True,
               description="网络白名单域名(仅用户可改)"),
    SettingDef(key="agent.subagents.max_concurrent", module="agent", type=SettingType.INT,
               default=3, min=1, max=16, description="subagent 并发上限"),
    SettingDef(key="agent.memory.retention_days", module="agent", type=SettingType.INT,
               default=90, min=0, max=3650,
               description="情节记忆保留天数;0 = 交 agent 管理(§9.11)"),
    SettingDef(key="agent.observe.auto_index", module="agent", type=SettingType.BOOL,
               default=False, description="观察到新资源就绪时自动建立图谱索引(§9.2)"),
    # 外接 MCP(phase-11b,§9.13):用户在设置页添加的 stdio/URL server 列表。
    # 一条记录:{id,name,kind,command,args,url,approval,approved,enabled};
    # 远端 schema / 本机绝对路径不进这条 JSON,连接细节在运行态。
    # user_only:提示注入改不了 server 列表(phase-13)。
    SettingDef(key="agent.mcp.servers", module="agent", type=SettingType.JSON,
               default=[], user_only=True,
               description="外接 MCP server 配置与批准记录(§9.13;仅用户可改)"),
    # 应用内 capability 白名单(phase-19,§9.9):仅用户可改,热读后立即影响桥工具调用。
    # 名称形如 `notes__create_note`、`graph__search`;`*` 表示全部;`notes__*` 表示前缀。
    # 空允许名单会拒绝所有 app 维工具,UI 必须拦空,后端保持语义不变。
    SettingDef(key="agent.app.allowed", module="agent", type=SettingType.JSON,
               default=["*"], user_only=True,
               description="应用内能力白名单(§9.9;仅用户可改)"),
    SettingDef(key="agent.app.denied", module="agent", type=SettingType.JSON,
               default=[], user_only=True,
               description="应用内能力拒绝名单(§9.9;拒绝优先;仅用户可改)"),
]
