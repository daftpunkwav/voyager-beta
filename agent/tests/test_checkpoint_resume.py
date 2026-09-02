"""checkpoint resume 后端(phase-69,§9.17):boot PAUSED、恢复列表、实例重建、拒绝路径。

范围(任务书 E):任务型 + 非 conversational + mode=react;
对话型 / 无快照 / 其它 mode / 终态 返回明确错误。
限制(已知,写回披露):仅 turn 结束存盘,ReAct 中途崩溃丢当轮进度。
"""

import asyncio
import json

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

from agent.llm import FakeLLM
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
