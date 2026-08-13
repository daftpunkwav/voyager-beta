"""Atlas 代码图谱工具注册冒烟。"""
from agent_core.agents.registry import AGENT_DEFINITIONS
from agent_core.tools.builtin import ensure_tools_loaded
from agent_core.tools.registry import global_registry


def test_code_graph_tools_registered():
    ensure_tools_loaded()
    for name in (
        "trigger_code_index",
        "search_code_graph",
        "search_code",
        "trace_calls",
        "query_graph",
        "get_graph_schema",
        "get_project_architecture",
        "get_code_snippet_from_graph",
    ):
        tools = [t for t in global_registry.get_tools_for_agent("atlas") if t.name == name]
        assert tools, f"missing tool {name} for atlas"
        assert "atlas" in tools[0].allowed_agents


def test_atlas_includes_code_graph_tools():
    tools = AGENT_DEFINITIONS["atlas"].tools
    assert "search_code_graph" in tools
    assert "trace_calls" in tools
    assert "trigger_code_index" in tools
    assert "query_knowledge_graph" in tools
