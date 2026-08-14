"""LLM 直连客户端(修订自旧 llm/provider.py):去掉 litellm 依赖,httpx 直连。

只支持两种 API 格式(§8.8):`chat`(OpenAI 兼容)与 `anthropic`(Messages)。
用量在 complete 成功后由调用方写入 store(计量直写,不再是日志解析)。
tools 入参为统一中性格式 [{"name","description","schema"}](与 agent ToolSpec
对齐);tool_calls 返回统一为 [{"id","name","arguments":dict}],双格式各自转换。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


@dataclass(frozen=True)
class CompleteResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class TestResult:
    ok: bool
    latency_ms: float = 0.0
    model: str = ""
    error: str = ""


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    rest = [m for m in messages if m.get("role") != "system"]
    return system, rest


def _chat_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("schema") or {"type": "object"},
            },
        }
        for t in tools
    ]


def _anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("schema") or {"type": "object"},
        }
        for t in tools
    ]


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> tuple[dict[str, Any], ...]:
    """chat 格式:arguments 是 JSON 字符串,解析失败降级为空参数。"""
    calls = []
    for tc in raw or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments") or "{}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        calls.append({
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "arguments": args if isinstance(args, dict) else {},
        })
    return tuple(calls)


async def complete(
    provider: dict[str, Any],
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    temperature: float = 0.7,
    tools: list[dict[str, Any]] | None = None,
) -> CompleteResult:
    fmt = provider["api_format"]
    base = provider["base_url"].rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if fmt == "anthropic":
            system, rest = _split_system(messages)
            body: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [
                    {"role": m["role"], "content": str(m.get("content", ""))}
                    for m in rest
                ],
            }
            if tools:
                body["tools"] = _anthropic_tools(tools)
            resp = await client.post(
                f"{base}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage") or {}
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            tool_calls = tuple(
                {
                    "id": b.get("id", ""),
                    "name": b.get("name", ""),
                    "arguments": b.get("input") or {},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            )
            return CompleteResult(
                text=text,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                model=data.get("model", model),
                tool_calls=tool_calls,
            )
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = _chat_tools(tools)
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return CompleteResult(
            text=str(message.get("content") or ""),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=data.get("model", model),
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
        )


async def test_connection(
    provider: dict[str, Any], *, api_key: str, model: str
) -> TestResult:
    """连通性测试(修订自旧 test_connection):真实发一次最小请求,回延迟与错误。"""
    start = time.perf_counter()
    try:
        result = await complete(
            provider,
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
    except httpx.HTTPStatusError as exc:
        return TestResult(
            ok=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=model,
            error=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
    except Exception as exc:  # noqa: BLE001  # 连接错误作为结果返回,不抛出
        return TestResult(
            ok=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=model,
            error=f"{type(exc).__name__}: {exc}",
        )
    return TestResult(
        ok=bool(result.text or result.model),
        latency_ms=(time.perf_counter() - start) * 1000,
        model=result.model or model,
    )
