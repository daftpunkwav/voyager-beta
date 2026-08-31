"""任务派单(§9.4):把 Master 的派遣逻辑抽到独立模块。

只负责按 persona / mode / tools / network 档位装配 TaskBook,
后台启动 subagent 并在完成/失败时回调查询 master 的 _reply。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from agent.master.settings_store_protocol import SettingsReader
from agent.personas import resolve_persona
from agent.policy import NetworkPolicy, PolicyEngine, narrow_network
from agent.subagent import Mode, Spawner, SubagentInstance, TaskBook
from agent.subagent.registry import SubagentDef, SubagentRegistry
from agent.tools.base import Toolbelt

if TYPE_CHECKING:
    from agent.master.master import Master


async def dispatch_task(
    master: "Master",
    spawner: Spawner,
    settings: SettingsReader,
    policy: PolicyEngine | None,
    subagents: SubagentRegistry | None,
    hooks,
    goal: str,
    *,
    persona: str = "",
    mode: str | None = None,
    allowed_tools: tuple[str, ...] | None = None,
    name: str = "",
    constraints: str = "",
) -> SubagentInstance:
    """派单实现。

    persona 先查内置预设;查不到再查自建 subagent 注册表(§9.4.4,
    对 master 与预设同构:套用其 mode 与 allowed_tools 白名单)。
    """
    from agent.master.master import limits_from_settings

    preset = resolve_persona(persona) if persona else None
    custom = _load_custom(subagents, persona) if persona and preset is None else None
    if custom is not None:
        if mode is None:
            mode = custom.mode
        if allowed_tools is None:
            allowed_tools = custom.allowed_tools
        constraints = f"{constraints}\n{custom.description}".strip()
    elif preset is not None and preset.key == "orchestrator":
        mode = Mode.REACT.value  # 统筹者强制 ReAct(决策 §15)
    if allowed_tools is None and preset is not None:
        allowed_tools = preset.tool_allow
    limits = limits_from_settings(
        settings,
        max_rounds=custom.max_rounds if custom is not None else None,
        max_tool_calls=custom.max_tool_calls if custom is not None else None,
    )
    task = TaskBook(
        goal=goal,
        constraints=constraints,
        mode=Mode(mode) if mode else None,
        allowed_tools=allowed_tools,
        limits=limits,
    )
    spawn_key = preset.key if preset is not None else persona
    inst = spawner.spawn(task, persona=spawn_key, name=name or goal[:16])
    if custom is not None and custom.network_mode:
        inst.toolbelt = _narrowed_toolbelt(inst.toolbelt, custom.network_mode, settings, policy)
    master.digests.upsert(inst)
    if hooks is not None:
        await hooks.fire("on_subagent_start", subagent=inst.id, goal=goal)

    async def _run() -> None:
        try:
            result = await spawner.start(inst)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001  # run_turn 已落状态;这里只通报
            await master._reply(f"[失败] {inst.name}:{type(exc).__name__}: {exc}")
        else:
            await master._reply(f"[完成] {inst.name}:{result[:200]}")
        finally:
            master.digests.upsert(inst)
            if hooks is not None:
                await hooks.fire("on_subagent_end", subagent=inst.id)

    task_handle = asyncio.create_task(_run())
    master.background.add(task_handle)
    task_handle.add_done_callback(master.background.discard)
    return inst


def _load_custom(subagents: SubagentRegistry | None, name: str) -> SubagentDef | None:
    """按名取自建 subagent 定义;未注册返回 None(按普通无名任务处理)。"""
    from platform_contracts import ServiceError

    if subagents is None:
        return None
    try:
        return subagents.load(name)
    except ServiceError:
        return None


def _narrowed_toolbelt(
    belt: Toolbelt,
    requested_mode: str,
    settings: SettingsReader,
    policy: PolicyEngine | None,
) -> Toolbelt:
    """自建 subagent 指定网络档位时的实例专属工具带(§9.9「派出再裁,只能更严」)。

    同一(已裁剪)工具表换一份新 PolicyEngine:fs/app 复用全局,网络档位取
    narrow_network(全局, 自建),域名用全局 agent.network.domains。
    拷贝不带 settings 句柄——任务中途全局放宽不回灌到已派出实例。
    """
    global_mode = str(settings.get("agent.network.mode") or "")
    domains = tuple(settings.get("agent.network.domains") or ())
    engine = PolicyEngine(
        network=NetworkPolicy(
            mode=narrow_network(global_mode, requested_mode), domains=domains
        ),
        fs=policy.fs if policy is not None else None,
        app=policy.app if policy is not None else None,
    )
    return belt.with_policy(engine)
