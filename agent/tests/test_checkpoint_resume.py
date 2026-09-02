"""checkpoint resume 后端(phase-69/70/71,§9.17):boot PAUSED、恢复列表、
实例重建、拒绝路径、ReAct 中途增量存盘与续跑。

范围(任务书 E):任务型 + 非 conversational + mode=react;
对话型 / 无快照 / 其它 mode / 终态 返回明确错误。
phase-71 起每步增量存盘,ReAct 中途崩溃可从中途续跑,不重复已完成 tool 步。
"""

import asyncio
import json

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.runtime.state import CheckpointStore, ResumeSnapshot, RunState, RunStatus
from agent.subagent import Mode, TaskBook

USER_CTX = ActorContext(actor=LOCAL_USER)


def _snapshot(**overrides) -> ResumeSnapshot:
    base: dict = {
        "instance_id": "instabcd",
        "instance_name": "侦察兵",
        "persona": "recon",
        "goal": "索引仓库",
        "constraints": "只读",
        "done_when": "产出清单",
        "mode": "react",
        "allowed_tools": ["list_dir"],
        "max_rounds": 5,
        "max_tool_calls": None,
        "conversational": False,
        "history": [{"role": "user", "content": "开始"}],
        "active_tools": [],
    }
    base.update(overrides)
    return ResumeSnapshot(**base)


def _seed_checkpoint(
    rd, snap: ResumeSnapshot, *, run_id="runresum001",
    status=RunStatus.RUNNING, with_resume=True,
) -> RunState:
    """boot 前预写 checkpoint(与 build_agent 同目录)。"""
    store = CheckpointStore(rd / "checkpoints")
    state = RunState(task=snap.goal, run_id=run_id, status=status)
    state.add_step("llm", "round-1", "第 1 轮")
    if with_resume:
        state.resume = snap.to_dict()
    store.save(state)
    return state


def _build(tmp_path):
    return build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
    )


class TestSnapshotData:
    def test_snapshot_roundtrip(self) -> None:
        snap = _snapshot(max_tool_calls=9, active_tools=["notes", "web"])
        assert ResumeSnapshot.from_dict(snap.to_dict()) == snap

    def test_phase71_fields_default_and_old_json_loads(self) -> None:
        """A 验收:新字段有缺省;旧 JSON(无新键)可读,与 69 快照等价。"""
        snap = _snapshot()
        assert snap.pending_messages is None
        assert snap.in_turn is False
        data = snap.to_dict()
        assert "pending_messages" in data and "in_turn" in data
        old = {k: v for k, v in data.items() if k not in ("pending_messages", "in_turn")}
        assert ResumeSnapshot.from_dict(old) == snap

    def test_old_checkpoint_without_resume_loads(self, tmp_path) -> None:
        """旧版 checkpoint(无 resume 键)可读:resume=None,不炸。"""
        cp = tmp_path / "checkpoints"
        store = CheckpointStore(cp)
        (cp / "oldrun00001.json").write_text(
            json.dumps({"task": "旧任务", "status": "running"}), encoding="utf-8"
        )
        state = store.load("oldrun00001")
        assert state.resume is None
        assert state.status is RunStatus.RUNNING


class TestBootAndList:
    async def test_boot_paused_and_listed(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            store = CheckpointStore(rd / "checkpoints")
            loaded = store.load(state.run_id)
            assert loaded.status is RunStatus.PAUSED
            assert loaded.error == "进程重启,可恢复"
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert [i["run_id"] for i in out["items"]] == [state.run_id]
            item = out["items"][0]
            assert item["status"] == "paused"
            assert item["goal"] == "索引仓库"
            assert item["instance_name"] == "侦察兵"
            assert item["mode"] == "react"
            assert item["last_step"] == "第 1 轮"
            assert item["started_ts"] == loaded.started_ts
        finally:
            app.memory.close()

    async def test_list_excludes_legacy_conversational_and_non_react(self, tmp_path) -> None:
        """列表只收 任务型+react+有快照;legacy boot 已标 failed 不在 alive。"""
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(), run_id="legacy00001", with_resume=False)
        _seed_checkpoint(
            rd, _snapshot(conversational=True, instance_id="instchat1"),
            run_id="convres001",
        )
        _seed_checkpoint(rd, _snapshot(mode="direct"), run_id="directres01")
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert out["items"] == []
            store = CheckpointStore(rd / "checkpoints")
            assert store.load("legacy00001").status is RunStatus.FAILED
            # 对话型/其它模式带快照:boot 机械转 PAUSED 存活,只是不给恢复入口
            assert store.load("convres001").status is RunStatus.PAUSED
            assert store.load("directres01").status is RunStatus.PAUSED
        finally:
            app.memory.close()


class TestResumeRun:
    async def test_resume_rebuilds_instance_without_continuing(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            out = await execute(
                app.registry, "resume_run", USER_CTX, {"run_id": state.run_id}
            )
            assert out["resumed"] == "instabcd"
            assert out["continuing"] is False
            inst = app.spawner.instances["instabcd"]
            assert inst.state.run_id == state.run_id
            assert inst.status is RunStatus.PAUSED  # 只重建不重跑
            assert inst.history == [{"role": "user", "content": "开始"}]
            assert inst.task.goal == "索引仓库"
            assert inst.task.constraints == "只读"
            assert inst.task.done_when == "产出清单"
            assert inst.task.mode is Mode.REACT
            assert inst.task.allowed_tools == ("list_dir",)
            assert inst.task.limits is not None
            assert inst.task.limits.max_rounds == 5
            assert inst.persona == "recon"
            assert inst.name == "侦察兵"
            # 同 run 已有存活实例(PAUSED 也算 alive):重复恢复拒绝
            with pytest.raises(ServiceError):
                await execute(
                    app.registry, "resume_run", USER_CTX, {"run_id": state.run_id}
                )
        finally:
            app.memory.close()

    async def test_resume_continue_completes_task(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            out = await execute(
                app.registry, "resume_run", USER_CTX,
                {"run_id": state.run_id, "continue_run": True},
            )
            assert out["continuing"] is True
            await asyncio.sleep(0.1)
            inst = app.spawner.instances["instabcd"]
            assert inst.status is RunStatus.COMPLETED
            assert inst.state.result
            # 续跑完 checkpoint 重落盘:状态非 alive,不再出现在恢复列表
            listed = await execute(
                app.registry, "list_resumable_checkpoints", USER_CTX, {}
            )
            assert listed["items"] == []
        finally:
            app.memory.close()


class TestMidTurnCheckpoint:
    """phase-71(§9.17):ReAct 中途增量存盘 → boot PAUSED → resume 从中途续跑。"""

    async def test_mid_turn_save_and_resume_continues_without_redo(self, tmp_path) -> None:
        """D 验收:round-1 调 tool、round-2 前崩溃 → resume 续跑完成,tool 只调一次。"""
        rd = tmp_path / "rd"
        hang = asyncio.Event()
        n_calls = {"n": 0}

        async def _script(messages, tools):
            n_calls["n"] += 1
            if n_calls["n"] == 1:  # round-1:请求 list_dir
                return LLMReply(
                    tool_calls=(ToolCall(id="c1", name="list_dir", arguments={"path": "."}),)
                )
            await hang.wait()  # round-2 complete 挂起 = 崩溃点
            return LLMReply(text="不应到达")

        app = build_agent(
            data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM(dynamic=_script)
        )
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="中途存盘", mode=Mode.REACT, allowed_tools=("list_dir",)),
                persona="recon", name="scout",
            )
            # 绕过 spawner.start 驱动 run_turn:进程死亡不会执行 start 的
            # finally 存盘,盘上应保留最后一步的 mid-turn 快照
            turn = asyncio.create_task(inst.run_turn())
            store = CheckpointStore(rd / "checkpoints")
            # B 验收:轮询等待 tool 步的增量存盘落盘(含刚落地的 tool 行)
            for _ in range(500):
                await asyncio.sleep(0.01)
                if not (rd / "checkpoints" / f"{inst.state.run_id}.json").exists():
                    continue  # 首个存盘点(第 1 步 on_step)尚未发生
                saved = store.load(inst.state.run_id).resume
                if (
                    isinstance(saved, dict)
                    and saved.get("in_turn")
                    and any(
                        m.get("role") == "tool"
                        for m in saved.get("pending_messages") or []
                    )
                ):
                    break
            else:
                pytest.fail("tool 步后未见 mid-turn 快照落盘")
            pending = saved["pending_messages"]
            # 快照形状:成对回填(system 起步,assistant(tool_calls) 与 tool 同组)
            assert [m["role"] for m in pending] == ["system", "assistant", "tool"]
            assert pending[1]["tool_calls"][0]["id"] == "c1"
            assert pending[2]["tool_call_id"] == "c1"
            assert inst.state.tool_calls == 1
            assert inst.state.rounds == 1

            # 模拟进程被杀:硬取消,盘上 mid-turn 快照不被 turn 边界覆盖
            turn.cancel()
            await asyncio.gather(turn, return_exceptions=True)
            assert store.load(inst.state.run_id).resume["in_turn"] is True
            assert store.load(inst.state.run_id).status is RunStatus.RUNNING
        finally:
            app.close()

        # “重启”:同一数据目录重建 app → boot 转 PAUSED → resume 续跑
        llm2 = FakeLLM(script=[LLMReply(text="目录清点完成。")])
        app2 = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=llm2)
        try:
            out = await execute(
                app2.registry, "resume_run", USER_CTX,
                {"run_id": inst.state.run_id, "continue_run": True},
            )
            assert out["continuing"] is True
            await asyncio.sleep(0.1)
            inst2 = app2.spawner.instances[inst.id]
            assert inst2.status is RunStatus.COMPLETED
            assert inst2.state.result == "目录清点完成。"
            # C 验收:续跑只做了一次 complete(崩溃点的下一轮);
            # list_dir 不重复执行(结果已在 transcript)
            assert len(llm2.calls) == 1
            assert inst2.state.tool_calls == 1
            assert inst2.state.rounds == 2
            msgs = llm2.calls[0]["messages"]
            assert [m["role"] for m in msgs] == ["system", "assistant", "tool"]
            assert msgs[2]["content"] == pending[2]["content"]
            # 续跑完 turn 边界快照覆盖中途快照:in_turn 复位、状态终态
            final = CheckpointStore(rd / "checkpoints").load(inst.state.run_id)
            assert final.status is RunStatus.COMPLETED
            assert final.resume["in_turn"] is False
        finally:
            app2.close()

    def test_snapshot_repairs_unpaired_tail(self, tmp_path) -> None:
        """崩在多工具轮中途:尾部残组(assistant 带 tool_calls 但 tool 行未齐)整体回退。"""
        app = _build(tmp_path)
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="残组回退", mode=Mode.REACT, allowed_tools=("list_dir",)),
                persona="recon",
            )
            inst._turn_messages = [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "",
                 "tool_calls": [{"id": "a"}, {"id": "b"}]},
                {"role": "tool", "tool_call_id": "a", "name": "list_dir", "content": "r1"},
            ]
            snap = inst.build_resume_snapshot(
                in_turn=True, pending_messages=inst._turn_messages
            )
            assert snap.in_turn is True
            assert [m["role"] for m in snap.pending_messages] == ["system", "user"]
            # 缺省调用 = turn 边界快照,与 phase-69 行为一致
            plain = inst.build_resume_snapshot()
            assert plain.pending_messages is None
            assert plain.in_turn is False
        finally:
            app.memory.close()

    async def test_in_turn_without_pending_falls_back_to_turn_boundary(self, tmp_path) -> None:
        """in_turn=True 但 pending_messages 缺失:退回 69 行为(history 重建 + 新开 turn)。"""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot(in_turn=True))
        app = _build(tmp_path)
        try:
            await execute(
                app.registry, "resume_run", USER_CTX,
                {"run_id": state.run_id, "continue_run": True},
            )
            await asyncio.sleep(0.1)
            inst = app.spawner.instances["instabcd"]
            assert inst.status is RunStatus.COMPLETED
            assert inst.history[-1] == {"role": "assistant", "content": "收到。"}
        finally:
            app.memory.close()

    async def test_in_turn_corrupt_pending_rejected(self, tmp_path) -> None:
        """pending_messages 结构残缺(非 list / 含非 dict):拒为 NOT_FOUND,不留半建实例。"""
        rd = tmp_path / "rd"
        _seed_checkpoint(
            rd, _snapshot(in_turn=True, pending_messages="garbage"), run_id="badpend01",
        )
        _seed_checkpoint(
            rd, _snapshot(in_turn=True, pending_messages=[1, 2]), run_id="badpend02",
        )
        app = _build(tmp_path)
        try:
            for rid in ("badpend01", "badpend02"):
                with pytest.raises(ServiceError) as exc:
                    await execute(app.registry, "resume_run", USER_CTX, {"run_id": rid})
                assert exc.value.body.code == "AGENT.NOT_FOUND", rid
            assert app.spawner.instances == {}  # 拒绝时不留半建实例
        finally:
            app.memory.close()


class TestResumeRejections:
    async def test_legacy_without_snapshot_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot(), run_id="legacy00001", with_resume=False)
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert out["items"] == []  # legacy 已被 boot 标 failed,不在 alive
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "resume_run", USER_CTX, {"run_id": state.run_id}
                )
            assert exc.value.body.code == "AGENT.NOT_FOUND"
        finally:
            app.memory.close()

    async def test_conversational_snapshot_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(conversational=True), run_id="convres001")
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "resume_run", USER_CTX, {"run_id": "convres001"}
                )
            assert exc.value.body.code == "AGENT.INVALID_INPUT"
        finally:
            app.memory.close()

    async def test_non_react_mode_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(mode="direct"), run_id="directres01")
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "resume_run", USER_CTX, {"run_id": "directres01"}
                )
            assert exc.value.body.code == "AGENT.INVALID_INPUT"
        finally:
            app.memory.close()

    async def test_terminal_status_rejected(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        _seed_checkpoint(rd, _snapshot(), run_id="doneresum01", status=RunStatus.COMPLETED)
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "resume_run", USER_CTX, {"run_id": "doneresum01"}
                )
            assert exc.value.body.code == "AGENT.INVALID_INPUT"
        finally:
            app.memory.close()

    async def test_missing_checkpoint_rejected(self, tmp_path) -> None:
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "resume_run", USER_CTX, {"run_id": "nosuchrun1"}
                )
            assert exc.value.body.code == "AGENT.NOT_FOUND"
        finally:
            app.memory.close()

    async def test_corrupt_snapshot_rejected_and_not_listed(self, tmp_path) -> None:
        """快照残缺(缺必填键)/非 dict:列表跳过,resume 拒为 NOT_FOUND,不裸抛 TypeError。"""
        rd = tmp_path / "rd"
        store = CheckpointStore(rd / "checkpoints")
        for rid, bad_resume in (
            ("corruptres1", {"mode": "react", "goal": "缺 id"}),  # 缺 instance_id 等必填键
            ("corruptres2", "garbage"),  # 非 dict
        ):
            st = RunState(task="坏快照", run_id=rid, status=RunStatus.RUNNING)
            st.resume = bad_resume
            store.save(st)
        app = _build(tmp_path)
        try:
            out = await execute(app.registry, "list_resumable_checkpoints", USER_CTX, {})
            assert out["items"] == []
            for rid in ("corruptres1", "corruptres2"):
                with pytest.raises(ServiceError) as exc:
                    await execute(
                        app.registry, "resume_run", USER_CTX, {"run_id": rid}
                    )
                assert exc.value.body.code == "AGENT.NOT_FOUND", rid
        finally:
            app.memory.close()


class TestAbandonCheckpoint:
    """放弃可恢复 checkpoint(phase-70,§9.17):删盘 + 清内存实例,口径同 resume_run。"""

    async def test_abandon_deletes_file_and_empties_list(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            out = await execute(
                app.registry, "abandon_resumable_checkpoint", USER_CTX,
                {"run_id": state.run_id},
            )
            assert out == {"abandoned": state.run_id}
            # 盘上文件已删,列表不再出现
            assert not (rd / "checkpoints" / f"{state.run_id}.json").exists()
            listed = await execute(
                app.registry, "list_resumable_checkpoints", USER_CTX, {}
            )
            assert listed["items"] == []
        finally:
            app.memory.close()

    async def test_abandon_missing_run_not_found(self, tmp_path) -> None:
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "abandon_resumable_checkpoint", USER_CTX,
                    {"run_id": "nosuchrun1"},
                )
            assert exc.value.body.code == "AGENT.NOT_FOUND"
        finally:
            app.memory.close()

    async def test_abandon_legacy_without_snapshot_not_found(self, tmp_path) -> None:
        """legacy 无快照不可放弃,口径与 resume_run 一致(NOT_FOUND)。"""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot(), run_id="legacy00001", with_resume=False)
        app = _build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry, "abandon_resumable_checkpoint", USER_CTX,
                    {"run_id": state.run_id},
                )
            assert exc.value.body.code == "AGENT.NOT_FOUND"
            # 拒绝时不误删盘
            assert (rd / "checkpoints" / "legacy00001.json").exists()
        finally:
            app.memory.close()

    async def test_abandon_allows_conversational_snapshot(self, tmp_path) -> None:
        """放弃比列表宽:对话型带合法快照的孤儿 checkpoint 列表不收,但可弃
        (这是它们唯一的清理通道;行为钉住防未来无意收紧)。"""
        rd = tmp_path / "rd"
        _seed_checkpoint(
            rd, _snapshot(conversational=True, instance_id="instchat1"),
            run_id="convres001",
        )
        app = _build(tmp_path)
        try:
            listed = await execute(
                app.registry, "list_resumable_checkpoints", USER_CTX, {}
            )
            assert listed["items"] == []  # 列表不收
            out = await execute(
                app.registry, "abandon_resumable_checkpoint", USER_CTX,
                {"run_id": "convres001"},
            )
            assert out == {"abandoned": "convres001"}
            assert not (rd / "checkpoints" / "convres001.json").exists()
        finally:
            app.memory.close()

    async def test_abandon_after_resume_removes_instance(self, tmp_path) -> None:
        """resume 重建(PAUSED=alive)后放弃:实例从 list_subagents 消失 + 删盘。"""
        rd = tmp_path / "rd"
        state = _seed_checkpoint(rd, _snapshot())
        app = _build(tmp_path)
        try:
            await execute(app.registry, "resume_run", USER_CTX, {"run_id": state.run_id})
            running = (await execute(app.registry, "list_subagents", USER_CTX, {}))["running"]
            assert any(r["id"] == "instabcd" for r in running)

            await execute(
                app.registry, "abandon_resumable_checkpoint", USER_CTX,
                {"run_id": state.run_id},
            )
            running = (await execute(app.registry, "list_subagents", USER_CTX, {}))["running"]
            assert all(r["id"] != "instabcd" for r in running)
            assert state.run_id not in app.spawner.instances
        finally:
            app.memory.close()


class TestSnapshotOnSave:
    async def test_task_turn_end_checkpoint_has_snapshot(self, tmp_path) -> None:
        """A 验收:新 save 带 resume 快照;完成态不在 alive。"""
        app = _build(tmp_path)
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="小任务", mode=Mode.REACT, allowed_tools=("list_dir",)),
                persona="recon", name="小任务",
            )
            await app.spawner.start(inst)
            loaded = CheckpointStore(
                tmp_path / "rd" / "checkpoints"
            ).load(inst.state.run_id)
            assert loaded.status is RunStatus.COMPLETED
            assert loaded.resume is not None
            assert loaded.resume["goal"] == "小任务"
            assert loaded.resume["instance_id"] == inst.id
            assert loaded.resume["mode"] == "react"
            assert loaded.resume["conversational"] is False
        finally:
            app.memory.close()
