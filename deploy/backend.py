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
from platform_actor import LocalTokenIssuer
from platform_capability import CostQuota, SqliteAuditSink, Wiring, execute
from platform_contracts import ErrorSuffix, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from agent.main import AgentApp, build_agent
from agent.settings import DEFS as AGENT_SETTING_DEFS

from .bridge import agent_context, make_domain_tools
from .llm_adapter import ServiceLLM

ROOT = Path(__file__).parent.parent


def _resolve_workspace(
    workspace_dir: str | Path | None, settings_store: SettingsStore
) -> Path:
    """工作目录解析(§9.10):显式入参(测试注入口)优先;否则读 agent.workspace.dir,
    相对路径以仓库根为基准,空/缺省回落 ROOT/workspace。settings 库中的值禁止
    含 `..` 段(防越出仓库根);改目录后需重启才换 jail(fs 工具与资源库启动装配)。"""
    if workspace_dir is not None:
        return Path(workspace_dir)
    raw = str(settings_store.get("agent.workspace.dir") or "").strip()
    if not raw:
        return ROOT / "workspace"
    if ".." in Path(raw).parts:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"agent.workspace.dir 禁止包含 .. 段: {raw}",
        )
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


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
    parse_fn=None,
) -> FastAPI:
    """装配整个后端;uvicorn deploy.backend:build --factory。

    llm:测试注入口(agent.llm.LLMClient 协议);省略时走 llm 服务能力(ServiceLLM)。
    clone_fn:sources 克隆函数测试注入口;省略时真 git clone(不 mock 骗用户)。
    parse_fn:sources 文档解析函数测试注入口;省略时真实提取(pypdfium2/docx)。
    """
    from services.gateway.mounts import MountSpec
    from services.gateway.rest import create_app as gateway_create
    from services.gateway.settings import DEFS as GATEWAY_SETTING_DEFS
    from services.gateway.uploads import build_upload_router
    from services.graph.wiring import wire as wire_graph
    from services.llm.wiring import wire as wire_llm
    from services.notes.wiring import wire as wire_notes
    from services.settings.wiring import wire as wire_settings
    from services.sources.files import build_files_router
    from services.sources.wiring import wire as wire_sources

    data_root = Path(data_dir) if data_dir else ROOT / "runtime-data"
    data_root.mkdir(parents=True, exist_ok=True)

    # 共享基础设施:一条事件时间线、一个加密仓、一个设置存储、一个审计库
    log = EventLog(data_root / "events.db")
    bus = EventBus(log)
    secrets = SecretStore(data_root / "secrets.db")
    settings_store = SettingsStore(data_root / "settings.db", bus)
    audit = [SqliteAuditSink(data_root / "audit.db")]
    issuer = LocalTokenIssuer(data_root / "machine.token")
    # 本机工作台配额取宽松日预算:拦住失控循环,不挡正常对话/索引
    quota = [CostQuota(default_daily_budget=50_000)]
    # gateway 自身设置项由部署入口注册(其模块注释约定,无 wiring 装配)
    settings_store.register_fresh(GATEWAY_SETTING_DEFS)
    # agent 设置项也要先注册:工作目录解析要读 agent.workspace.dir(§9.10)
    settings_store.register_fresh(AGENT_SETTING_DEFS)
    workspace = _resolve_workspace(workspace_dir, settings_store)

    # graph L0 资源目录桥:按 kinds 从 sources 各店 fan-out 资源摘要
    # (形状= list_sources summaries;依赖倒置,graph 不 import sources)。
    # STORES 由下方 wire_sources→init_all 填充,闭包惰性读取故先定义无碍。
    from services.sources.capabilities import STORES as SOURCES_STORES

    def _graph_resource_provider(kinds: list[str]) -> list[dict]:
        out: list[dict] = []
        for k in kinds:
            store = SOURCES_STORES.get(k)
            if store is not None:
                out.extend(store.summaries(limit=2000))
        return out

    wirings: dict[str, Wiring] = {
        "settings": wire_settings(data_root / "settings", bus=bus, store=settings_store),
        "llm": wire_llm(data_root / "llm", secrets=secrets,
                        settings_store=settings_store),
        "sources": wire_sources(data_root / "sources", workspace=workspace,
                                bus=bus, secrets=secrets, clone_fn=clone_fn,
                                parse_fn=parse_fn,
                                settings_store=settings_store),
        "notes": wire_notes(data_root / "notes", bus=bus,
                            settings_store=settings_store, workspace=workspace),
        "graph": wire_graph(data_root / "graph", bus=bus,
                            settings_store=settings_store,
                            resource_provider=_graph_resource_provider,
                            workspace=workspace),
    }
    # sources 自带文档文件只读路由(wire→init_all 已填充其 STORES)
    # notes 自带附件只读路由(/api/notes/assets/{id};wire 后可用)
    from services.notes.assets import build_assets_router as build_notes_assets_router
    mounts = [MountSpec(domain=name, registry=w.registry, probe=w.probe,
                        extra_router=(
                            build_files_router(SOURCES_STORES["doc"])
                            if name == "sources"
                            else build_notes_assets_router() if name == "notes"
                            else None))
              for name, w in wirings.items()]
    extra_routers = [build_upload_router(workspace)]

    # agent runtime:LLM 走 llm 服务能力,领域能力经桥注入,设置/事件与全系统共享
    async def _call(domain: str, name: str, args: dict) -> dict:
        return await execute(wirings[domain].registry, name, agent_context(), args,
                             audit=audit, quota=quota)

    agent = build_agent(
        data_dir=data_root / "agent", workspace_dir=workspace,
        llm=llm if llm is not None else ServiceLLM(_call),
        bus=bus, settings_store=settings_store,
        extra_tools=make_domain_tools(mounts, audit=audit, quota=quota),
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
            for sink in audit:
                sink.close()
            log.close()

    app = gateway_create(mounts, bus=bus, lifespan=lifespan, issuer=issuer,
                         quota=quota, audit=audit, extra_routers=extra_routers)
    app.state.backend = Backend(
        app=app, agent=agent, wirings=wirings, bus=bus, log=log,
        secrets=secrets, settings_store=settings_store,
    )
    return app
