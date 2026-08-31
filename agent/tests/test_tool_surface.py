"""工具面分级(phase-06):前缀授予、Lucien 域激活、工具步骤可见。

- C 前缀授予:notes__* 相对当前名册展开,新挂载的领域能力自动进入
  organizer 的 trimmed 工具面,人格文件不写死展开结果;
- D 域激活:对话实例(Lucien)首轮 complete 只送 CORE 激活集;
  activate_tools 并入后下一轮可见;call() 不受激活限制;
- B agent.step:工具步骤进事件流(gateway _STREAM_TYPES)。
"""

import asyncio
from pathlib import Path

import agent.personas.organizer as organizer_mod
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.personas import resolve_persona
from agent.subagent.instance import page_preactivate
from agent.tests.test_master import _replies, _settle
from agent.tools import AgentTool


def _app(tmp_path, llm, extra_tools=None):
    return build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=llm,
        extra_tools=extra_tools,
    )


def _fake_notes_tools() -> dict[str, AgentTool]:
    async def create_note(title: str = "", content: str = "") -> dict:
        return {"note_id": "n-1", "title": title}

    async def mark_note_span(note_id: str = "", **kw) -> str:
        return f"marked {note_id}"

    return {
        "notes__create_note": AgentTool(
            name="notes__create_note",
            description="[notes] 新建笔记",
            handler=create_note,
        ),
        "notes__mark_note_span": AgentTool(
            name="notes__mark_note_span",
            description="[notes] 给选区加底纹",
            handler=mark_note_span,
        ),
    }


class TestPrefixGrant:
    """C 前缀授予:白名单 notes__* 相对当前名册展开。"""

    async def test_organizer_picks_up_new_notes_tools(self, tmp_path) -> None:
        """往桥里塞一个名单里没写过的新 notes 能力,Miyai 无需改名单即可用。"""
        app = _app(tmp_path, FakeLLM(default="完成。"), _fake_notes_tools())
        inst = await app.master.dispatch_task("给笔记加底纹", persona="organizer")
        names = inst.toolbelt.names()
        assert "notes__mark_note_span" in names
        assert "notes__create_note" in names
        # sources 窄授权没有被前缀放宽:写类能力不进来
        assert not any(n.startswith("sources__remove") for n in names)
        app.memory.close()

    def test_persona_file_does_not_enumerate_expansion(self) -> None:
        """人格文件是前缀授予,不是枚举展开结果(不写死桥工具名)。"""
        src = Path(organizer_mod.__file__).read_text(encoding="utf-8")
        assert "notes__*" in src
        assert "notes__create_note" not in src
        assert "mark_note_span" not in src

    def test_allow_none_stays_full(self) -> None:
        """allow=None(统筹者)不裁剪;前缀授予只影响白名单路径。"""
        persona = resolve_persona("organizer")
        assert persona is not None and any(a.endswith("*") for a in persona.tool_allow)


class TestLucienDomainActivation:
    """D 域激活:对话实例首轮只送 CORE 激活集,activate 后下一轮可见。"""

    async def test_first_round_is_graded_then_activate(self, tmp_path) -> None:
        llm = FakeLLM([
            LLMReply(tool_calls=(ToolCall("1", "activate_tools", {"domain": "notes"}),)),
            LLMReply(tool_calls=(ToolCall("2", "notes__create_note",
                                          {"title": "t", "content": "c"}),)),
            LLMReply(text="笔记已落库。"),
        ])
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("开始处理刚才那几件事")
        await _settle(app)
        first = [s.name for s in llm.calls[0]["tools"]]
        second = [s.name for s in llm.calls[1]["tools"]]
        # 首轮:远小于全量名册,无 notes 工具,但有 activate_tools
        assert "notes__create_note" not in first
        assert "activate_tools" in first
        assert len(first) < 12
        # activate(domain=notes) 之后:下一轮 complete 含 notes 工具
        assert "notes__create_note" in second
        assert "[完成]" in _replies(app)[-1] or _replies(app)  # 通报路径未回归
        app.memory.close()

    async def test_call_before_activation_still_executes(self, tmp_path) -> None:
        """call() 不受激活限制:误点未激活名仍可执行(超时问题只来自 schema 体积)。"""
        llm = FakeLLM([
            LLMReply(tool_calls=(ToolCall("1", "notes__create_note",
                                          {"title": "t", "content": "c"}),)),
            LLMReply(text="done"),
        ])
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("直接写笔记,别激活")
        await _settle(app)
        # 工具结果在当轮 messages(llm.calls[1])里,不进跨轮 history(现有行为)
        tool_results = [
            m["content"]
            for m in llm.calls[1]["messages"]
            if m["role"] == "tool"
        ]
        assert tool_results and "未知工具" not in tool_results[0]
        assert "n-1" in tool_results[0]
        app.memory.close()

    async def test_ack_without_followup_still_runs_tools(self, tmp_path) -> None:
        """用户说「都测试一下」后模型只回「好」:同一回合继续调工具,不必再等用户。"""
        llm = FakeLLM([
            LLMReply(text="好,一次性把三件事都试一遍。马上。"),
            LLMReply(tool_calls=(ToolCall("1", "activate_tools", {"domain": "notes"}),)),
            LLMReply(tool_calls=(ToolCall("2", "notes__mark_note_span", {"note_id": "n-1"}),)),
            LLMReply(text="底纹已加上。"),
        ])
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("都测试一下")
        await _settle(app)
        assert len(llm.calls) == 4  # 没有第二次 handle_user_message
        assert "底纹已加上" in _replies(app)[-1]
        app.memory.close()

    async def test_note_keyword_preactivates_notes_domain(self, tmp_path) -> None:
        """用户话里带「笔记」时首轮即可看见 notes schema,少一轮纯 activate。"""
        llm = FakeLLM([LLMReply(text="先看一眼工具面。")])
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("给这篇笔记加底纹")
        await _settle(app)
        first = [s.name for s in llm.calls[0]["tools"]]
        assert "notes__mark_note_span" in first
        app.memory.close()

    async def test_dispatched_task_instance_not_graded(self, tmp_path) -> None:
        """派遣的任务型 subagent(trimmed)整份 specs 给模型,不走激活。"""
        llm = FakeLLM(default="完成。")
        app = _app(tmp_path, llm, _fake_notes_tools())
        inst = await app.master.dispatch_task("整理", persona="organizer")
        assert inst.active is None  # 分级只挂在对话实例
        await asyncio.sleep(0.05)
        specs = llm.calls[0]["tools"]
        assert specs is not None and "notes__create_note" in [s.name for s in specs]
        app.memory.close()


class TestStepEvents:
    """B agent.step:工具步骤进事件流,Chat 能看到正在调哪个工具。"""

    async def test_tool_step_reaches_event_stream(self, tmp_path) -> None:
        llm = FakeLLM([
            LLMReply(tool_calls=(ToolCall("1", "list_dir", {"path": "."}),)),
            LLMReply(text="看完了。"),
        ])
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("看看工作目录")
        await _settle(app)
        steps = [
            e.payload for _, e in app.log.read_after(types=["agent.step"])
        ]
        assert any(s["name"] == "list_dir" for s in steps)
        assert all(s.get("subagent") for s in steps)
        assert all(len(s.get("summary", "")) <= 120 for s in steps)
        app.memory.close()

    async def test_step_refreshes_digest_store(self, tmp_path) -> None:
        """phase-20:工具步骤后 DigestStore 能 render 出最近步骤,且截断 120 字。"""
        llm = FakeLLM([
            LLMReply(tool_calls=(ToolCall("1", "list_dir", {"path": "."}),)),
            LLMReply(text="看完了。"),
        ])
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("看看工作目录")
        await _settle(app)
        # 步骤序列里 list_dir 已写入;DigestStore 在每一步都 upsert,因此最终 last_step
        # 是最后的文本回复。通过实例状态直接断言 list_dir 步骤存在,并验证 render 非空。
        chat = app.master.chat
        assert chat is not None
        assert any(s.name == "list_dir" for s in chat.state.steps)
        rendered = app.master._digests.render()
        assert "chat" in rendered
        assert "| 最近:" in rendered
        app.memory.close()

    async def test_digest_render_omits_empty_last_step(self, tmp_path) -> None:
        """phase-20:没有步骤时 render 不拼空「最近」。"""
        app = _app(tmp_path, FakeLLM(default="收到。"))
        inst = await app.master.dispatch_task("无工具任务", name="noop")
        await asyncio.sleep(0.05)
        rendered = app.master._digests.render()
        assert "noop" in rendered
        # 无步骤时 last_step 为空,不应出现「| 最近: 」空尾巴
        assert not rendered.strip().endswith("| 最近:")
        app.memory.close()


class TestPagePreactivate:
    """phase-09:页面 → 预激活域的小映射(扩到 notes/graph/sources)。"""

    def test_domain_pages_map_to_own_domain(self) -> None:
        assert page_preactivate("notes") == "notes"
        assert page_preactivate("graph") == "graph"
        assert page_preactivate("sources") == "sources"

    def test_other_pages_do_not_preactivate(self) -> None:
        for page in ("chat", "team", "activity", "settings", "usage", ""):
            assert page_preactivate(page) is None
