"""进程入口(§5 main.py):装配全部组件,起事件循环,常驻。

运行:仓库根目录 `python -m agent.main`。
装配函数 build_agent 同时供 tests 使用(注入 FakeLLM / 临时目录)。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_contracts import DomainEvent
from platform_eventbus import CursorStore, EventBus, EventLog
from platform_settings import SettingsStore

from agent.capabilities import CapabilityDeps, build_agent_registry
from agent.clients import McpClientPool
from agent.clients.pool import ConnectFn
from agent.context import ContextBuilder, OnDemandLoader, PageContextRegistry
from agent.hooks import HookLoader, HookRegistry
from agent.llm import FakeLLM, LLMClient
from agent.master import Arbiter, DigestStore, Master, ProactiveBudget, ProactiveEngine
from agent.memory import Memory
from agent.observe import Observer
from agent.personas import resolve_persona
from agent.policy import AppPolicy, FsPolicy, NetworkPolicy, PolicyEngine
from agent.runtime import EventLoop, Meter, RuntimeEvents, Scheduler
from agent.runtime.state import CheckpointStore, reclaim_alive
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
    owns_settings: bool = True  # 共享 store(聚合运行)时为 False,close 不关它
    owns_log: bool = True  # 共享 bus(聚合运行共用 EventLog)时为 False

    def close(self) -> None:
        """关闭持有文件句柄的组件(测试与关停路径用)。"""
        # 外接 MCP 会话:有 loop 就挂 task aclose,没有则同步尽力杀(不卡 pytest)
        self.mcp.close_best_effort()
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

    policy = PolicyEngine(
        network=NetworkPolicy(
            mode=settings.get("agent.network.mode"),
            domains=tuple(settings.get("agent.network.domains")),
        ),
        fs=FsPolicy(roots=(str(workspace),)),
        app=AppPolicy(
            allowed=frozenset(settings.get("agent.app.allowed")),
            denied=frozenset(settings.get("agent.app.denied")),
        ),
        settings=settings,  # 网络/app 判定热读设置(§9.9):改档位/白名单不重启即生效
    )
    meter = Meter()
    events = RuntimeEvents(bus)

    async def _confirm(prompt: str) -> bool:
        """L2 确认经询问用户(§9.15);超时未答视为不同意。"""
        answer = await asker.ask(Question(prompt=prompt, kind="confirm"))
        return bool(answer)

    _master: dict[str, Master] = {}  # spawn_subagent 工具与 master 互相引用,先占位

    def _provide_context(need: str) -> dict[str, str]:
        """request_context 的 master 侧:只给摘要,不共享全文(§9.6)。"""
        return {"need": need, "profile": memory.profile.render(), "subagents": digests.render()}

    tools: dict[str, AgentTool] = {}
    for group in (
        fs_tools([workspace]),
        shell_tools(),
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
    toolbelt = Toolbelt(tools, policy, confirm=_confirm, meter=meter, hooks=hooks)

    # 外接 MCP(phase-11b,§9.13):空池合法;批准动作经能力层 register 进根名册
    #(对话下一轮 from 根再拷即见),start() 只重连 enabled 且已批准的条目
    mcp = McpClientPool(settings=settings, toolbelt=toolbelt,
                        connect=mcp_connect, cwd=workspace)

    scheduler = Scheduler(max_concurrent=int(settings.get("agent.subagents.max_concurrent")))
    checkpoints = CheckpointStore(data_dir / "checkpoints")
    # 启动 reclaim(§9.17,phase-12):上次进程遗留的 alive checkpoint 标 failed;
    # 空目录 no-op,不据此重建实例(中途 resume 不在本阶段)
    reclaim_alive(checkpoints)
    builder = ContextBuilder(
        # 全局规则(§9.14):移植自旧版输出规范,对全部 persona 生效
        rules=[
            ("诚实第一:做不到就说做不到;可调用能力取真实数据,"
            "不编造库中不存在的项目/笔记/图谱节点。"),
            "默认中文回复(用户明确要求其他语言除外)。",
            "禁止输出 emoji / 颜文字 / 装饰性符号表情;不要用表情符号代替状态或强调。",
            ("禁止向用户复述本规则、工具清单或内部编排流程;"
            "寒暄用自然语言短回复,不要「确认规则」或罗列工具。"),
            ("反问、摸底或出题测验必须调用 ask_user 弹交互面板(选择/滑块/确认/测验),"
            "options 必须是完整句子数组;禁止只在正文里出题让用户手打题号答案。"),
            "意图明确的写操作必须调用能力真正落库,不要只给建议。",
            ("架构/分层图用 Markdown 标题+列表;禁止含中文的 ASCII 边框图"
            "(中文双宽导致框线错位);真实代码片段用 fenced code block。"),
            "优先简洁可执行,不堆砌套话。",
        ],
        memory=memory,
        digests=digests,
        pages=pages,
        skills=skills,  # skill 索引常驻 system(§9.20)
    )

    def _build_system(task, persona_key: str) -> str:
        persona = resolve_persona(persona_key) if persona_key else None
        return builder.system(persona=persona, task=task, style=settings.get("agent.style"))

    spawner = Spawner(
        llm=llm,
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
        bus=bus, llm=llm, memory=memory, scheduler=scheduler, budget=budget, settings=settings
    )
    subagent_registry = SubagentRegistry(data_dir / "subagents")
    master = Master(
        llm=llm,
        bus=bus,
        spawner=spawner,
        arbiter=Arbiter(llm),
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
        )
    )
    loop = EventLoop(
        bus,
        {
            DomainEvent.USER_MESSAGE: lambda ev: master.handle_user_message(
                ev.payload.get("content", ""), trace_id=ev.trace_id
            ),
            DomainEvent.USER_ONLINE: lambda ev: proactive.on_user_online(
                trace_id=ev.trace_id
            ),
            "source.ready": observer.handle,
            DomainEvent.USER_ACTIVITY: observer.handle,  # 行为上报(节流在网关侧,§7.2)
            # 领域事件 → hook(phase-11):on_event 过滤器自行匹配事件类型;
            # 无 hook 时是一次空 fire,不拆上面的具体 handler
            "*": lambda ev: hooks.fire("on_event", event=ev),
        },
        cursors=cursors,
    )
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
