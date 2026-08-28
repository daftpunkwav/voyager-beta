"""笔记正文底纹标记(仍是 Markdown):==tone:text==,不是富文本。

用户工具栏与 mark_note_span 共用同一语法;本模块零依赖 capabilities,
便于单测与后续扩展色板。
"""

from __future__ import annotations

import re

TONES = ("warm", "cool", "rose", "lime")
CLEAR = "clear"
QUOTE_MAX = 500

_TOKEN_RE = re.compile(r"^==(warm|cool|rose|lime):(.*)==\Z", re.DOTALL)
_BARE_RE = re.compile(r"^==(.*)==\Z", re.DOTALL)


class MarkError(ValueError):
    """底纹参数非法,或正文中找不到对应片段。"""


def parse_mark(text: str) -> tuple[str, str] | None:
    """完整标记 → (tone, inner);无法识别则 None。"""
    if not text:
        return None
    matched = _TOKEN_RE.fullmatch(text)
    if matched:
        return matched.group(1), matched.group(2)
    matched = _BARE_RE.fullmatch(text)
    if not matched:
        return None
    inner = matched.group(1)
    for tone in TONES:
        prefix = f"{tone}:"
        if inner.startswith(prefix):
            return tone, inner[len(prefix):]
    return "warm", inner


def wrap_mark(inner: str, tone: str) -> str:
    return f"=={tone}:{inner}=="


def _in_fence(content: str, idx: int) -> bool:
    return content[:idx].count("```") % 2 == 1


def _find_needle(content: str, needle: str) -> int:
    start = 0
    while True:
        idx = content.find(needle, start)
        if idx < 0:
            return -1
        if not _in_fence(content, idx):
            return idx
        start = idx + 1


def existing_span(content: str, inner_at: int, inner_len: int) -> tuple[int, int, str] | None:
    """inner 已包在 ==tone:…== 或 ==…== 里时返回 (start, end, tone)。"""
    after = inner_at + inner_len
    if content[after:after + 2] != "==":
        return None
    for tone in TONES:
        prefix = f"=={tone}:"
        if inner_at >= len(prefix) and content[inner_at - len(prefix):inner_at] == prefix:
            return inner_at - len(prefix), after + 2, tone
    if inner_at >= 2 and content[inner_at - 2:inner_at] == "==":
        return inner_at - 2, after + 2, "warm"
    return None


def apply_note_mark(content: str, quote: str, tone: str) -> str:
    """给正文中围栏外首次出现的 quote 上色或去掉底纹。已是目标色则幂等。"""
    tone = (tone or "").strip()
    if tone not in TONES and tone != CLEAR:
        raise MarkError(f"tone 须为 {list(TONES)} 或 {CLEAR}")
    raw = quote or ""
    if not raw.strip():
        raise MarkError("quote 不能为空")
    if len(raw) > QUOTE_MAX:
        raw = raw[:QUOTE_MAX]

    parsed = parse_mark(raw)
    needle = parsed[1] if parsed else raw
    if not needle or "==" in needle:
        raise MarkError("片段不能为空或含 ==")

    idx = _find_needle(content, needle)
    if idx < 0:
        raise MarkError("正文中找不到该片段")

    span = existing_span(content, idx, len(needle))
    if tone == CLEAR:
        if span is None:
            return content
        start, end, _ = span
        return content[:start] + needle + content[end:]

    token = wrap_mark(needle, tone)
    if span is None:
        return content[:idx] + token + content[idx + len(needle):]
    start, end, old = span
    if old == tone:
        return content
    return content[:start] + token + content[end:]
