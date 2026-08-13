"""Agent 目录常量 —— 与前端 agentCatalog 对齐"""
from api_backend.schemas.agent import AgentProfileOut

AGENT_PROFILES: list[AgentProfileOut] = [
    AgentProfileOut(
        id="hub",
        name="Hub",
        description="总调度 Agent，协调其他专业 Agent",
        avatar_emoji="🎯",
        capabilities=["路由", "任务分解", "多 Agent 协调"],
    ),
    AgentProfileOut(
        id="scout",
        name="Scout",
        description="快速扫描项目，生成技术概览",
        avatar_emoji="🔭",
        capabilities=["README 分析", "技术栈识别", "依赖图谱"],
    ),
    AgentProfileOut(
        id="mentor",
        name="Mentor",
        description="深度教学与概念讲解",
        avatar_emoji="📚",
        capabilities=["概念讲解", "对比分析", "练习题"],
    ),
    AgentProfileOut(
        id="navigator",
        name="Navigator",
        description="学习路径规划与进度追踪",
        avatar_emoji="🧭",
        capabilities=["路径规划", "里程碑", "进度建议"],
    ),
    AgentProfileOut(
        id="curator",
        name="Curator",
        description="项目库整理与分类建议",
        avatar_emoji="🗂️",
        capabilities=["分类", "标签", "去重"],
    ),
    AgentProfileOut(
        id="scribe",
        name="Scribe",
        description="笔记生成与知识整理",
        avatar_emoji="✍️",
        capabilities=["笔记生成", "知识整理", "摘要"],
    ),
    AgentProfileOut(
        id="atlas",
        name="Atlas",
        description="知识图谱向导，解读项目关联",
        avatar_emoji="🗺️",
        capabilities=["图谱查询", "关系解读", "探索建议"],
    ),
]


def get_agent_profiles() -> list[AgentProfileOut]:
    """§4.2.2 R-02: 从 agent_core registry 派生的 AgentProfileOut 列表。

    注意：因 agent_core 反向依赖 backend 的端口与安全（§4.2.1），此处采用延迟
    导入以避免模块加载时死锁。真源仍由 services/agent/agent_core/agents/registry.py
    维护，本文件 AGENT_PROFILES 保留为 e2e/文档展示用的静态快照。
    """
    try:
        from agent_runtime.runtime import get_agent_runtime
        defs = get_agent_runtime().list_agent_definitions()
        return [
            AgentProfileOut(
                id=d.id,
                name=d.display_name or d.name,
                description=(d.description or ""),
                avatar_emoji="",
                capabilities=list(d.capabilities or []),
            )
            for d in defs
        ]
    except Exception:
        # agent_core 不可用（独立部署、CI mock 等场景），回退到静态快照
        return list(AGENT_PROFILES)