"""MCP 会话最小实现(§9.13):stdio 子进程与 HTTP URL 两条产品路径。

协议最小集(JSON-RPC 2.0):initialize → notifications/initialized →
tools/list / tools/call。根 pyproject 不硬依赖 mcp SDK,本模块自研路径
即可工作;测试经 pool 的 connect 注入 Fake,不走这里。

帧格式:MCP stdio 规范(2024-11-05 起)按**换行**分帧,每行一条 JSON-RPC
消息——不是 LSP 的 Content-Length。非 JSON 行(部分 server 的日志)忽略。
"""

from __future__ import annotations

import asyncio
import itertools
import json
from contextlib import suppress
from typing import Any, Protocol, runtime_checkable

import httpx

#: initialize 握手用的协议版本(长期兼容线)
PROTOCOL_VERSION = "2024-11-05"

CALL_TIMEOUT = 30.0  # HTTP 客户端单请求上限(秒);stdio 调用超时在池侧包 wait_for


@runtime_checkable
class McpSession(Protocol):
    """一台外接 MCP server 的会话;生产实现见本文件,测试注入 Fake。"""

    async def list_remote_tools(self) -> list[dict]:
        """远端工具清单;每条至少 {name, description, schema?}。"""
        ...

    async def call_tool(self, name: str, arguments: dict) -> str:
        """调用远端工具,返回拼接后的文本结果。"""
        ...

    async def aclose(self) -> None:
        """断开(杀子进程 / 关 HTTP 客户端),可重复调用。"""
        ...


class _McpProtocol:
    """JSON-RPC 2.0 之上的 MCP 最小协议;传输由子类实现 connect/_request/_notify。"""

    _ids = itertools.count(1)

    async def connect(self) -> None:
        raise NotImplementedError

    async def _request(self, method: str, params: dict | None) -> Any:
        raise NotImplementedError

    async def _notify(self, method: str, params: dict | None) -> None:
        raise NotImplementedError

    async def initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "voyager-agent", "version": "1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def list_remote_tools(self) -> list[dict]:
        result = await self._request("tools/list", {})
        tools = result.get("tools") or [] if isinstance(result, dict) else []
        return [
            {
                "name": str(t.get("name") or ""),
                "description": str(t.get("description") or ""),
                "schema": t.get("inputSchema") or {},
            }
            for t in tools
            if isinstance(t, dict) and t.get("name")
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        # content 是 [{type:"text",text:...},...];拼接文本,空则原样回 JSON
        parts = [
            str(c.get("text") or "")
            for c in (result.get("content") or [])
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        text = "\n".join(p for p in parts if p)
        return text or json.dumps(result, ensure_ascii=False)


class StdioMcpSession(_McpProtocol):
    """stdio 子进程会话。command+args 直接 exec(shell=False,禁 shell=True)。"""

    def __init__(self, command: str, args: list[str], cwd: str | None = None) -> None:
        self._command = command
        self._args = list(args)
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None

    async def connect(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # 子进程日志不混进协议流
            cwd=self._cwd,
        )

    async def _send(self, payload: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("MCP 子进程未启动")
        proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await proc.stdin.drain()

    async def _read_result(self, want_id: int) -> Any:
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise RuntimeError("MCP 子进程未启动")
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP 子进程已退出(stdout EOF)")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # 非 JSON 行(server 日志)不进协议
            if not isinstance(msg, dict) or msg.get("id") != want_id:
                continue  # 通知 / server 主动请求(如 sampling)本阶段忽略
            if msg.get("error"):
                err = msg["error"] or {}
                raise RuntimeError(f"JSON-RPC {err.get('code')}: {err.get('message')}")
            return msg.get("result")

    async def _request(self, method: str, params: dict | None) -> Any:
        rid = next(self._ids)
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        return await self._read_result(rid)

    async def _notify(self, method: str, params: dict | None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def aclose(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        with suppress(Exception):
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except TimeoutError:
                proc.kill()

    def close_sync(self) -> None:
        """无事件循环时的尽力收尾(AgentApp.close 是 sync):直接杀,不等待。"""
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            with suppress(Exception):
                proc.terminate()


def _sse_result(text: str) -> Any:
    """解析 SSE 文本:逐事件取 data: 行拼 JSON,回第一条带 result/error 的消息。"""
    for block in text.split("\n\n"):
        data_lines = [ln[5:].strip() for ln in block.splitlines() if ln.startswith("data:")]
        if not data_lines:
            continue
        try:
            msg = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
            return msg
    raise RuntimeError("SSE 响应里没有 JSON-RPC result")


class UrlMcpSession(_McpProtocol):
    """HTTP 会话:每条 JSON-RPC 消息 POST 到配置的 URL(最简形态,无会话头)。

    响应兼容两种形态:application/json 直读;text/event-stream 解析 data: 行;
    通知(notes/initialized 等)按 202/空 body 处理。
    """

    def __init__(self, url: str, timeout: float = CALL_TIMEOUT) -> None:
        self._url = url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _post(self, payload: dict) -> Any:
        client = self._client
        if client is None:
            raise RuntimeError("MCP HTTP 会话未连接")
        resp = await client.post(
            self._url,
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        resp.raise_for_status()
        if resp.status_code == 202 or not resp.content.strip():
            return None
        if "text/event-stream" in resp.headers.get("content-type", ""):
            return _sse_result(resp.text)
        return resp.json()

    async def _request(self, method: str, params: dict | None) -> Any:
        rid = next(self._ids)
        msg = await self._post(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        )
        if not isinstance(msg, dict):
            raise RuntimeError(f"MCP server 对 {method} 未返回响应")
        if msg.get("error"):
            err = msg["error"] or {}
            raise RuntimeError(f"JSON-RPC {err.get('code')}: {err.get('message')}")
        return msg.get("result")

    async def _notify(self, method: str, params: dict | None) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with suppress(Exception):
                await client.aclose()


async def default_connect(cfg: dict) -> McpSession:
    """生产 connect:kind=stdio 起子进程(shell=False);kind=url 走 HTTP。

    完成 initialize 握手才返回;握手失败回收资源后原样抛出,由池转成可读错误。
    """
    if cfg.get("kind") == "stdio":
        session: _McpProtocol = StdioMcpSession(
            str(cfg["command"]), list(cfg.get("args") or []), cfg.get("cwd")
        )
    else:
        session = UrlMcpSession(str(cfg["url"]))
    try:
        await session.connect()
        await session.initialize()
    except Exception:
        with suppress(Exception):
            await session.aclose()
        raise
    return session  # type: ignore[return-value]
