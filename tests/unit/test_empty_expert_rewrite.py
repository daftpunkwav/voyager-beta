"""专家空正文时 Hub 不得 skip_merge"""
import pytest
from agent_core.agents.hub import HubService

from tests.sse_util import join_sse


@pytest.mark.asyncio
async def test_empty_expert_passthrough_triggers_hub_rewrite(monkeypatch):
    from agent_core.agents.react import EngineResult

    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = type("R", (), {"has": staticmethod(lambda aid: True)})()

    class Mem:
        async def append_short_memory(self, *args, **kwargs):
            return None

    service.memory = Mem()
    eval_calls = {"n": 0}

    async def fake_handle_dispatches(**kwargs):
        bag = kwargs.get("result_bag")
        if bag is not None:
            bag.summaries = ["[mentor] empty"]
            bag.expert_results = [("mentor", "")]
            bag.direct_streamed = True
            bag.hub_passthrough = True
            bag.had_question = False
        if False:
            yield ""
        return
        yield  # pragma: no cover

    async def fake_run_agent(**kwargs):
        if kwargs.get("evaluate_mode") or kwargs.get("merge_mode"):
            eval_calls["n"] += 1
            yield EngineResult(text="补写正文", dispatches=[])
            return
        yield EngineResult(text="", dispatches=[])

    monkeypatch.setattr(service, "_handle_dispatches", fake_handle_dispatches)
    monkeypatch.setattr(service, "_run_agent", fake_run_agent)

    chunks: list[str] = []
    async for chunk in service._dispatch_evaluate_loop(
        dispatches=[{"target_agent": "mentor", "task": "讲", "reason": "t"}],
        session_id="s1",
        original_message="想学",
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
    assert "未产出可用正文" in joined
    assert eval_calls["n"] >= 1
    assert "skip_merge" not in joined
