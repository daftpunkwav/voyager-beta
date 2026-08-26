"""主 agent 测试(§9.2/§9.5/§9.7):对话双轨、忙时仲裁、直聊开关、派单通报。"""

import asyncio

from platform_contracts import LOCAL_USER, DomainEvent

from agent.llm import FakeLLM, LLMReply
from agent.main import build_agent
from agent.runtime.state import RunStatus
from agent.subagent import Mode


def _app(tmp_path, llm: FakeLLM | None = None):
    return build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm or FakeLLM()
    )


def _replies(app) -> list[str]:
    return [
        e.payload["content"] for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
    ]


class TestChat:
    async def test_first_message_spawns_chat_subagent(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="你好,我在。"))
        await app.master.handle_user_message("你好")
        assert _replies(app) == ["你好,我在。"]
        chat = app.master.chat
        assert chat is not None and chat.status == RunStatus.WAITING_INPUT
        assert chat.task.mode is Mode.REACT  # Lucien 对话强制 ReAct(决策 §15)
        app.memory.close()

    async def test_queue_mode_holds_second_message(self, tmp_path) -> None:
        llm = FakeLLM(default="收到。")
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("第一句")
        app.master.chat.state.status = RunStatus.RUNNING  # 模拟忙
        await app.master.handle_user_message("第二句")
        assert len(llm.calls) == 1  # queue 模式不调判官,也不插话
        assert len(_replies(app)) == 1
        app.master.chat.state.status = RunStatus.WAITING_INPUT  # 恢复空闲
        await app.master.handle_user_message("第三句")
        assert _replies(app) == ["收到。", "收到。", "收到。"]  # 排队的第二句被补处理
        history = [m["content"] for m in app.master.chat.history if m["role"] == "user"]
        assert history == ["第一句", "第三句", "第二句"]  # 先当前,后排队
        app.memory.close()

    async def test_auto_mode_merge_feeds_running_chat(self, tmp_path) -> None:
        # 脚本第一条被首轮对话消费,第二条才是判官判定(并入)
        llm = FakeLLM([LLMReply(text="好。"), LLMReply(text="merge")])
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("分析这个项目")
        await app.settings.set("agent.arbiter.mode", "auto", LOCAL_USER)
        app.master.chat.state.status = RunStatus.RUNNING
        await app.master.handle_user_message("补充:只看 Python 部分")
        user_msgs = [m["content"] for m in app.master.chat.history if m["role"] == "user"]
        assert "补充:只看 Python 部分" in user_msgs  # 并入 chat 上下文
        app.memory.close()

    async def test_direct_chat_skips_subagent(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="直接回答。"))
        await app.settings.set("agent.direct_chat", True, LOCAL_USER)
        await app.master.handle_user_message("1+1=?")
        assert _replies(app) == ["直接回答。"]
        assert app.master.chat is None  # 直聊不派 subagent
        app.memory.close()


class TestDispatch:
    async def test_dispatch_runs_and_reports(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="索引完成。"))
        inst = await app.master.dispatch_task("为 langgraph 建索引", name="index")
        await asyncio.sleep(0.05)
        assert inst.status == RunStatus.COMPLETED
        assert any("[完成]" in t and "index" in t for t in _replies(app))
        app.memory.close()

    async def test_lucien_forced_react(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="完成。"))
        inst = await app.master.dispatch_task("整理笔记", persona="lucien", mode="tot")
        assert inst.task.mode is Mode.REACT  # 人格预设也改不掉(决策 §15)
        await asyncio.sleep(0.05)
        app.memory.close()

    async def test_persona_tool_allow_trims(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="完成。"))
        inst = await app.master.dispatch_task("巡检仓库", persona="atlas")
        assert "write_file" not in inst.toolbelt.names()  # atlas 能力面不含写
        await asyncio.sleep(0.05)
        app.memory.close()
