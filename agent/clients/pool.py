"""MCP client 连接池(§9.13):用户在设置页添加并批准的外接 MCP server。

单体形态下领域工具经 deploy/bridge.py 的 capability 桥已进工具面,
**禁止**再用 MCP client 把 services/*/mcp_server 灌一遍;本池只装用户
在设置页添加、批准后的 stdio/URL MCP server(phase-11b)。空池是合法稳态。

职责边界:校验/连接在此;挂载逻辑在 mount.py。配置持久化走 agent.mcp.servers
设置项,写入由 capabilities/mcp.py 的能力传入 actor(落审计)经本池落库。
测试注入 connect=... 用 Fake session,不进程不网;生产用 session.default_connect。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from platform_contracts import ErrorSuffix, ServiceError

from agent.clients.mount import remount, unmount
from agent.clients.session import McpSession, default_connect
from agent.tools.base import Toolbelt

#: 设置项 key:外接 MCP 配置列表
MCP_KEY = "agent.mcp.servers"

#: 单条配置 id 的合法形状(稳定主键,进工具名 mcp__<id>__<tool>)
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

CONNECT_TIMEOUT = 15.0  # 连接握手 + tools/list 上限(秒)

ConnectFn = Callable[[dict], Awaitable[McpSession]]


def validate_server_config(raw: dict) -> dict:
    """校验并规范化一条外接 MCP 配置;失败抛 AGENT.INVALID_INPUT,不静默丢。"""
    if not isinstance(raw, dict):
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "MCP 配置须为对象")
    sid = str(raw.get("id") or "").strip()
    if not _ID_RE.match(sid):
        raise ServiceError(
            "agent", ErrorSuffix.INVALID_INPUT,
            f"id 须为小写字母开头、1–32 位小写字母/数字/连字符: {sid!r}",
        )
    name = str(raw.get("name") or "").strip() or sid
    kind = raw.get("kind")
    approval = raw.get("approval") or "item"
    if kind not in ("stdio", "url"):
        raise ServiceError(
            "agent", ErrorSuffix.INVALID_INPUT, f"kind 须为 stdio 或 url: {kind!r}"
        )
    if approval not in ("package", "item"):
        raise ServiceError(
            "agent", ErrorSuffix.INVALID_INPUT, f"approval 须为 package 或 item: {approval!r}"
        )
    args = [str(a) for a in (raw.get("args") or [])]
    command = str(raw.get("command") or "").strip()
    url = str(raw.get("url") or "").strip()
    if kind == "stdio":
        if not command:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "stdio 类型 command 不能为空")
        url = ""
    else:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                f"url 须以 http:// 或 https:// 开头(禁止 file:): {url!r}",
            )
        command, args = "", []
    return {
        "id": sid,
        "name": name,
        "kind": kind,
        "command": command,
        "args": args,
        "url": url,
        "approval": approval,
        "enabled": bool(raw.get("enabled", True)),
    }


class McpClientPool:
    """外接 MCP server 连接池:connect(可注入)→ preview → 批准 → 挂根 Toolbelt。"""

    def __init__(
        self,
        *,
        settings: Any = None,  # SettingsStore:读/写 agent.mcp.servers
        toolbelt: Toolbelt | None = None,  # 根名册:批准后 register 进去
        connect: ConnectFn | None = None,  # 测试注入口;缺省走 session.default_connect
        cwd: str | Path | None = None,  # stdio 子进程工作目录(= agent 工作目录)
    ) -> None:
        self._settings = settings
        self._toolbelt = toolbelt
        self._connect = connect or default_connect
        self._cwd = str(cwd) if cwd else None
        self._sessions: dict[str, McpSession] = {}
        self._previews: dict[str, list[dict]] = {}  # 每台 server 最近一次 tools/list
        self._errors: dict[str, str] = {}  # 最近一次启动重连失败的条目级错误
        self._started = False

    # ---- 配置(agent.mcp.servers;写经 actor 落审计) ----

    def configs(self) -> list[dict]:
        if self._settings is None:
            return []
        return [dict(c) for c in (self._settings.get(MCP_KEY) or [])]

    def find_config(self, sid: str) -> dict | None:
        return next((c for c in self.configs() if c.get("id") == sid), None)

    async def _save_configs(self, configs: list[dict], actor: Any) -> None:
        if self._settings is None:
            raise ServiceError("agent", ErrorSuffix.INTERNAL, "MCP 池未绑定设置存储")
        await self._settings.set(MCP_KEY, configs, actor)

    async def upsert_config(self, cfg: dict, actor: Any) -> None:
        """整条替换(按 id);不动其他条目。"""
        configs = [c for c in self.configs() if c.get("id") != cfg["id"]]
        configs.append(cfg)
        await self._save_configs(configs, actor)

    async def delete_config(self, sid: str, actor: Any) -> None:
        await self._save_configs([c for c in self.configs() if c.get("id") != sid], actor)

    # ---- 连接与预览 ----

    async def preview(self, sid: str) -> list[dict]:
        """连接(如未连)并 tools/list,返回远端工具清单。

        连接前先 validate_server_config:脏配置(直写 settings 绕过 add 校验的
        残留)记条目 error 并拒绝,不进 connect(phase-13)。其余失败抛
        AGENT.UNAVAILABLE(消息可读),错误同时记在条目状态里;
        配置不受影响,用户修好环境后可再次预览。
        """
        cfg = self.find_config(sid)
        if cfg is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"没有这台外接 MCP: {sid}")
        try:
            validate_server_config(cfg)
        except ServiceError as exc:
            self._errors[sid] = str(exc)
            raise
        try:
            if sid not in self._sessions:
                self._sessions[sid] = await asyncio.wait_for(
                    self._connect({**cfg, "cwd": self._cwd}), CONNECT_TIMEOUT
                )
            tools = await asyncio.wait_for(
                self._sessions[sid].list_remote_tools(), CONNECT_TIMEOUT
            )
        except Exception as exc:  # 含超时:统一转可读错误,不把异常打出能力框架
            await self.drop_session(sid)
            message = f"MCP「{cfg['name']}」连接或列工具失败: {exc}"
            self._errors[sid] = message
            raise ServiceError("agent", ErrorSuffix.UNAVAILABLE, message) from exc
        self._previews[sid] = tools
        self._errors.pop(sid, None)
        # 已批准过:列工具成功就重挂(启动失败修好后点「刷新」也能回到工具面)
        approved = list(cfg.get("approved") or [])
        if approved:
            self.remount(sid, approved)
        return tools

    async def drop_session(self, sid: str) -> None:
        """断开并清掉一台 server 的会话;未连接时是空操作。"""
        session = self._sessions.pop(sid, None)
        if session is not None:
            try:
                await session.aclose()
            except Exception:
                pass

    # ---- 挂载(进 Toolbelt 工具面;实现在 mount.py) ----

    def remount(self, sid: str, approved: list[str]) -> list[str]:
        """按 approved 挂载(["*"] = 全部 preview);先卸旧挂,避免残名。

        需要 preview 在场(先 preview());返回本次挂上的工具名。
        """
        session = self._sessions.get(sid)
        remote_tools = self._previews.get(sid) or []
        cfg = self.find_config(sid) or {"id": sid, "name": sid}
        return remount(self._toolbelt, cfg, session, remote_tools, approved)

    def unmount(self, sid: str) -> list[str]:
        """从根名册卸掉 mcp__<sid>__*;返回实际卸载的名字。"""
        return unmount(self._toolbelt, sid)

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动重连(deploy lifespan 调):enabled 且已批准的条目 connect + 挂载。

        幂等(重复调用是空操作);单台失败记录到条目 error,不挡启动与其他 server;
        缺 id 的脏条目(直写 settings 的残留)直接跳过,同样不挡其他 server。
        """
        if self._started:
            return
        self._started = True
        for cfg in self.configs():
            if not cfg.get("enabled", True) or not cfg.get("approved"):
                continue
            sid = str(cfg.get("id") or "").strip()
            if not sid:
                continue
            try:
                # preview 成功后若已批准会自行 remount
                await self.preview(sid)
            except Exception as exc:
                self._errors[sid] = str(exc)

    def list_state(self) -> list[dict]:
        """设置页数据源:配置 + 运行态(connected / error / preview / mounted)。

        缺 id 的脏条目直接跳过,不让整表 KeyError 炸掉设置页列表接口。
        """
        mounted_all = self._toolbelt.names() if self._toolbelt else []
        return [
            {
                **cfg,
                "connected": sid in self._sessions,
                "error": self._errors.get(sid, ""),
                "preview": self._previews.get(sid, []),
                "mounted": [
                    n for n in mounted_all if n.startswith(f"mcp__{sid}__")
                ],
            }
            for cfg in self.configs()
            if (sid := str(cfg.get("id") or "").strip())
        ]

    async def aclose_sessions(self, sessions: list[McpSession] | None = None) -> None:
        targets = list(self._sessions.values()) if sessions is None else sessions
        for session in targets:
            try:
                await session.aclose()
            except Exception:
                pass
        if sessions is None:
            self._sessions.clear()

    def close_best_effort(self) -> None:
        """AgentApp.close 的 sync 收尾:有运行中的 loop 就挂 task;没有则同步尽力杀。"""
        sessions = list(self._sessions.values())
        self._sessions.clear()
        if not sessions:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            for session in sessions:
                closer = getattr(session, "close_sync", None)
                if closer is not None:
                    try:
                        closer()
                    except Exception:
                        pass
        else:
            loop.create_task(self.aclose_sessions(sessions))
