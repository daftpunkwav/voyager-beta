"""activate_tools:对话实例的工具分级加载(phase-06,§9.20 精神)。

Lucien(tool_allow=None)的 `call()` 能调任何已有工具,但 `llm.complete`
每轮只收到**已激活**的完整 schema——避免把约百个桥工具 schema 全量塞给
模型(首轮 60s read timeout 的根因)。约定:

- 常驻激活(CORE):编排必需的内部工具 + 本工具;
- `activate_tools(domain=...)` / `(names=[...])` 把匹配工具并入**该实例**的
  激活集(下一轮 complete 即可见),不改全局 Toolbelt(多实例共享);
- 派遣的任务型 subagent 走 trimmed(),工具本来就少,整份 specs 给模型,
  不走激活。
"""

from __future__ import annotations

from typing import Any

from agent.tools.base import AgentTool, Toolbelt

#: 常驻激活(完整 schema):对话编排离不开的工具 + activate_tools 自身
CORE_TOOLS = (
    "ask_user",
    "spawn_subagent",
    "load_skill",
    "recall_memory",
    "request_context",
    "reach_out",
    "settings__get_theme",
    "settings__set_theme",
    "activate_tools",
)

#: 可按域激活的前缀(= 桥挂载的领域服务;fs/shell/web 是内部工具名前缀;
#: mcp 是外接 MCP 挂载的工具,phase-11b,批准后进名册)
DOMAINS = ("notes", "sources", "graph", "settings", "llm", "fs", "shell", "web", "mcp")

# 从近况话里猜要预激活的域(「都测试一下」本身无域名,靠上文「底纹/笔记」)
_DOMAIN_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("notes", ("笔记", "底纹", "加粗", "回收站", "正文", "markdown")),
    ("graph", ("图谱", "索引", "节点", "建图")),
    ("sources", ("仓库", "导入", "github", "资源库", "剪藏")),
)


def infer_domains(*texts: str) -> tuple[str, ...]:
    """从近期对话猜域;命中的域启动即并入激活集,少一轮纯 activate。"""
    blob = " ".join(texts).lower()
    found: list[str] = []
    for domain, hints in _DOMAIN_HINTS:
        if any(h.lower() in blob for h in hints):
            found.append(domain)
    return tuple(found)

ACTIVATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "enum": list(DOMAINS),
            "description": "按域激活:该域全部工具并入激活集(如 notes → notes__*)",
        },
        "names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "按精确名激活(当前名册中存在的工具)",
        },
    },
}


def _activate_handler(toolbelt: Toolbelt, active: set[str]):
    async def activate(domain: str | None = None, names: list[str] | None = None) -> str:
        """把匹配工具并入本实例激活集;下一轮起 LLM 可见其完整 schema。"""
        pool = set(toolbelt.names())
        matched: set[str] = set()
        if domain:
            prefix = f"{domain}__"
            matched.update(n for n in pool if n.startswith(prefix))
        if names:
            matched.update(n for n in pool if n in set(names))
        if not matched:
            return (
                "[无匹配] 当前名册中没有匹配的工具;"
                f"可用域:{', '.join(DOMAINS)} 或用 names 给精确名"
            )
        active.update(matched)
        return f"已激活 {len(matched)} 个工具: {', '.join(sorted(matched))}"

    return activate


def graded_toolbelt(
    toolbelt: Toolbelt, active: set[str] | None = None,
    *, preactivate: tuple[str, ...] = (),
) -> Toolbelt:
    """对话实例的分级视图:激活集默认 CORE;跨轮保留由调用方持有同一 set。

    preactivate:启动即并入的域(如用户在笔记页则预激活 notes,省一轮激活)。
    activate_tools 本身绑定 active 共享引用,调用后下一轮 specs() 即见。
    """
    if active is None:
        active = set(CORE_TOOLS)
    else:
        active.update(CORE_TOOLS)
    pool = set(toolbelt.names())
    for domain in preactivate:
        active.update(n for n in pool if n.startswith(f"{domain}__"))
    activate = AgentTool(
        name="activate_tools",
        description=(
            "按域或按名激活工具(domain=notes/sources/graph/… 或 names=[...]),"
            "激活后下一轮即可使用该工具;调用工具前若怀疑其未激活,先激活再调"
        ),
        handler=_activate_handler(toolbelt, active),
        schema=ACTIVATE_SCHEMA,
    )
    return toolbelt.with_active(active, extra={"activate_tools": activate})
