"""load_skill / recall_memory 工具:按需加载体系的 LLM 侧入口(§9.20)。"""

from __future__ import annotations

from agent.context.loader import OnDemandLoader
from agent.tools.base import AgentTool


def load_skill_tool(loader: OnDemandLoader) -> dict[str, AgentTool]:
    def load_skill(name: str) -> str:
        return loader.skill_text(name)

    return {
        "load_skill": AgentTool(
            name="load_skill",
            description="按需读取某个 skill 的全文(索引已在上下文里,这里取全文)",
            handler=load_skill,
            schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
    }


def recall_memory_tool(loader: OnDemandLoader) -> dict[str, AgentTool]:
    def recall_memory(query: str, limit: int = 8) -> list:
        return loader.recall(query, limit)

    return {
        "recall_memory": AgentTool(
            name="recall_memory",
            description="检索式记忆查询:画像/情节/语义三类命中,标注来源",
            handler=recall_memory,
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
    }
