"""activate_tools:对话实例的工具分级加载(phase-06,§9.20 精神)。

Lucien(tool_allow=None)的 `call()` 能调任何已有工具,但 `llm.complete`
每轮只收到**已激活**的完整 schema——避免把约百个桥工具 schema 全量塞给
模型(首轮 60s read timeout 的根因)。约定:

- 常驻激活(CORE):编排必需的内部工具 + 本工具;
- `activate_tools(domain=...)` / `(names=[...])` 把匹配工具并入**该实例**的
  激活集(下一轮 complete 即可见),不改全局 Toolbelt(多实例共享);
- 派遣的任务型 subagent 走 trimmed(),工具本来就少,整份 specs 给模型,
  不走激活。

域不是模块常量:可激活域从**当前 Toolbelt 名册**的 `__` 前缀现算
(`domain_prefixes`,phase-30),新挂一个 `office__*` 工具不必改本文件;
页面预激活名单(`page_preactivate`)也在本文件。
"""

from __future__ import annotations

from collections.abc import Iterable
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

#: 页面 → 预激活域(§9.20):用户停在这三个领域页时,对话开局即并入该域
#: 工具,省一轮 activate_tools;其他页(settings/usage…)不预激活。
#: 名单有意收窄成三页:若按「页面 id 等于域名就预激活」泛化,settings 页
#: 一上报就会把 settings__* 整域 schema 打进对话。
_PAGE_PREACTIVATE: dict[str, str] = {
    "notes": "notes",
    "graph": "graph",
    "sources": "sources",
}


def page_preactivate(page: str) -> str | None:
    """当前页面对应的工具域;无映射返回 None(单测直测这个小函数)。"""
    return _PAGE_PREACTIVATE.get(page)


def domain_prefixes(names: Iterable[str]) -> tuple[str, ...]:
    """名册里 `foo__bar` → foo(取第一段 `__` 之前);无 `__` 的内部工具
    (read_file / run_shell / activate_tools…)不产生域。去重,排序稳定。
    """
    prefixes = set()
    for n in names:
        head, sep, _tail = n.partition("__")
        if sep and head:
            prefixes.add(head)
    return tuple(sorted(prefixes))


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


def _activate_schema(domains: tuple[str, ...]) -> dict[str, Any]:
    """activate_tools 的参数 schema:domain enum 从当前名册现算(phase-30)。"""
    return {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "enum": list(domains),
                "description": "按域激活:该域全部工具并入激活集(如 notes → notes__*)",
            },
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "按精确名激活(当前名册中存在的工具)",
            },
        },
    }


def _activate_handler(
    toolbelt: Toolbelt, active: set[str], domains: tuple[str, ...]
):
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
                f"可用域:{', '.join(domains)} 或用 names 给精确名"
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
    domains = domain_prefixes(pool)
    activate = AgentTool(
        name="activate_tools",
        description=(
            "按域或按名激活工具(domain=notes/sources/graph/… 或 names=[...]),"
            "激活后下一轮即可使用该工具;调用工具前若怀疑其未激活,先激活再调"
        ),
        handler=_activate_handler(toolbelt, active, domains),
        schema=_activate_schema(domains),
    )
    return toolbelt.with_active(active, extra={"activate_tools": activate})
