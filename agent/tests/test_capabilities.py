"""agent 能力注册表测试(§5/铁律 4):agent 的能力经 capability 框架与用户同权调用。"""

import asyncio

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError

from agent.llm import FakeLLM
from agent.main import build_agent

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    yield app
    app.memory.close()


class TestSettingsParity:
    async def test_get_settings_lists_schema(self, app) -> None:
        schema = await execute(app.registry, "get_settings", USER_CTX, {})
        keys = {s["key"] for s in schema}
        assert {"agent.rounds.max", "agent.style", "agent.arbiter.mode"} <= keys

    async def test_agent_can_change_setting_like_user(self, app) -> None:
        """parity:用户能改的设置 agent 也能改(非 secret),_actor 注入调用者。"""
        result = await execute(
            app.registry, "set_setting", AGENT_CTX, {"key": "agent.style", "value": "毒舌"}
        )
        assert result["ok"] is True
        assert app.settings.get("agent.style") == "毒舌"

    async def test_unknown_setting_rejected(self, app) -> None:
        with pytest.raises(ServiceError):
            await execute(
                app.registry, "set_setting", USER_CTX, {"key": "agent.不存在", "value": 1}
            )

    async def test_no_actor_auth_required(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "get_settings", None, {})
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"


class TestSurface:
    async def test_list_skills_and_read(self, app) -> None:
        index = await execute(app.registry, "list_skills", USER_CTX, {})
        names = {s["name"] for s in index}
        assert "explore-repo" in names  # 内置 skill 入库
        doc = await execute(
            app.registry, "read_skill", USER_CTX, {"name": "explore-repo"}
        )
        assert doc["name"] == "explore-repo" and doc["text"]

    async def test_report_page_context(self, app) -> None:
        await execute(
            app.registry,
            "report_page_context",
            USER_CTX,
            {"page": "notes", "summary": "36 条笔记", "counts": {"notes": 36}},
        )
        assert app.pages.current().page == "notes"
        assert "notes=36" in app.pages.render()

    async def test_answer_question_roundtrip(self, app) -> None:
        from agent.tools.ask_user import Question

        task = asyncio.create_task(app.asker.ask(Question(prompt="继续吗?")))
        await asyncio.sleep(0.01)
        qid = next(iter(app.asker._pending))  # 测试取等待中的问题 id
        out = await execute(
            app.registry,
            "answer_question",
            USER_CTX,
            {"question_id": qid, "value": True},
        )
        assert out["matched"] is True
        assert await task is True

    async def test_list_subagents_shape(self, app) -> None:
        out = await execute(app.registry, "list_subagents", USER_CTX, {})
        assert set(out) == {"definitions", "running"}
        assert isinstance(out["definitions"], list)


class TestTeamSurface:
    """团队页数据源(阶段 09):人格清单、自建 subagent、工具面名册。"""

    async def test_list_personas_builtin_five(self, app) -> None:
        personas = await execute(app.registry, "list_personas", USER_CTX, {})
        keys = {p["key"] for p in personas}
        assert keys == {"orchestrator", "recon", "explainer", "organizer", "graph_guide"}
        master = next(p for p in personas if p["key"] == "orchestrator")
        assert master["tool_allow"] is None  # 统筹者不裁剪
        atlas = next(p for p in personas if p["key"] == "graph_guide")
        assert "graph__query_graph" in atlas["tool_allow"]
        assert all(p["system_prompt"] for p in personas)

    async def test_register_subagent_persisted_and_listed(self, app) -> None:
        out = await execute(app.registry, "register_subagent", USER_CTX, {
            "name": "scout", "description": "只读侦察员",
            "mode": "direct", "allowed_tools": ["web_search", "web_fetch"],
        })
        assert out == {"name": "scout", "mode": "direct",
                       "allowed_tools": ["web_search", "web_fetch"]}
        defs = (await execute(app.registry, "list_subagents", USER_CTX, {}))["definitions"]
        mine = next(d for d in defs if d["name"] == "scout")
        assert mine["mode"] == "direct"
        assert mine["allowed_tools"] == ["web_search", "web_fetch"]

    async def test_register_subagent_invalid_mode(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "register_subagent", USER_CTX, {
                "name": "bad", "description": "x", "mode": "流模式",
            })
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_list_tools_includes_internal_and_bridge(self, tmp_path) -> None:
        """名册 = LLM 看到的 ToolSpec:内部工具 + 领域桥注入工具。"""
        from agent.tools.base import AgentTool

        async def noop(**kw):
            return {}

        bridge = {"notes__create_note": AgentTool(
            name="notes__create_note", description="[notes] 新建笔记",
            handler=noop)}
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws",
                          llm=FakeLLM(), extra_tools=bridge)
        try:
            tools = await execute(app.registry, "list_tools", USER_CTX, {})
            names = {t["name"] for t in tools}
            assert "notes__create_note" in names  # 桥工具
            assert "spawn_subagent" in names  # 内部工具
            assert "read_file" in names
            bridge_tool = next(t for t in tools if t["name"] == "notes__create_note")
            assert bridge_tool["description"] == "[notes] 新建笔记"  # 原样透传
        finally:
            app.memory.close()

    async def test_dispatch_custom_applies_allowlist(self, app) -> None:
        """自建 subagent 按名派遣:白名单裁剪真实生效(§9.4.1,不是提示词约束)。"""
        await execute(app.registry, "register_subagent", USER_CTX, {
            "name": "scout2", "description": "只读侦察员",
            "mode": "direct", "allowed_tools": ["web_search"],
        })
        inst = await app.master.dispatch_task("查资料", persona="scout2")
        names = inst.toolbelt.names()
        assert names == ["web_search"]  # write_file 等真的不在工具面里
