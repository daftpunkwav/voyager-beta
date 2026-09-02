"""subagent 相关能力:列出、注册、急停、可恢复 checkpoint 与恢复/放弃。"""

from __future__ import annotations

import asyncio

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_subagents", description="已注册的 subagent 定义 + 运行中实例")
    def list_subagents() -> dict:
        return {
            "definitions": [
                {"name": d.name, "mode": d.mode, "description": d.description,
                 "persona": d.persona, "allowed_tools": list(d.allowed_tools)
                 if d.allowed_tools else None,
                 "max_rounds": d.max_rounds, "max_tool_calls": d.max_tool_calls,
                 "network_mode": d.network_mode}
                for d in deps.subagents.list()
            ],
            "running": [
                {
                    "id": i.id, "name": i.name, "status": i.status.value,
                    "goal": i.task.goal, "started_ts": i.state.started_ts,
                    "last_step": (
                        (i.state.steps[-1].summary or "")[:120]
                        if i.state.steps else ""
                    ),
                }
                for i in deps.spawner.instances.values()
            ],
        }

    @capability(reg, name="cancel_run", description="急停运行中的 subagent(按 id 或 name;'chat'=对话主实例)",
                cost=1)
    async def cancel_run(id_or_name: str) -> dict:
        """用户与 agent 都可急停(修复 Parity:原来双方都缺 kill switch)。"""
        cancelled = await deps.spawner.cancel(id_or_name)
        if not cancelled:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND,
                f"没有匹配的运行中实例: {id_or_name}",
                hint="list_subagents 查看运行中实例",
            )
        return {"cancelled": cancelled}

    @capability(reg, name="register_subagent", description="注册自建 subagent 定义",
                cost=2)
    def register_subagent(name: str, description: str, mode: str = "react",
                          allowed_tools: list[str] | None = None,
                          persona: str = "",
                          max_rounds: int | None = None,
                          max_tool_calls: int | None = None,
                          network_mode: str = "") -> dict:
        """写入 SubagentRegistry;mode 取七种模式枚举(非法值 AGENT.INVALID_INPUT)。

        allowed_tools 是能力面白名单裁剪(Toolbelt.trimmed,§9.4.1):
        不给 write_file 就是真的不能写,不是提示词约束;None = 不裁剪。
        max_rounds / max_tool_calls / network_mode 是权限档位覆盖(§9.9/§9.19):
        轮数不传跟随全局,网络档位空串继承全局;派出时只能比全局更严。
        """
        from agent.subagent.registry import SubagentDef

        d = SubagentDef(
            name=name, description=description, mode=mode, persona=persona,
            allowed_tools=tuple(allowed_tools) if allowed_tools else None,
            max_rounds=max_rounds, max_tool_calls=max_tool_calls,
            network_mode=network_mode or "",
        )
        deps.subagents.save(d)
        return {"name": d.name, "mode": d.mode, "allowed_tools": allowed_tools,
                "max_rounds": d.max_rounds, "max_tool_calls": d.max_tool_calls,
                "network_mode": d.network_mode}

    @capability(reg, name="list_resumable_checkpoints",
                description="可恢复的任务 checkpoint(进程重启后待恢复;任务型 REACT)")
    def list_resumable_checkpoints() -> dict:
        """盘上 alive 且带 resume 快照的 checkpoint(phase-69,§9.17)。

        只列本刀范围:mode=react 且非对话型;快照按 ResumeSnapshot 解析,
        残缺/非 dict 的坏条目跳过不给入口(与 37/38「坏文件不炸」同模式);
        legacy 无快照已被启动标 failed,不在 alive。
        """
        from agent.runtime.state import ResumeSnapshot

        items = []
        for st in deps.checkpoints.list_alive():
            raw = st.resume
            if not isinstance(raw, dict):
                continue
            try:
                snap = ResumeSnapshot.from_dict(raw)
            except TypeError:
                continue
            if snap.mode != "react" or snap.conversational:
                continue
            items.append({
                "run_id": st.run_id,
                "status": st.status.value,
                "goal": snap.goal or st.task,
                "instance_name": snap.instance_name,
                "started_ts": st.started_ts,
                "last_step": (st.steps[-1].summary or "")[:120] if st.steps else "",
                "mode": snap.mode,
            })
        return {"items": items}

    @capability(reg, name="abandon_resumable_checkpoint",
                description="放弃可恢复 checkpoint(删盘;内存实例一并停止并移除)", cost=1)
    async def abandon_resumable_checkpoint(run_id: str) -> dict:
        """放弃一个可恢复 checkpoint(phase-70,§9.17):删盘 + 清内存实例。

        NOT_FOUND 口径与 resume_run 一致:文件不存在 / 无恢复快照(legacy)/
        快照损坏都拒。有合法快照即可弃(比恢复列表宽:对话型 / 非 react 的
        孤儿 checkpoint 列表不收,本能力是它们唯一的清理通道)。
        内存里该 run 的实例:alive 先走 spawner.cancel(置 CANCELLED + 打断
        底层任务 + AgentCancelled 事件),然后从 instances 移除,
        list_subagents 不再出现。
        """
        from agent.runtime.state import ResumeSnapshot

        try:
            state = deps.checkpoints.load(run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND, f"checkpoint 不存在: {run_id}"
            ) from exc
        snap = None
        if isinstance(state.resume, dict):
            try:
                snap = ResumeSnapshot.from_dict(state.resume)
            except TypeError:
                snap = None
        if snap is None:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND,
                f"checkpoint {run_id} 无恢复快照(legacy),不可放弃",
            )
        hits = [
            inst.id for inst in deps.spawner.instances.values()
            if inst.state.run_id == run_id
        ]
        for inst_id in hits:
            inst = deps.spawner.instances.get(inst_id)  # await 间隙可能被并发移除
            if inst is not None and inst.status.alive:
                await deps.spawner.cancel(inst_id)
        for inst_id in hits:
            deps.spawner.instances.pop(inst_id, None)
        deps.checkpoints.delete(run_id)
        return {"abandoned": run_id}

    @capability(reg, name="resume_run",
                description="从 checkpoint 恢复任务实例(任务型 REACT;continue_run=true 立即续跑)",
                cost=2)
    async def resume_run(run_id: str, continue_run: bool = False) -> dict:
        """重建实例进内存(continue_run=false,状态保持 PAUSED 供 UI 稍后继续);
        continue_run=true 时后台续跑整轮 ReAct(与 dispatch_task 同为后台,不阻塞)。"""
        inst = deps.spawner.resume_from_checkpoint(run_id)
        out = {
            "resumed": inst.id,
            "run_id": run_id,
            "status": inst.status.value,
            "continuing": False,
        }
        if continue_run:

            async def _run() -> None:
                try:
                    await deps.spawner.start(inst)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001, S110  # run_turn 已落状态并发 RunFailed;此处无 master 通道可报
                    pass

            asyncio.create_task(_run())
            out["continuing"] = True
        return out
