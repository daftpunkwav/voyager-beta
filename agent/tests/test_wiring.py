"""build_agent 聚合运行扩展点(§5.2):外部设置存储与领域能力注入。"""

import asyncio

from platform_settings import SettingsStore

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.tools import AgentTool


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
