"""agent 自己暴露的能力(§5 capabilities.py):经 gateway 与用户同权(铁律 4 parity)。

用户能在设置页做的,agent 也能做——除 secret(api key 等),由 settings 框架层拒绝。
handler 声明 `_actor` 参数时,框架注入调用者 ActorRef(见 platform_capability.guards)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from agent.clients.pool import validate_server_config
from agent.context.pages import PageContextRegistry
from agent.memory import Memory
from agent.skills.loader import SkillLoader
from agent.subagent.registry import SubagentRegistry
from agent.subagent.spawn import Spawner
from agent.tools.ask_user import AskUser


@dataclass
class CapabilityDeps:
    settings: Any  # SettingsStore
    memory: Memory
    skills: SkillLoader
    spawner: Spawner
    subagents: SubagentRegistry
    pages: PageContextRegistry
    asker: AskUser
    toolbelt: Any  # Toolbelt(list_tools 数据源,§9.4)
    mcp: Any  # McpClientPool(外接 MCP,phase-11b;配置写经 actor 落审计)


def build_agent_registry(deps: CapabilityDeps) -> Registry:
    reg = Registry("agent")

    @capability(reg, name="get_settings", description="列出全部设置项 schema(secret 只回 has_value)")
    def get_settings() -> list[dict]:
        return deps.settings.list_schema()

    @capability(reg, name="set_setting", description="修改一个设置项(secret 项会被框架拒绝)")
    async def set_setting(key: str, value, _actor: ActorRef = None) -> dict:
        await deps.settings.set(key, value, _actor)
        return {"key": key, "ok": True}

    @capability(reg, name="list_skills", description="skill 索引(常驻:name + 描述)")
    def list_skills() -> list[dict]:
        return deps.skills.index()

    @capability(reg, name="read_skill", description="按需读 skill 全文")
    def read_skill(name: str) -> dict:
        return {"name": name, "text": deps.skills.full_text(name)}

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
                {"id": i.id, "name": i.name, "status": i.status.value,
                 "goal": i.task.goal, "started_ts": i.state.started_ts}
                for i in deps.spawner.instances.values()
            ],
        }

    @capability(reg, name="cancel_run", description="急停运行中的 subagent(按 id 或 name;'chat'=对话主实例)",
                cost=1)
    async def cancel_run(id_or_name: str) -> dict:
        """用户与 agent 都可急停(修复 Parity:原来双方都缺 kill switch)。"""
        cancelled = await deps.spawner.cancel(id_or_name)
        if not cancelled:
            from platform_contracts import ErrorSuffix, ServiceError

            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND,
                f"没有匹配的运行中实例: {id_or_name}",
                hint="list_subagents 查看运行中实例",
            )
        return {"cancelled": cancelled}

    @capability(reg, name="list_personas", description="人格预设清单(团队页数据源)")
    def list_personas() -> list[dict]:
        from agent.personas import PERSONAS

        return [
            {"key": p.key, "id": p.key, "display_name": p.display_name, "style": p.style,
             "default_mode": p.default_mode,
             "tool_allow": list(p.tool_allow) if p.tool_allow else None,
             "system_prompt": p.system_prompt}
            for p in PERSONAS.values()
        ]

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

    @capability(reg, name="list_tools", description="当前工具面名册(自建 subagent 白名单候选项)")
    def list_tools() -> list[dict]:
        # 名册与 LLM 看到的 ToolSpec 一致(内部工具 + 领域桥 notes__* 等)
        return [{"name": s.name, "description": s.description}
                for s in deps.toolbelt.specs()]

    # ---- 外接 MCP(phase-11b,§9.13):设置页添加 → 预览 → 批准挂载 ----

    @capability(reg, name="list_mcp_servers",
                description="外接 MCP 配置与运行态(连接/错误/预览/已挂载)")
    def list_mcp_servers() -> list[dict]:
        return deps.mcp.list_state()

    @capability(reg, name="add_mcp_server",
                description="添加外接 MCP server(stdio 命令或 HTTP URL);先校验入库再试连预览",
                cost=1)
    async def add_mcp_server(id: str, kind: str, name: str = "", command: str = "",
                             args: list[str] | None = None, url: str = "",
                             approval: str = "item",
                             _actor: ActorRef = None) -> dict:
        cfg = validate_server_config({
            "id": id, "kind": kind, "name": name, "command": command,
            "args": args or [], "url": url, "approval": approval,
        })
        if deps.mcp.find_config(cfg["id"]) is not None:
            raise ServiceError("agent", ErrorSuffix.CONFLICT,
                               f"已存在同 id 的外接 MCP: {cfg['id']}")
        await deps.mcp.upsert_config({**cfg, "approved": []}, _actor)
        try:
            preview = await deps.mcp.preview(cfg["id"])
        except ServiceError as exc:
            # 连不上也保留配置:用户修好环境后可「刷新工具列表」重试,不吞半条配置
            return {"ok": True, "id": cfg["id"], "connected": False,
                    "error": str(exc), "preview": []}
        return {"ok": True, "id": cfg["id"], "connected": True, "error": "",
                "preview": preview}

    @capability(reg, name="preview_mcp_tools",
                description="对已配置的外接 MCP 再列一次工具(未批准也可预览)")
    async def preview_mcp_tools(id: str) -> dict:
        preview = await deps.mcp.preview(id)  # 失败抛 AGENT.UNAVAILABLE(可读消息)
        return {"id": id, "preview": preview}

    @capability(reg, name="approve_mcp_tools",
                description="批准外接 MCP 工具进对话工具面(整包 names=['*'] 或点名)",
                cost=1)
    async def approve_mcp_tools(id: str, names: list[str] | None = None,
                                _actor: ActorRef = None) -> dict:
        cfg = deps.mcp.find_config(id)
        if cfg is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND,
                               f"没有这台外接 MCP: {id}")
        prev = list(cfg.get("approved") or [])
        if names is None:
            if cfg.get("approval") != "package":
                raise ServiceError("agent", ErrorSuffix.INVALID_INPUT,
                                   "逐项批准需要给出 names;整包批准传 names=['*']")
            names = ["*"]
        if "*" in names or "*" in prev:
            approved = ["*"]  # 已整包批准过就保持整包,不悄悄收窄
        else:
            remote_names = {t.get("name") for t in await deps.mcp.preview(id)}
            unknown = [n for n in names if n not in remote_names]
            if unknown:
                raise ServiceError(
                    "agent", ErrorSuffix.INVALID_INPUT,
                    f"预览里没有这些工具: {', '.join(unknown)};"
                    "先「刷新工具列表」再批准",
                )
            # 逐项批准是累积(不撤销先前批准);撤销走移除整台 server
            approved = sorted(set(prev) | set(names))
        await deps.mcp.upsert_config({**cfg, "approved": approved}, _actor)
        mounted = deps.mcp.remount(id, approved)
        return {"ok": True, "id": id, "approved": approved, "mounted": mounted,
                "note": "已批准的工具进入工具名册;进行中的这轮对话看不到,"
                        "下一句或新对话可见。"}

    @capability(reg, name="remove_mcp_server",
                description="移除外接 MCP:断开、卸载其工具、删配置", cost=1)
    async def remove_mcp_server(id: str, _actor: ActorRef = None) -> dict:
        if deps.mcp.find_config(id) is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND,
                               f"没有这台外接 MCP: {id}")
        deps.mcp.unmount(id)
        await deps.mcp.drop_session(id)
        await deps.mcp.delete_config(id, _actor)
        return {"ok": True, "id": id}

    @capability(reg, name="recall_memory", description="检索 agent 记忆(画像/情节/语义)")
    def recall_memory(query: str, limit: int = 8) -> list[dict]:
        return deps.memory.recall(query, limit)

    @capability(reg, name="get_memory", description="记忆快照:画像摘要+键值、最近情节/语义、工作记忆条数")
    def get_memory() -> dict:
        """设置页数据源(§10.11):读 retention_days 并惰性清超期情节(与 notes 回收站同精神)。"""
        retention = int(deps.settings.get("agent.memory.retention_days") or 0)
        purged = deps.memory.purge(retention)["episodic"] if retention > 0 else 0
        episodic_recent = deps.memory.episodic.recent(limit=20)
        semantic_recent = deps.memory.semantic.query(limit=20)
        return {
            "profile": {
                "summary": deps.memory.profile.render(),
                "items": [
                    {"key": k, "value": v} for k, v in deps.memory.profile.all().items()
                ],
            },
            "episodic": {"recent": episodic_recent, "shown": len(episodic_recent)},
            "semantic": {"recent": semantic_recent, "shown": len(semantic_recent)},
            "working": {"size": len(deps.memory.working)},
            "retention_days": retention,
            "purged_episodic": purged,
        }

    @capability(reg, name="clear_memory", description="清空记忆区(zone: profile/episodic/semantic/working/all)",
                cost=2)
    def clear_memory(zone: str) -> dict:
        return {"zone": zone, "cleared": deps.memory.clear(zone)}

    @capability(reg, name="set_profile", description="写入/更新一条用户画像键值")
    def set_profile(key: str, value: str) -> dict:
        cleaned = (key or "").strip()
        if not cleaned:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "画像键不能为空")
        deps.memory.profile.set(cleaned, value)
        return {"key": cleaned, "ok": True}

    @capability(reg, name="delete_profile", description="删除一条用户画像键值(键不存在不报错)")
    def delete_profile(key: str) -> dict:
        cleaned = (key or "").strip()
        if not cleaned:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "画像键不能为空")
        deps.memory.profile.delete(cleaned)
        return {"key": cleaned, "ok": True}

    @capability(reg, name="report_page_context", description="页面上报:前端 provider 推送页面摘要(§10.12)")
    def report_page_context(
        page: str, summary: str, counts: dict | None = None, selected: str = ""
    ) -> dict:
        item = deps.pages.update(page, summary, counts=counts, selected=selected)
        return {"page": item.page, "ok": True}

    @capability(reg, name="answer_question", description="AskUser 答案回投(§9.15)")
    def answer_question(question_id: str, value) -> dict:
        return {"matched": deps.asker.answer(question_id, value)}

    return reg
