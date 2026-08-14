"""AI 管线(§8.4 决策 16):agent 经 set_node/set_relationship 直接建图。

本模块是给 agent 的建图约定与校验(不是执行器):
- 标签/类型词表(开放集,词表只是推荐,不封锁新类型);
- 校验:必填字段、名称长度、project 非空;
- guide_text():注入 agent 上下文的建图指引(按需加载,§9.20)。
"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "graph"

#: 推荐标签(开放集):书籍/新闻/文档建图的常见概念层
RECOMMENDED_LABELS = (
    "Concept", "Topic", "Person", "Organization", "Book", "Chapter",
    "Article", "Event", "Term", "Project", "File", "Function", "Class",
)

RECOMMENDED_RELATIONS = (
    "CONTAINS", "RELATES_TO", "DEPENDS_ON", "EXPLAINS", "MENTIONS",
    "AUTHORED_BY", "PART_OF", "COMPARED_WITH", "CALLS", "IMPORTS",
)

_GUIDE = """# AI 建图约定(§8.4)

- 节点:set_node(project, label, name, qualified_name?, attrs?)
  —— upsert 语义,同一 (project, label, qualified_name) 重复写=更新;
- 关系:set_relationship(project, src_qualified_name, dst_qualified_name, type, attrs?)
  —— 两端节点不存在时自动补占位节点(label=Term);
- project 即资源 id(仓库/书籍/新闻);同一资源的所有内容进同一 project 图;
- 推荐标签:Concept/Topic/Chapter/Article/Term…;推荐关系:CONTAINS/EXPLAINS/MENTIONS…;
  词表是推荐不是封锁,新概念类型允许,但保持一致(大写蛇形);
- 批量建图:先建骨架(章→节),再填概念与关系;每条调用都带来源摘录进 attrs.quote。
"""


def guide_text() -> str:
    return _GUIDE


def validate_node(project: str, label: str, name: str) -> None:
    if not project.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "project 不能为空")
    if not label.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "label 不能为空",
                           hint=f"推荐: {', '.join(RECOMMENDED_LABELS[:6])}…")
    if not name.strip() or len(name) > 200:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "name 必填且不超过 200 字")


def validate_relation(project: str, src: str, dst: str, type_: str) -> None:
    if not project.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "project 不能为空")
    if not src.strip() or not dst.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "src/dst 均为节点的 qualified_name,不能为空")
    if not type_.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "关系类型不能为空",
                           hint=f"推荐: {', '.join(RECOMMENDED_RELATIONS[:6])}…")
