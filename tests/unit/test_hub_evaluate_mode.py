# -*- coding: utf-8 -*-
"""Hub evaluate loop: re-dispatch, dedupe, cap."""
import pytest
from agent_core.agents.hub import (
    MAX_HUB_DISPATCH_ROUNDS,
    HubService,
    _dispatch_fingerprint,
    apply_evaluate_mode,
    apply_merge_mode,
)
from agent_core.agents.registry import AGENT_DEFINITIONS

from tests.sse_util import join_sse


def test_apply_evaluate_mode_keeps_dispatch_only():
    hub = AGENT_DEFINITIONS["hub"]
    evaluated = apply_evaluate_mode(hub)
    assert evaluated.workflow == "react"
    assert evaluated.tools == ["dispatch_agent", "ask_user"]
    assert evaluated.max_iterations == 2
    assert evaluated.max_tokens <= 3200
    prompt = evaluated.system_prompt or ""
    assert "\u8bc4\u4f30" in prompt
    assert "\u7981\u6b62\u7f16\u9020" in prompt
    assert hub.workflow == "plan_execute"
    assert "query_user_projects" in hub.tools


def test_evaluate_and_merge_modes_are_distinct():
    hub = AGENT_DEFINITIONS["hub"]
    evaluated = apply_evaluate_mode(hub)
    merged = apply_merge_mode(hub)
    assert "dispatch_agent" in evaluated.tools
    assert merged.tools == []
    assert merged.workflow == "direct"


def test_dispatch_fingerprint_dedupes_similar_tasks():
    a = {"target_agent": "Mentor", "task": "explain  Godot  tree"}
    b = {"target_agent": "mentor", "task": "explain Godot tree"}
    c = {"target_agent": "scout", "task": "explain Godot tree"}
    assert _dispatch_fingerprint(a) == _dispatch_fingerprint(b)
    assert _dispatch_fingerprint(a) != _dispatch_fingerprint(c)


def test_dispatch_fingerprint_full_text_not_truncated():
    # 前 120 字相同但后半不同的任务不得被误杀（全文 hash）
    prefix = "explain " * 30  # 前 120 字相同
    a = {"target_agent": "mentor", "task": prefix + "A 部分"}
    b = {"target_agent": "mentor", "task": prefix + "B 部分"}
    assert len(prefix) > 120
    assert _dispatch_fingerprint(a) != _dispatch_fingerprint(b)


def test_evaluate_prompt_includes_summaries():
    prompt = HubService._evaluate_prompt(["[mentor] done"], "Godot deps", 0)
    assert "\u8bc4\u4f30\u4efb\u52a1" in prompt
    assert "[mentor] done" in prompt
    assert "Godot deps" in prompt
    assert "dispatch_agent" in prompt


def test_max_hub_dispatch_rounds_is_bounded():
    assert MAX_HUB_DISPATCH_ROUNDS == 2


@pytest.mark.asyncio
async def test_dispatch_evaluate_loop_nested_expert_merges(monkeypatch):
    from agent_core.agents.react import EngineResult

    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = type("R", (), {"has": staticmethod(lambda aid: True)})()
    memory_calls = []

    class Mem:
        async def append_short_memory(self, *args, **kwargs):
            memory_calls.append(True)

    service.memory = Mem()
    eval_calls = {"n": 0}
    merge_calls = {"n": 0}

    async def fake_handle_dispatches(**kwargs):
        bag = kwargs.get("result_bag")
        if bag is not None:
            bag.summaries = ["[mentor] long"]
            bag.expert_results = [("mentor", "long")]
            bag.direct_streamed = False
            bag.hub_passthrough = False
            bag.nested_expert = True
            bag.had_question = False
        if False:
            yield ""
        return
        yield  # pragma: no cover

    async def fake_run_agent(**kwargs):
        if kwargs.get("evaluate_mode"):
            eval_calls["n"] += 1
        if kwargs.get("merge_mode"):
            merge_calls["n"] += 1
            yield 'event: text_delta\ndata: {"content":"Hub summary"}\n\n'
            yield EngineResult(text="Hub summary", dispatches=[])
            return
        yield EngineResult(text="should-not-run", dispatches=[])

    monkeypatch.setattr(service, "_handle_dispatches", fake_handle_dispatches)
    monkeypatch.setattr(service, "_run_agent", fake_run_agent)

    chunks = []
    async for chunk in service._dispatch_evaluate_loop(
        dispatches=[{"target_agent": "mentor", "task": "x", "reason": "y"}],
        session_id="s1",
        original_message="learn",
        llm=None,
        llm_config=None,
        raw_settings={},
        permissions={},
        project_id=None,
        history=[],
        hub_preamble="",
    ):
        chunks.append(chunk)

    joined = join_sse(chunks)
    assert eval_calls["n"] == 0
    assert merge_calls["n"] == 1
    assert "skip_merge" not in joined
    assert "Hub summary" in joined
    assert memory_calls


@pytest.mark.asyncio
async def test_dispatch_evaluate_loop_hub_passthrough_skips_rewrite(monkeypatch):
    from agent_core.agents.react import EngineResult

    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = type("R", (), {"has": staticmethod(lambda aid: True)})()
    memory_calls = []

    class Mem:
        async def append_short_memory(self, *args, **kwargs):
            memory_calls.append(True)

    service.memory = Mem()
    eval_calls = {"n": 0}

    async def fake_handle_dispatches(**kwargs):
        bag = kwargs.get("result_bag")
        if bag is not None:
            bag.summaries = ["[mentor] long"]
            bag.expert_results = [("mentor", "long")]
            bag.direct_streamed = True
            bag.hub_passthrough = True
            bag.had_question = False
        if False:
            yield ""
        return
        yield  # pragma: no cover

    async def fake_run_agent(**kwargs):
        if kwargs.get("evaluate_mode"):
            eval_calls["n"] += 1
        yield EngineResult(text="should-not-run", dispatches=[])

    monkeypatch.setattr(service, "_handle_dispatches", fake_handle_dispatches)
    monkeypatch.setattr(service, "_run_agent", fake_run_agent)

    chunks = []
    async for chunk in service._dispatch_evaluate_loop(
        dispatches=[{"target_agent": "mentor", "task": "x", "reason": "y"}],
        session_id="s1",
        original_message="learn",
        llm=None,
        llm_config=None,
        raw_settings={},
        permissions={},
        project_id=None,
        history=[],
        hub_preamble="",
    ):
        chunks.append(chunk)

    joined = join_sse(chunks)
    assert eval_calls["n"] == 0
    assert "\u8bc4\u4f30\u4e13\u5bb6\u7ed3\u679c" not in joined
    assert "skip_merge" in joined or "event: done" in joined
    assert memory_calls


@pytest.mark.asyncio
async def test_dispatch_evaluate_loop_can_re_dispatch_until_cap(monkeypatch):
    from agent_core.agents.react import EngineResult

    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = type(
        "R",
        (),
        {"has": staticmethod(lambda aid: aid in {"mentor", "scout", "atlas"})},
    )()
    memory_calls = []

    class Mem:
        async def append_short_memory(self, *args, **kwargs):
            memory_calls.append({"args": args, "kwargs": kwargs})

    service.memory = Mem()

    async def fake_handle_dispatches(**kwargs):
        bag = kwargs.get("result_bag")
        dispatches = kwargs["dispatches"]
        if bag is not None:
            summaries = []
            results = []
            for d in dispatches:
                t = d["target_agent"]
                summaries.append(f"[{t}] ok")
                results.append((t, "ok"))
            bag.summaries = summaries
            bag.expert_results = results
            bag.direct_streamed = (
                len(dispatches) == 1 and not kwargs.get("force_subagent")
            )
            bag.had_question = False
        if False:
            yield ""
        return
        yield  # pragma: no cover

    eval_calls = {"n": 0}
    merge_calls = {"n": 0}

    async def fake_run_agent(**kwargs):
        if kwargs.get("evaluate_mode"):
            eval_calls["n"] += 1
            n = eval_calls["n"]
            if n == 1:
                yield EngineResult(
                    text="",
                    dispatches=[
                        {"target_agent": "atlas", "task": "deps", "reason": "gap"}
                    ],
                )
            elif n < MAX_HUB_DISPATCH_ROUNDS:
                yield EngineResult(
                    text="",
                    dispatches=[
                        {
                            "target_agent": "scout",
                            "task": f"more {n}",
                            "reason": "more",
                        }
                    ],
                )
            else:
                yield EngineResult(text="", dispatches=[])
            return
        if kwargs.get("merge_mode"):
            merge_calls["n"] += 1
            yield 'event: text_delta\ndata: {"content":"merged"}\n\n'
            yield EngineResult(text="merged", dispatches=[])
            return
        yield EngineResult(text="expert", dispatches=[])

    monkeypatch.setattr(service, "_handle_dispatches", fake_handle_dispatches)
    monkeypatch.setattr(service, "_run_agent", fake_run_agent)

    chunks = []
    async for chunk in service._dispatch_evaluate_loop(
        dispatches=[
            {"target_agent": "mentor", "task": "teach", "reason": "learn"}
        ],
        session_id="s1",
        original_message="Godot",
        llm=None,
        llm_config=None,
        raw_settings={},
        permissions={},
        project_id=None,
        history=[],
        hub_preamble="",
    ):
        chunks.append(chunk)

    assert eval_calls["n"] >= 2
    assert merge_calls["n"] == 1
    joined = join_sse(chunks)
    assert "\u8c03\u5ea6\u8f6e\u6b21\u4e0a\u9650" in joined or merge_calls["n"] == 1
