"""LLM 直连客户端(修订自旧 llm/provider.py):去掉 litellm 依赖,httpx 直连。

只支持两种 API 格式(§8.8):`chat`(OpenAI 兼容)与 `anthropic`(Messages)。
用量在 complete 成功后由调用方写入 store(计量直写,不再是日志解析)。
"""

from __future__ import annotations

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


async def complete(
    provider: dict[str, Any],
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> CompleteResult:
    fmt = provider["api_format"]
    base = provider["base_url"].rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if fmt == "anthropic":
            system, rest = _split_system(messages)
            resp = await client.post(
                f"{base}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system,
                    "messages": [
                        {"role": m["role"], "content": str(m.get("content", ""))}
                        for m in rest
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage") or {}
            text = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            )
            return CompleteResult(
                text=text,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                model=data.get("model", model),
            )
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        return CompleteResult(
            text=str((choice.get("message") or {}).get("content") or ""),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=data.get("model", model),
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
