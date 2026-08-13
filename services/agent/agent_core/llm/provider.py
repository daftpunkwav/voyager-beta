"""LiteLLM 封装 —— 流式/非流式补全"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

from agent_core.llm.config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMChunk:
    type: Literal["text", "thinking", "tool_call", "done", "error"]
    text: str = ""
    tool_call: dict[str, Any] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    error: str = ""


@dataclass
class LLMCompleteResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw_message: dict[str, Any] | None = None
    failed: bool = False
    # 原生 reasoning_content（与正文分离，供 thinking 通道）
    reasoning: str = ""


@dataclass
class LLMTestResult:
    success: bool
    latency_ms: int
    model: str
    reply: str = ""
    error: str = ""
    litellm_model: str = ""


class LLMProvider:
    """统一 LLM 调用层。"""

    def __init__(self, config: LLMConfig | None):
        self.config = config

    @property
    def available(self) -> bool:
        return self.config is not None and self.config.has_llm

    def _kwargs(self, model_override: str | None = None) -> dict[str, Any]:
        """始终经 litellm_model() 解析，禁止把裸模型名直接交给 LiteLLM。"""
        assert self.config is not None
        if model_override and model_override.strip():
            resolved = LLMConfig(
                provider=self.config.provider,
                model=model_override.strip(),
                api_key=self.config.api_key,
                api_base=self.config.api_base,
                api_format=self.config.api_format,
            )
        else:
            resolved = self.config
        model = resolved.litellm_model()
        # 兜底：仍无 provider 前缀时，按 api_format 强制加
        if "/" not in model:
            fmt = (resolved.api_format or "openai").lower()
            if fmt == "anthropic" or "anthropic" in (resolved.normalized_api_base() or ""):
                model = f"anthropic/{model}"
            elif fmt == "google":
                model = f"gemini/{model}"
            elif fmt == "ollama":
                model = f"ollama/{model}"
            else:
                model = f"openai/{model}"

        kw: dict[str, Any] = {
            "model": model,
            "api_key": self.config.api_key,
        }
        api_base = self.config.normalized_api_base()
        if api_base:
            fmt = (self.config.api_format or "openai").lower()
            # Ollama 本机：跳过公网 HTTPS SSRF 校验
            from urllib.parse import urlparse

            host = (urlparse(api_base).hostname or "").lower()
            is_local_ollama = fmt == "ollama" and host in (
                "localhost",
                "127.0.0.1",
                "::1",
            )
            if not is_local_ollama:
                from py_shared.security.url_safety import (
                    assert_safe_outbound_https_url,
                )

                try:
                    api_base = assert_safe_outbound_https_url(api_base)
                except ValueError as exc:
                    raise RuntimeError(f"LLM_API_BASE_BLOCKED: {exc}") from exc
            if api_base:
                kw["api_base"] = api_base
        # 按前缀显式指定 provider，避免 LiteLLM 无法识别自定义端点
        if model.startswith("anthropic/"):
            kw["custom_llm_provider"] = "anthropic"
        elif model.startswith("openai/"):
            kw["custom_llm_provider"] = "openai"
        elif model.startswith("gemini/"):
            kw["custom_llm_provider"] = "gemini"
        elif model.startswith("ollama/"):
            kw["custom_llm_provider"] = "ollama"
        logger.info(
            "LLM call route model=%s api_base=%s format=%s",
            model,
            api_base,
            self.config.api_format,
        )
        return kw

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        model_override: str | None = None,
    ) -> LLMCompleteResult | AsyncIterator[LLMChunk]:
        if not self.available or self.config is None:
            raise RuntimeError("LLM_NOT_CONFIGURED")

        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("litellm 未安装") from exc

        litellm.drop_params = True
        # Anthropic：历史含 tool_calls / tool 消息时，无 tools= 会报 UnsupportedParamsError
        litellm.modify_params = True
        call_kw = self._kwargs(model_override)
        call_kw.update(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if tools:
            call_kw["tools"] = tools
            call_kw["tool_choice"] = "auto"

        if stream:
            return self._stream(litellm, call_kw)
        return await self._complete_once(litellm, call_kw)

    async def _complete_once(self, litellm: Any, call_kw: dict) -> LLMCompleteResult:
        import asyncio

        call_kw["stream"] = False
        try:
            resp = await asyncio.wait_for(
                litellm.acompletion(**call_kw),
                timeout=120,
            )
        except asyncio.TimeoutError as e:
            logger.exception(
                "LLM complete timeout: model=%s base=%s",
                call_kw.get("model"),
                call_kw.get("api_base"),
            )
            raise RuntimeError("LLM 调用超时（120s）") from e
        except Exception as e:
            logger.exception("LLM complete failed: model=%s base=%s", call_kw.get("model"), call_kw.get("api_base"))
            raise RuntimeError(f"LLM 调用失败: {e}") from e

        choice = resp.choices[0]
        msg = choice.message
        content_text = _coerce_content(getattr(msg, "content", None)).strip()
        reasoning = _extract_reasoning(msg)
        tool_calls: list[dict[str, Any]] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                )
        # 有工具调用时：reasoning 保持独立，勿并入 text（避免工具轮丢思考）
        # 无工具且正文空：回落 reasoning，兼容只吐 reasoning 的模型
        text = content_text
        kept_reasoning = reasoning
        if not text and reasoning and not tool_calls:
            text = reasoning
            kept_reasoning = ""
        usage = _normalize_usage(getattr(resp, "usage", None))
        record_model = (
            (self.config.model if self.config else "")
            or call_kw.get("model")
            or ""
        )
        _maybe_record_usage(
            usage,
            model=record_model,
            provider=(self.config.provider if self.config else "") or "",
        )
        return LLMCompleteResult(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            reasoning=kept_reasoning,
            raw_message={
                "role": "assistant",
                "content": text or None,
                "tool_calls": tool_calls or None,
            },
        )

    async def _stream(self, litellm: Any, call_kw: dict) -> AsyncIterator[LLMChunk]:
        call_kw["stream"] = True
        provider_name = (self.config.provider if self.config else "") or ""
        if call_kw.get("tools"):
            result = await self._complete_once(litellm, {**call_kw, "stream": False})
            if result.tool_calls:
                for tc in result.tool_calls:
                    yield LLMChunk(type="tool_call", tool_call=tc)
            if result.text:
                step = 24
                for i in range(0, len(result.text), step):
                    yield LLMChunk(type="text", text=result.text[i : i + step])
            # _complete_once 已落库，此处不再重复
            yield LLMChunk(type="done", usage=result.usage)
            return

        try:
            import asyncio

            # OpenAI 兼容流式：请求最终 chunk 带 usage
            fmt = (self.config.api_format if self.config else "openai") or "openai"
            if fmt in ("openai", "custom", "ollama"):
                call_kw.setdefault("stream_options", {"include_usage": True})

            resp = await asyncio.wait_for(
                litellm.acompletion(**call_kw),
                timeout=120,
            )
            usage: dict[str, int] = {}
            async for chunk in resp:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = _normalize_usage(chunk_usage)
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield LLMChunk(type="text", text=content)
                reasoning = getattr(delta, "reasoning_content", None)
                if isinstance(reasoning, str) and reasoning:
                    yield LLMChunk(type="thinking", text=reasoning)
            _maybe_record_usage(
                usage,
                model=(self.config.model if self.config else "")
                or call_kw.get("model")
                or "",
                provider=provider_name,
            )
            yield LLMChunk(type="done", usage=usage)
        except asyncio.TimeoutError:
            logger.exception("LLM stream timeout")
            yield LLMChunk(type="error", error="LLM 调用超时（120s）")
        except Exception as e:
            logger.exception("LLM stream failed")
            yield LLMChunk(type="error", error=str(e))

    async def complete_json(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """要求模型返回 JSON 对象。"""
        result = await self.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        assert isinstance(result, LLMCompleteResult)
        text = result.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            # 保持空 dict 契约，但必须留痕，便于排查「LLM 返回被静默降级」
            logger.warning("complete_json parse failed: %s", text[:200])
            return {}

    async def test_connection(self, *, model_override: str | None = None) -> LLMTestResult:
        """
        真实请求一个模型：发送简短 prompt，收到非空回复视为通过。
        """
        import time

        if not self.available or self.config is None:
            return LLMTestResult(
                success=False,
                latency_ms=0,
                model="",
                error="未配置 API Key",
            )

        display_model = model_override or self.config.model
        litellm_name = ""
        try:
            kw = self._kwargs(model_override)
            litellm_name = str(kw.get("model") or "")
        except Exception:
            litellm_name = display_model

        t0 = time.perf_counter()
        try:
            # 推理型模型（如 MiniMax-M2.7）会先占用 thinking tokens，需给足预算
            result = await self.complete(
                [
                    {
                        "role": "user",
                        "content": "Reply with exactly: OK",
                    }
                ],
                max_tokens=256,
                temperature=0,
                stream=False,
                model_override=model_override,
            )
            assert isinstance(result, LLMCompleteResult)
            ms = int((time.perf_counter() - t0) * 1000)
            reply = (result.text or "").strip()
            if not reply:
                return LLMTestResult(
                    success=False,
                    latency_ms=ms,
                    model=display_model,
                    reply="",
                    error=(
                        "模型返回空正文（可能仍在 thinking，"
                        "请换用 highspeed 模型或增大 max_tokens）"
                    ),
                    litellm_model=litellm_name,
                )
            return LLMTestResult(
                success=True,
                latency_ms=ms,
                model=display_model,
                reply=reply[:500],
                error="",
                litellm_model=litellm_name,
            )
        except Exception as e:
            ms = int((time.perf_counter() - t0) * 1000)
            err = str(e)
            # 截断过长错误
            if len(err) > 800:
                err = err[:800] + "…"
            return LLMTestResult(
                success=False,
                latency_ms=ms,
                model=display_model,
                reply="",
                error=err,
                litellm_model=litellm_name,
            )


def _extract_reasoning(msg: Any) -> str:
    """提取原生 reasoning / thinking_blocks，不回落到 content。"""
    reasoning = getattr(msg, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    thinking_blocks = getattr(msg, "thinking_blocks", None)
    if isinstance(thinking_blocks, list):
        parts: list[str] = []
        for b in thinking_blocks:
            if isinstance(b, dict) and b.get("thinking"):
                parts.append(str(b["thinking"]))
            else:
                t = getattr(b, "thinking", None)
                if t:
                    parts.append(str(t))
        if parts:
            return "\n".join(parts)
    return ""


def _extract_text(msg: Any) -> str:
    """兼容 content 为 str / list(blocks)，以及 reasoning/thinking 回落。"""
    content = getattr(msg, "content", None)
    text = _coerce_content(content)
    if text.strip():
        return text
    return _extract_reasoning(msg)


def _coerce_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") in ("text", "output_text"):
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


def _normalize_usage(raw: Any) -> dict[str, int]:
    """将 LiteLLM / 厂商 usage 归一化为含命中字段的 dict。"""
    try:
        from agent_core import services as _agent_svc

        return _agent_svc.llm_usage().parse_usage_details(raw)
    except Exception:
        if not raw:
            return {}
        return {
            "prompt_tokens": int(getattr(raw, "prompt_tokens", 0) or 0)
            if not isinstance(raw, dict)
            else int(raw.get("prompt_tokens") or 0),
            "completion_tokens": int(getattr(raw, "completion_tokens", 0) or 0)
            if not isinstance(raw, dict)
            else int(raw.get("completion_tokens") or 0),
            "total_tokens": int(getattr(raw, "total_tokens", 0) or 0)
            if not isinstance(raw, dict)
            else int(raw.get("total_tokens") or 0),
            "prompt_cached_tokens": 0,
            "prompt_uncached_tokens": 0,
        }


def _strip_litellm_model_prefix(model: str) -> str:
    """去掉 litellm 路由前缀（anthropic/openai/…），保留真实模型名。"""
    m = (model or "").strip()
    if not m or "/" not in m:
        return m
    known = {
        "openai",
        "anthropic",
        "gemini",
        "ollama",
        "deepseek",
        "minimax",
        "azure",
        "bedrock",
        "vertex_ai",
    }
    left, right = m.split("/", 1)
    if left.lower() in known and right:
        return right
    return m


def _maybe_record_usage(
    usage: dict[str, int] | None,
    *,
    model: str,
    provider: str = "",
) -> None:
    """尽力记录用量；任何失败都吞掉，不影响主路径。"""
    if not usage:
        return
    try:
        from agent_core import services as _agent_svc

        display_model = _strip_litellm_model_prefix(model)
        prov = (provider or "").strip()
        if prov.lower() == "litellm":
            prov = "unknown"
        _agent_svc.llm_usage().record_parsed_usage_fire_and_forget(
            usage,
            model=display_model or model,
            provider=(prov or "unknown")[:64],
        )
    except Exception:
        logger.debug("用量记录跳过", exc_info=True)

