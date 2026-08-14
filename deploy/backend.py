"""聚合装配根(§13.1 单体形态):全部服务 + agent runtime + gateway 单进程单端口。

各服务独立运行入口不变(uvicorn services.<x>.rest:app_factory);本模块是
部署形态之一,接口与协议与多进程形态完全一致(挂载换成 HTTP 反代即可)。
生命周期统一:gateway lifespan 内 start 全部 worker/scheduler 与 agent 事件循环,
关停逆序 stop/close;共享设施(EventLog/SecretStore/SettingsStore)由本根持有。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from platform_capability import Wiring, execute
from platform_eventbus import EventBus, EventLog
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from agent.main import AgentApp, build_agent

from .bridge import AGENT_MAIN, make_domain_tools
from .llm_adapter import ServiceLLM

ROOT = Path(__file__).parent.parent


@dataclass
class Backend:
    """装配产物句柄(测试与调试入口用)。"""

    app: FastAPI
    agent: AgentApp
    wirings: dict[str, Wiring]
    bus: EventBus
    log: EventLog
    secrets: SecretStore
    settings_store: SettingsStore


def build(
    data_dir: str | Path | None = None,
    workspace_dir: str | Path | None = None,
    *,
    llm: object | None = None,
    clone_fn=None,
) -> FastAPI:
    """装配整个后端;uvicorn deploy.backend:build --factory。

    llm:测试注入口(agent.llm.LLMClient 协议);省略时走 llm 服务能力(ServiceLLM)。
    clone_fn:sources 克隆函数测试注入口;省略时真 git clone(不 mock 骗用户)。
    """
    from services.gateway.mounts import MountSpec
    from services.gateway.rest import create_app as gateway_create
    from services.graph.wiring import wire as wire_graph
    from services.llm.wiring import wire as wire_llm
    from services.notes.wiring import wire as wire_notes
    from services.settings.wiring import wire as wire_settings
    from services.sources.wiring import wire as wire_sources

    data_root = Path(data_dir) if data_dir else ROOT / "runtime-data"
    workspace = Path(workspace_dir) if workspace_dir else ROOT / "workspace"
    data_root.mkdir(parents=True, exist_ok=True)

    # 共享基础设施:一条事件时间线、一个加密仓、一个设置存储
    log = EventLog(data_root / "events.db")
    bus = EventBus(log)
    secrets = SecretStore(data_root / "secrets.db")
    settings_store = SettingsStore(data_root / "settings.db", bus)

    wirings: dict[str, Wiring] = {
        "settings": wire_settings(data_root / "settings", bus=bus, store=settings_store),
        "llm": wire_llm(data_root / "llm", secrets=secrets),
        "sources": wire_sources(data_root / "sources", workspace=workspace,
                                bus=bus, secrets=secrets, clone_fn=clone_fn),
        "notes": wire_notes(data_root / "notes", bus=bus),
        "graph": wire_graph(data_root / "graph", bus=bus),
    }
    mounts = [MountSpec(domain=name, registry=w.registry, probe=w.probe)
              for name, w in wirings.items()]

    # agent runtime:LLM 走 llm 服务能力,领域能力经桥注入,设置/事件与全系统共享
    async def _call(domain: str, name: str, args: dict) -> dict:
        return await execute(wirings[domain].registry, name, AGENT_MAIN, args)

    agent = build_agent(
        data_dir=data_root / "agent", workspace_dir=workspace,
        llm=llm if llm is not None else ServiceLLM(_call),
        bus=bus, settings_store=settings_store,
        extra_tools=make_domain_tools(mounts),
    )
    mounts.append(MountSpec(domain="agent", registry=agent.registry,
                            probe=lambda: {"status": "up"}))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        for w in wirings.values():
            if w.start:
                await w.start()
        agent_task = asyncio.create_task(agent.loop.run())
        try:
            yield
        finally:
            agent.loop.stop()
            agent_task.cancel()
            with suppress(asyncio.CancelledError):
                await agent_task
            for w in reversed(list(wirings.values())):
                if w.stop:
                    await w.stop()
            for w in reversed(list(wirings.values())):
                if w.close:
                    w.close()
            agent.close()  # 共享 store/log 由本根关闭(owns_* 均为 False)
            secrets.close()
            settings_store.close()
            log.close()

    app = gateway_create(mounts, bus=bus, lifespan=lifespan)
    app.state.backend = Backend(
        app=app, agent=agent, wirings=wirings, bus=bus, log=log,
        secrets=secrets, settings_store=settings_store,
    )
    return app
