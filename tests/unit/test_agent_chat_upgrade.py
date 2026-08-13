"""意图规则与 dispatch 枚举对齐"""
import asyncio

from agent_core.agents.intent import IntentClassifier
from agent_core.agents.registry import AGENT_DEFINITIONS
from agent_core.tools.builtin import ensure_tools_loaded
from agent_core.tools.registry import global_registry


def _classify(msg: str):
    clf = IntentClassifier(llm=None)
    return asyncio.run(clf.classify(msg))


def test_intent_want_learn_langchain():
    r = _classify("想学习langchain")
    assert r.agent_id == "mentor"
    assert r.confidence >= 0.85


def test_intent_how_to_learn():
    r = _classify("怎么学 React")
    assert r.agent_id == "mentor"


def test_intent_learning_path_is_navigator():
    r = _classify("学习路径怎么规划")
    assert r.agent_id == "navigator"


def test_intent_scout():
    r = _classify("快速分析这个仓库")
    assert r.agent_id == "scout"


def test_dispatch_agent_enum_includes_atlas():
    ensure_tools_loaded()
    tools = global_registry.openai_tools_for("hub")
    dispatch = next(
        t for t in tools if (t.get("function") or {}).get("name") == "dispatch_agent"
    )
    enum = (
        (dispatch.get("function") or {})
        .get("parameters", {})
        .get("properties", {})
        .get("target_agent", {})
        .get("enum")
        or []
    )
    assert "atlas" in enum
    assert "mentor" in enum


def test_plan_phase_branches_forbid_dispatch_for_experts():
    import inspect

    from agent_core.agents import react as react_mod

    src = inspect.getsource(react_mod.ReActEngine._plan_phase_to_thinking)
    assert "dispatch_agent" in src
    assert "禁止调用或提及 dispatch_agent" in src


def test_hub_max_tokens_for_merge_budget():
    assert AGENT_DEFINITIONS["hub"].max_tokens >= 4096
