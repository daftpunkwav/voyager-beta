"""进程入口(§5 main.py):装配全部组件,起事件循环,常驻。

运行:仓库根目录 `python -m agent.main`。
装配函数 build_agent 同时供 tests 使用(注入 FakeLLM / 临时目录)。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_eventbus import CursorStore, EventBus, EventLog
from platform_settings import SettingsStore

from agent.capabilities import CapabilityDeps, build_agent_registry
from agent.clients import McpClientPool
from agent.clients.pool import ConnectFn
from agent.context import ContextBuilder, OnDemandLoader, PageContextRegistry
from agent.context.rules import GLOBAL_RULES
from agent.hooks import HookLoader, HookRegistry
from agent.llm import FakeLLM, LLMClient
from agent.master import Arbiter, DigestStore, Master, ProactiveBudget, ProactiveEngine
from agent.memory import Memory
from agent.observe import Observer
from agent.personas import canonical_persona_key, resolve_persona
from agent.plugins import PluginManager
from agent.policy import AppPolicy, FsPolicy, NetworkPolicy, PolicyEngine
from agent.runtime import EventLoop, Meter, MeterStore, RuntimeEvents, Scheduler, metered_llm
from agent.runtime.state import CheckpointStore, prepare_resumable_checkpoints
from agent.runtime.wire import bind_event_loop
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.skills import SkillLoader
from agent.subagent import Spawner, SubagentRegistry
from agent.tools import (
    AgentTool,
    AskUser,
    Question,
    Toolbelt,
    ask_user_tool,
    ensure_workdir,
    fs_tools,
    load_skill_tool,
    reach_out_tool,
    recall_memory_tool,
    request_context_tool,
    shell_tools,
    spawn_tool,
    web_tools,
)


@dataclass
class AgentApp:
    """装配产物:进程内全部组件的句柄(tests 与 main 共用)。"""

    bus: EventBus
    log: EventLog
    settings: SettingsStore
    memory: Memory
    master: Master
    observer: Observer
    proactive: ProactiveEngine
    loop: EventLoop
    skills: SkillLoader
    hooks: HookRegistry
    pages: PageContextRegistry
    asker: AskUser
    spawner: Spawner
    registry: Any  # agent 能力注册表(§5 capabilities.py)
    mcp: McpClientPool  # 外接 MCP 连接池(phase-11b;空池合法)
    meter: Meter  # 内存计量(§9.9 资源维;metered_llm 与配额查询 capability 共用)
    plugins: PluginManager  # 插件发现与整包批准(phase-72,§9.13)
    owns_settings: bool = True  # 共享 store(聚合运行)时为 False,close 不关它
    owns_log: bool = True  # 共享 bus(聚合运行共用 EventLog)时为 False

    def close(self) -> None:
        """关闭持有文件句柄的组件(测试与关停路径用)。"""
        # 外接 MCP 会话:有 loop 就挂 task aclose,没有则同步尽力杀(不卡 pytest)
        self.mcp.close_best_effort()
        self.meter.close()  # meter.db 持久化连接(phase-66);纯内存 Meter 为 no-op
        self.memory.close()
        if self.owns_settings:
            self.settings.close()
        if self.owns_log:
            self.log.close()


def build_agent(
    *,
    data_dir: str | Path = "runtime-data",
    workspace_dir: str | Path | None = None,
    llm: LLMClient | None = None,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
    extra_tools: dict[str, AgentTool] | None = None,
    mcp_connect: ConnectFn | None = None,  # 外接 MCP 连接注入口(测试用 Fake)
    plugins_dir: str | Path | None = None,  # 插件根(默认仓库根 plugins/;测试注入临时目录)
) -> AgentApp:
    data_dir = Path(data_dir)
    llm = llm or FakeLLM()
    owns_log = bus is None

    log = EventLog(data_dir / "events.db")
    bus = bus or EventBus(log)
    cursors = CursorStore(log.conn)

    owns_settings = settings_store is None
    settings = settings_store or SettingsStore(data_dir / "settings.db", bus=bus)
    settings.register_fresh(AGENT_SETTING_DEFS)  # 幂等:只补尚未注册的 agent.* 键

    workspace = ensure_workdir(workspace_dir or settings.get("agent.workspace.dir"))
    memory = Memory(data_dir / "memory")
    pages = PageContextRegistry()
    asker = AskUser(bus)
    # skill roots(phase-11):内置 + 用户技能目录;插件 skill 未经批准不进索引
    skills_dir = workspace / "skills"  # agent 的家(§9.10),装配时创建
    skills_dir.mkdir(parents=True, exist_ok=True)
    skills = SkillLoader([Path(__file__).parent / "skills" / "builtin", skills_dir])
    # hook(phase-11):用户 hooks 目录声明式 hook 直接生效;插件目录不在此加载
    hooks = HookRegistry()
    HookLoader(hooks).load_dir(workspace / "hooks", source="user", approved=True)
    digests = DigestStore()
    on_demand = OnDemandLoader(skills=skills, memory=memory, pages=pages)

    # 附加只读根 + 附加读写根(phase-53/55,§9.9):policy 判定与 fs 工具层 jail
    # 都要放行(双层防护;write_roots 的写/删档位由 policy 判 L2 确认)
    read_roots = tuple(settings.get("agent.fs.read_roots") or ())
    write_roots = tuple(settings.get("agent.fs.write_roots") or ())
    policy = PolicyEngine(
        network=NetworkPolicy(
            mode=settings.get("agent.network.mode"),
            domains=tuple(settings.get("agent.network.domains")),
        ),
        fs=FsPolicy(roots=(str(workspace),), read_roots=read_roots, write_roots=write_roots),
        app=AppPolicy(
            allowed=frozenset(settings.get("agent.app.allowed")),
            denied=frozenset(settings.get("agent.app.denied")),
        ),
        settings=settings,  # 网络/app/fs(附加只读根)判定热读设置(§9.9):改设置不重启即生效
    )
    meter_store = MeterStore(data_dir / "meter.db")
    # 启动库维护(phase-68,§9.9):清 90 天前的历史日行,防 meter.db 随日期无限增长
    meter_store.purge_older_than_days(90)
    meter = Meter(store=meter_store)
    # token 日配额(phase-60/64,§9.9 资源维):主对话、派单、仲裁判官与主动问候
    # 的 LLM 均经同一 metered_llm 包装,complete 前热读 agent.resource.daily_tokens,
    # 当日累计超限不发起真实调用(0=不限)。
    chat_llm = metered_llm(
        llm, meter, quota_fn=lambda: settings.get("agent.resource.daily_tokens") or 0
    )
    events = RuntimeEvents(bus)

    async def _confirm(prompt: str) -> bool:
        """L2 确认经询问用户(§9.15);超时未答视为不同意。"""
        answer = await asker.ask(Question(prompt=prompt, kind="confirm"))
        return bool(answer)

    async def _notify(message: str) -> None:
        """L1 权限提示(§9.9):经事件流推到 Chat toast,不冒充对话。"""
        await events.emit("agent.policy.notify", message=message)

    _master: dict[str, Master] = {}  # spawn_subagent 工具与 master 互相引用,先占位

    def _provide_context(need: str) -> dict[str, str]:
        """request_context 的 master 侧:只给摘要,不共享全文(§9.6)。"""
        return {"need": need, "profile": memory.profile.render(), "subagents": digests.render()}

    tools: dict[str, AgentTool] = {}
    for group in (
        fs_tools(
            [workspace],
            read_roots=list(read_roots),
            write_roots=list(write_roots),
            read_roots_fn=lambda: list(settings.get("agent.fs.read_roots") or ()),
            write_roots_fn=lambda: list(settings.get("agent.fs.write_roots") or ()),
        ),
        shell_tools(workspace),
        web_tools(policy),
        ask_user_tool(asker),
        reach_out_tool(bus),
        load_skill_tool(on_demand),
        recall_memory_tool(on_demand),
        request_context_tool(_provide_context),
    ):
        tools.update(group)
    tools.update(spawn_tool(lambda *a, **kw: _master["master"].dispatch_task(*a, **kw)))
    tools.update(extra_tools or {})  # 领域能力桥(聚合运行注入,§9.4)
    toolbelt = Toolbelt(tools, policy, confirm=_confirm, notify=_notify, meter=meter, hooks=hooks)

    # 外接 MCP(phase-11b,§9.13):空池合法;批准动作经能力层 register 进根名册
    #(对话下一轮 from 根再拷即见),start() 只重连 enabled 且已批准的条目
    mcp = McpClientPool(settings=settings, toolbelt=toolbelt,
                        connect=mcp_connect, cwd=workspace)

    # 插件(phase-72/74,§9.13):清单可扫描(list 可见),装载仅限持久化批准名单
    # (整包 agent.plugins.approved 与分项 agent.plugins.approvals 的并集);
    # 名单里的插件目录已被删时跳过,不炸启动。MCP 条目只在批准动作登记,启动不重登记。
    # 事件订阅同步注入(phase-75):PluginManager 在 EventLoop 构造后才拿到,故先
    # 建 manager(不注入)跑启动装载,再补注入;注入后批准/撤销会实时把
    # hooks.event_patterns 推给 loop(批准即订 / 撤销即退,免重启)。
    plugins_root = Path(plugins_dir) if plugins_dir else (
        Path(__file__).resolve().parents[1] / "plugins"
    )
    plugins = PluginManager(plugins_root, settings=settings, skills=skills, hooks=hooks, mcp=mcp)
    for plugin_name in plugins.loadable_names():
        if plugins.find(plugin_name) is not None:
            plugins.apply(plugin_name)

    scheduler = Scheduler(max_concurrent=int(settings.get("agent.subagents.max_concurrent")))
    checkpoints = CheckpointStore(data_dir / "checkpoints")
    # 启动恢复准备(§9.17,phase-69):有 resume 快照的 alive checkpoint 转 PAUSED 待恢复;
    # 无快照的 legacy 仍标 failed。空目录 no-op;实例重建走 resume_run capability,不在启动时做
    prepare_resumable_checkpoints(checkpoints)
    # 启动清理超期情节(phase-44,§9.11):retention>0 时按保留天数清;
    # 0 = 交 agent 管理,启动不自动清(与 get_memory 惰性 purge 同语义)
    retention = int(settings.get("agent.memory.retention_days") or 0)
    if retention > 0:
        memory.purge(retention)
    builder = ContextBuilder(
        # 全局规则(§9.14):原文冻结,见 context/rules.py
        rules=list(GLOBAL_RULES),
        memory=memory,
        digests=digests,
        pages=pages,
        skills=skills,  # skill 索引常驻 system(§9.20)
    )

    def _build_system(task, persona_key: str) -> str:
        persona = resolve_persona(persona_key) if persona_key else None
        # 准则与风格一样每回合现读(phase-29,§9.14):改设置页下一回合即生效
        conduct = str(settings.get("agent.conduct") or "")
        raw = settings.get("agent.guidelines") or {}
        # raw 必须当 dict;人格 key 经 canonical_persona_key(别名 lucien→orchestrator),
        # 未知/自建 persona 没有对应键就没有【人格准则】层
        guideline = (
            str(raw.get(canonical_persona_key(persona_key), "") or "")
            if isinstance(raw, dict)
            else ""
        )
        return builder.system(
            persona=persona,
            task=task,
            style=settings.get("agent.style"),
            conduct=conduct,
            guideline=guideline,
        )

    spawner = Spawner(
        llm=chat_llm,
        toolbelt=toolbelt,
        scheduler=scheduler,
        events=events,
        checkpoints=checkpoints,
        build_system=_build_system,
        pages=pages,  # 对话实例按当前页面预激活工具(phase-06)
        sync_digest=digests.upsert,  # 步骤时刷新 DigestStore(phase-20)
    )
    budget = ProactiveBudget(
        per_session=int(settings.get("agent.proactive.per_session")),
        per_day=int(settings.get("agent.proactive.per_day")),
        follow_up_max=int(settings.get("agent.proactive.follow_up_max")),
        quiet_start=int(settings.get("agent.proactive.quiet_start")),
        quiet_end=int(settings.get("agent.proactive.quiet_end")),
    )
    proactive = ProactiveEngine(
        bus=bus, llm=chat_llm, memory=memory, scheduler=scheduler, budget=budget, settings=settings,
        meter=meter,  # 配额预检用同一份计量(§9.9 phase-65)
    )
    subagent_registry = SubagentRegistry(data_dir / "subagents")
    master = Master(
        llm=chat_llm,
        bus=bus,
        spawner=spawner,
        arbiter=Arbiter(chat_llm),
        digests=digests,
        settings=settings,
        proactive=proactive,
        hooks=hooks,
        memory=memory,
        subagents=subagent_registry,
        policy=policy,  # 自建 subagent 网络收窄时拷贝用(§9.9)
    )
    _master["master"] = master
    observer = Observer(master.consider)
    registry = build_agent_registry(
        CapabilityDeps(
            settings=settings,
            memory=memory,
            skills=skills,
            spawner=spawner,
            subagents=subagent_registry,
            pages=pages,
            asker=asker,
            toolbelt=toolbelt,
            mcp=mcp,
            meter=meter,  # 与 Toolbelt / metered_llm 同一实例(§9.9 配额查询读同一份计量)
            checkpoints=checkpoints,  # 可恢复 checkpoint 列表(phase-69,§9.17)
            plugins=plugins,  # 插件发现与批准(phase-72,§9.13)
        )
    )
    handlers, relay, hook_patterns = bind_event_loop(master, proactive, observer, hooks)
    loop = EventLoop(
        bus,
        handlers,
        cursors=cursors,
        relay=relay,
        extra_patterns=hook_patterns,
    )
    # 运行期订阅同步(phase-75):启动装载阶段 pattern 已随 extra_patterns 到位,
    # 注入后每次批准/撤销都由 PluginManager 推最新 event_patterns 给 loop
    plugins.set_subscription_sync(loop.sync_extra_patterns)
    return AgentApp(
        bus=bus,
        log=log,
        settings=settings,
        memory=memory,
        master=master,
        observer=observer,
        proactive=proactive,
        loop=loop,
        skills=skills,
        hooks=hooks,
        pages=pages,
        asker=asker,
        spawner=spawner,
        registry=registry,
        mcp=mcp,
        meter=meter,
        plugins=plugins,
        owns_settings=owns_settings,
        owns_log=owns_log,
    )


async def _serve() -> None:
    app = build_agent()
    print("agent runtime 已启动(事件循环常驻;Ctrl+C 退出)")
    await app.loop.run()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
