"""build_agent 聚合运行扩展点(§5.2):外部设置存储与领域能力注入。"""

import asyncio

from platform_actor import ActorContext
from platform_contracts import LOCAL_USER, ActorKind, ActorRef
from platform_settings import SettingsStore

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.subagent import Mode, TaskBook
from agent.tools import AgentTool

AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


def _extra_tool() -> AgentTool:
    async def handler(text: str = "") -> dict:
        return {"echo": text}

    return AgentTool(
        name="echo__ping", description="测试用领域工具", handler=handler,
        dimension="app", write=False, irreversible=False,
    )


class TestSharedSettings:
    def test_shared_store_reused_and_keys_registered(self, tmp_path) -> None:
        shared = SettingsStore(tmp_path / "shared-settings.db")
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws",
            llm=FakeLLM(), settings_store=shared,
        )
        assert app.settings is shared  # 直接复用,不新建
        keys = {d["key"] for d in shared.list_schema()}
        assert "agent.style" in keys  # agent.* 已注册进共享 store
        assert "agent.app.allowed" in keys
        assert "agent.app.denied" in keys
        app.memory.close()

    def test_close_does_not_close_shared_store(self, tmp_path) -> None:
        shared = SettingsStore(tmp_path / "shared-settings.db")
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws",
            llm=FakeLLM(), settings_store=shared,
        )
        app.close()
        assert shared.get("agent.style")  # 共享实例由装配根持有,close 后仍可用
        shared.close()

    def test_default_owns_store(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        app.close()  # 自建 store/log 由 close 关闭,不泄漏句柄


class TestExtraTools:
    def test_injected_into_toolbelt(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws",
            llm=FakeLLM(), extra_tools={"echo__ping": _extra_tool()},
        )
        assert "echo__ping" in app.spawner._toolbelt.names()
        app.close()

    def test_handler_callable_through_toolbelt(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws",
            llm=FakeLLM(), extra_tools={"echo__ping": _extra_tool()},
        )
        from agent.llm import ToolCall

        out = asyncio.run(app.spawner._toolbelt.call(
            ToolCall(id="1", name="echo__ping", arguments={"text": "hi"})
        ))
        assert '"echo": "hi"' in out  # dict 结果序列化为 JSON 文本回给 LLM
        app.close()


class TestStyleInSystem:
    """agent.style 是人格之上的叠加层(§9.14):改完即进下一轮对话 system。"""

    async def test_style_reaches_spawned_system(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            await app.settings.set("agent.style", "毒舌", AGENT_CTX.actor)
            inst = app.spawner.spawn(
                TaskBook(goal="测试", mode=Mode.REACT), persona="orchestrator"
            )
            assert "【人格】Lucien(热心、靠谱、有主见)" in inst.system_prompt
            assert "【风格】毒舌" in inst.system_prompt
        finally:
            app.close()

    async def test_default_style_is_warm(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            assert app.settings.get("agent.style") == "热心"
        finally:
            app.close()


class TestConductInSystem:
    """行为准则进 system(phase-29,§9.14):非空注入对应层,空则整层省略;
    guideline 按 persona_key 经 canonical_persona_key 取对应人格的键。"""

    def _spawn(self, app, persona: str):
        return app.spawner.spawn(
            TaskBook(goal="测试", mode=Mode.REACT), persona=persona
        )

    async def test_conduct_reaches_spawned_system(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            await app.settings.set(
                "agent.conduct", "回答简洁,不用 emoji", LOCAL_USER
            )
            inst = self._spawn(app, "orchestrator")
            assert "【用户准则】" in inst.system_prompt
            assert "回答简洁,不用 emoji" in inst.system_prompt
        finally:
            app.close()

    async def test_default_conduct_omits_layer(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            inst = self._spawn(app, "orchestrator")
            assert "【用户准则】" not in inst.system_prompt
            assert "【人格准则】" not in inst.system_prompt
        finally:
            app.close()

    async def test_guideline_scoped_to_persona(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            await app.settings.set(
                "agent.guidelines", {"orchestrator": "先确认再改代码"}, LOCAL_USER
            )
            orch = self._spawn(app, "orchestrator")
            assert "【人格准则】" in orch.system_prompt
            assert "先确认再改代码" in orch.system_prompt
            recon = self._spawn(app, "recon")
            assert "【人格准则】" not in recon.system_prompt
        finally:
            app.close()
