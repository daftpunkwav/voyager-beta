"""从各厂商 / LiteLLM usage 对象解析命中与未命中 Token。"""
from __future__ import annotations

from typing import Any


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def parse_usage_details(raw: Any) -> dict[str, int]:
    """
    归一化 usage 为：
    prompt_tokens / prompt_cached_tokens / prompt_uncached_tokens /
    completion_tokens / total_tokens
    """
    if not raw:
        return {
            "prompt_tokens": 0,
            "prompt_cached_tokens": 0,
            "prompt_uncached_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    prompt = _as_int(_get(raw, "prompt_tokens") or _get(raw, "input_tokens"))
    completion = _as_int(
        _get(raw, "completion_tokens") or _get(raw, "output_tokens")
    )
    total = _as_int(_get(raw, "total_tokens"))
    if total <= 0:
        total = prompt + completion

    cached = 0
    details = _get(raw, "prompt_tokens_details")
    if details is not None:
        cached = _as_int(_get(details, "cached_tokens"))

    # Anthropic / LiteLLM 常见字段
    cache_read = _as_int(_get(raw, "cache_read_input_tokens"))
    cache_creation = _as_int(_get(raw, "cache_creation_input_tokens"))
    if cache_read > cached:
        cached = cache_read

    if cached <= 0 and prompt <= 0:
        # 部分响应把明细放在嵌套 usage
        nested = _get(raw, "usage")
        if nested is not None and nested is not raw:
            return parse_usage_details(nested)

    if cached > prompt > 0:
        cached = prompt

    if prompt > 0:
        uncached = max(0, prompt - cached)
        # cache_creation 属于未命中写入；已包含在 prompt-cached 中则不再叠加
        if cache_creation > 0 and uncached == 0 and cached == 0:
            uncached = cache_creation
    else:
        # 仅有 cache 字段时回填
        uncached = cache_creation
        prompt = cached + uncached
        if total <= 0:
            total = prompt + completion

    return {
        "prompt_tokens": prompt,
        "prompt_cached_tokens": cached,
        "prompt_uncached_tokens": uncached,
        "completion_tokens": completion,
        "total_tokens": total or (prompt + completion),
    }
