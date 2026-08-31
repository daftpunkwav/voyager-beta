"""主 agent 测试(§9.2/§9.5/§9.7):对话双轨、忙时仲裁、直聊开关、派单通报。"""

import asyncio

from platform_contracts import LOCAL_USER, DomainEvent

from agent.llm import FakeLLM, LLMReply
from agent.main import build_agent
from agent.master.master import limits_from_settings
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


async def _settle(app) -> None:
    """等 handle_user_message 起的后台回合任务全部结束(phase-15 回合后台化)。

    入口现在创建 asyncio.Task 即返回;断言 llm.calls / 事件前必须先收完后台回合。
    """
    while app.master._bg:
        await asyncio.gather(*list(app.master._bg))


class _FakeSettings:
    """最小设置句柄(master 只依赖读设置,SettingsReader 协议)。"""

    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)


class TestChat:
    async def test_first_message_spawns_chat_subagent(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="你好,我在。"))
        await app.master.handle_user_message("你好")
        await _settle(app)
        assert _replies(app) == ["你好,我在。"]
        chat = app.master.chat
        assert chat is not None and chat.status == RunStatus.WAITING_INPUT
        assert chat.task.mode is Mode.REACT  # Lucien 对话强制 ReAct(决策 §15)
        app.memory.close()

    async def test_queue_mode_holds_second_message(self, tmp_path) -> None:
        llm = FakeLLM(default="收到。")
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("你好")
        await _settle(app)
        app.master.chat.state.status = RunStatus.RUNNING  # 模拟忙
        await app.master.handle_user_message("第二句")
        assert len(llm.calls) == 1  # queue 模式不调判官,也不插话
        assert len(_replies(app)) == 1
        app.master.chat.state.status = RunStatus.WAITING_INPUT  # 恢复空闲
        await app.master.handle_user_message("第三句")
        await _settle(app)  # 第三句 + 排队的第二句都在后台回合里
        assert _replies(app) == ["收到。", "收到。", "收到。"]  # 排队的第二句被补处理
        history = [m["content"] for m in app.master.chat.history if m["role"] == "user"]
        assert history == ["你好", "第三句", "第二句"]  # 先当前,后排队
        app.memory.close()

    async def test_auto_mode_merge_feeds_running_chat(self, tmp_path) -> None:
        # 脚本第一条被首轮对话消费,第二条才是判官判定(并入)
        llm = FakeLLM([
            LLMReply(text="好。"),
            LLMReply(text="先看结构。"),  # 非寒暄零工具会再 complete 一次,不能把判官那格提前吃掉
            LLMReply(text="merge"),
        ])
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("分析这个项目")
        await _settle(app)
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
        await _settle(app)
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


class TestLimitsFromSettings:
    """轮数上限装配辅助(phase-10,§9.19):全局现读 + 覆盖只能更严。"""

    def test_global_values_read_each_call(self) -> None:
        s = _FakeSettings({"agent.rounds.max": 7, "agent.rounds.tool_max": 9})
        limits = limits_from_settings(s)
        assert (limits.max_rounds, limits.max_tool_calls) == (7, 9)

    def test_override_stricter_wins_looser_capped(self) -> None:
        s = _FakeSettings({"agent.rounds.max": 20, "agent.rounds.tool_max": 40})
        assert limits_from_settings(s, max_rounds=5).max_rounds == 5
        assert limits_from_settings(s, max_rounds=99).max_rounds == 20  # 比全局松 → 夹回全局

    def test_invalid_override_treated_as_unset(self) -> None:
        s = _FakeSettings({"agent.rounds.max": 20, "agent.rounds.tool_max": 40})
        assert limits_from_settings(s, max_rounds=0).max_rounds == 20
        assert limits_from_settings(s, max_rounds=-3).max_rounds == 20
        assert limits_from_settings(s, max_tool_calls=None).max_tool_calls == 40

    def test_missing_global_falls_back_to_dataclass_default(self) -> None:
        limits = limits_from_settings(_FakeSettings({}))
        assert (limits.max_rounds, limits.max_tool_calls) == (20, 40)


class TestChatLimitsRefresh:
    async def test_chat_limits_reread_each_turn(self, tmp_path) -> None:
        """对话主实例每回合重读轮数(phase-10):改设置后下一句生效,无需重建实例。"""
        app = _app(tmp_path, FakeLLM(default="好。"))
        await app.master.handle_user_message("你好")
        await _settle(app)
        chat = app.master.chat
        assert chat is not None and chat.task.limits.max_rounds == 20
        await app.settings.set("agent.rounds.max", 5, LOCAL_USER)
        await app.master.handle_user_message("继续")
        await _settle(app)
        assert app.master.chat is chat  # 同一实例复用
        assert app.master.chat.task.limits.max_rounds == 5  # limits 已 replace
        app.memory.close()


class TestSystemRefresh:
    async def test_next_turn_system_reflects_style_change(self, tmp_path) -> None:
        """每回合重算 system(phase-15):改 agent.style 后下一句的 system 含新风格。"""
        llm = FakeLLM(default="好。")
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("你好")
        await _settle(app)
        old_sys = llm.calls[0]["messages"][0]["content"]
        await app.settings.set("agent.style", "毒舌", LOCAL_USER)
        await app.master.handle_user_message("继续")
        await _settle(app)
        new_sys = llm.calls[-1]["messages"][0]["content"]
        assert "【风格】毒舌" in new_sys
        assert "【风格】毒舌" not in old_sys
        app.memory.close()


class TestHistoryBound:
    async def test_history_capped_after_many_turns(self, tmp_path) -> None:
        """history 硬上限(phase-15):多回合后不超 HISTORY_MAX,成对丢、头部仍是 user。"""
        from platform_eventbus import EventBus, EventLog

        from agent.policy import PolicyEngine
        from agent.runtime.events import RuntimeEvents
        from agent.runtime.state import RunState
        from agent.subagent.instance import HISTORY_MAX, SubagentInstance, TaskBook
        from agent.tools import AgentTool, Toolbelt

        async def chat_tool() -> str:
            return "ok"

        inst = SubagentInstance(
            task=TaskBook(goal="聊", conversational=True),
            toolbelt=Toolbelt(
                {"chat_tool": AgentTool(name="chat_tool", description="占位", handler=chat_tool)},
                PolicyEngine(),
            ),
            llm=FakeLLM(default="嗯。"),
            system_prompt="s",
            events=RuntimeEvents(EventBus(EventLog(tmp_path / "ev.db"))),
            state=RunState(task="聊"),
        )
        for _ in range(35):  # 每回合 user+assistant 两条 → 70 条,须被裁回上限内
            await inst.run_turn("话")
        assert len(inst.history) <= HISTORY_MAX
        assert inst.history[0]["role"] == "user"  # 成对丢弃,头部不是残回合
        assert inst.status == RunStatus.WAITING_INPUT
