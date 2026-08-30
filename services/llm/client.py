"""LLM 直连客户端(修订自旧 llm/provider.py):去掉 litellm 依赖,httpx 直连。

只支持两种 API 格式(§8.8):`chat`(OpenAI 兼容)与 `anthropic`(Messages)。
用量在 complete 成功后由调用方写入 store(计量直写,不再是日志解析)。
tools 入参为统一中性格式 [{"name","description","schema"}](与 agent ToolSpec
对齐);tool_calls 返回统一为 [{"id","name","arguments":dict}],双格式各自转换。
messages 历史为 agent 中性协议:成对的 assistant.tool_calls / role:"tool"
按各家原生 tool 协议编码,孤儿工具结果降级为 user 文本(见 _resolve_tool_messages)。
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


def _resolve_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """成对历史保留中性 tool 协议;孤儿/残缺回合降级,避免端点 400。

    agent REACT 循环自 Phase 04 起成对回填:assistant 带 tool_calls(含 id),
    随后的 tool 结果带同一 tool_call_id(见 agent/subagent/modes.py _react),
    各家线格式由本 client 的编码器产出。严格端点要求「assistant 声明的每个
    id 都有结果,且结果出现在该 assistant 之后」。历史里仍可能残留:
    Phase 01–03 的旧会话、compressor 第二刀删掉部分消息、中断残环。
    孤儿原样发出会被 Anthropic 系端点(MiniMax 兼容层,错误码 2013
    "tool result's tool id not found")与 OpenAI 官方端点拒绝——这里翻成
    user 文本;assistant 上没有对应结果的 tool_calls 从发出去的副本里拿掉
    (不改调用方的 messages)。
    """
    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or ():
                tid = str((tc or {}).get("id") or "")
                if tid:
                    seen_ids.add(tid)
            out.append(m)
            continue
        if m.get("role") == "tool":
            tid = str(m.get("tool_call_id") or "")
            if tid and tid in seen_ids:
                out.append(m)
            else:
                name = str(m.get("name") or "tool")
                out.append({"role": "user", "content": f"[工具 {name} 结果]\n{m.get('content', '')}"})
            continue
        out.append(m)

    have_results = {
        str(m.get("tool_call_id") or "")
        for m in out
        if m.get("role") == "tool" and m.get("tool_call_id")
    }
    cleaned: list[dict[str, Any]] = []
    for m in out:
        calls = m.get("tool_calls") if m.get("role") == "assistant" else None
        if not calls:
            cleaned.append(m)
            continue
        kept = [tc for tc in calls if str((tc or {}).get("id") or "") in have_results]
        if len(kept) == len(calls):
            cleaned.append(m)
            continue
        if not kept and not str(m.get("content") or ""):
            continue
        nm = {**m, "tool_calls": kept}
        if not kept:
            nm = {k: v for k, v in nm.items() if k != "tool_calls"}
        cleaned.append(nm)
    return cleaned


def _chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """成对历史 → OpenAI 线格式:assistant.tool_calls 补 type/function 形状,
    arguments 序列化为 JSON 字符串。role:"tool" 与 tool_call_id 是 OpenAI
    原生字段,原样透传(孤儿已在 _resolve_tool_messages 阶段降级)。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        tool_calls = m.get("tool_calls") if m.get("role") == "assistant" else None
        if not tool_calls:
            out.append(m)
            continue
        out.append({
            **m,
            "tool_calls": [
                {
                    "id": str(tc.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(tc.get("name") or ""),
                        "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ],
        })
    return out


def _anthropic_messages(rest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """非 system 历史 → Anthropic 线格式(内容块,不再整体压成纯字符串)。

    - assistant:text 块(若有)+ tool_use 块(id/name/input);两者皆空则丢弃
      (Anthropic 拒绝空 content——MiniMax 2013 "messages must not be empty" 的
      另一来源)。
    - role:"tool":转为 user 消息内的 tool_result 块,tool_use_id 与发起的
      tool_use 同 id(注意是 Anthropic 字段名,不是 OpenAI 的 tool_call_id);
      连续多条合并进一条 user——Anthropic 惯例是同一 assistant 回合的多个
      结果放一条 user 的多个 tool_result 块。
    - 其余消息:字符串 content 原样。
    """
    out: list[dict[str, Any]] = []
    for m in rest:
        role = m.get("role")
        if role == "assistant":
            text = str(m.get("content") or "")
            blocks: list[dict[str, Any]] = []
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls") or ():
                blocks.append({
                    "type": "tool_use",
                    "id": str(tc.get("id") or ""),
                    "name": str(tc.get("name") or ""),
                    "input": tc.get("arguments") or {},
                })
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": str(m.get("tool_call_id") or ""),
                "content": str(m.get("content") or ""),
            }
            prev = out[-1] if out else None
            if (prev is not None and prev.get("role") == "user"
                    and isinstance(prev.get("content"), list)
                    and prev["content"]
                    and all(b.get("type") == "tool_result" for b in prev["content"])):
                prev["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        out.append({"role": role, "content": str(m.get("content") or "")})
    return out


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


def _raise_with_body(resp: httpx.Response) -> None:
    """非 2xx 时抛带响应体摘要的 HTTPStatusError。

    raise_for_status() 的 message 只含状态码与 URL,供应商的真实错误原因
    (如 MiniMax 2013 "tool id not found"、配额/鉴权文案)都在 body 里,
    丢了它用户气泡只剩一句 "Client error '400 Bad Request'",无法排障。
    """
    if resp.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}: {resp.text[:200]}",
            request=resp.request,
            response=resp,
        )


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
    messages = _resolve_tool_messages(messages)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if fmt == "anthropic":
            system, rest = _split_system(messages)
            body: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                # rest 为空(只有 system)时不发空 messages 数组,否则 MiniMax 报 2013
                "messages": _anthropic_messages(rest) or [
                    {"role": "user", "content": "（无内容，请继续。）"},
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
            _raise_with_body(resp)
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
            "messages": _chat_messages(messages) or [
                {"role": "user", "content": "（无内容，请继续。）"},
            ],
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
        _raise_with_body(resp)
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
        # complete 里已把 body 摘要放进 message,直接用,避免 "HTTP 400: HTTP 400:" 重复
        return TestResult(
            ok=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=model,
            error=str(exc),
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
