"""上下文压缩(§9.12):超预算时压缩/剪枝——先压缩最旧的工具结果,再剪最旧的非 system 消息。"""

from __future__ import annotations

from typing import Any


#: 粗略 token 估算:中文约 1 字 ≈ 1 token,英文约 4 字符 ≈ 1 token;取保守值
def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = str(m.get("content", ""))
        total += max(len(content) // 2, 4)
    return total


def compress(
    messages: list[dict[str, Any]], budget: int = 6000
) -> list[dict[str, Any]]:
    """返回压缩后的副本,不改原列表。system 消息永不压缩。"""
    out = list(messages)
    if estimate_tokens(out) <= budget:
        return out
    # 第一刀:最旧的 tool 结果截断为占位
    for i, m in enumerate(out):
        if m.get("role") == "tool" and i < len(out) - 4:
            content = str(m.get("content", ""))
            if len(content) > 200:
                out[i] = {**m, "content": content[:80] + " …[已压缩]"}
        if estimate_tokens(out) <= budget:
            return out
    # 第二刀:丢弃最旧的非 system 消息(保留最近 6 条)
    while len(out) > 8 and estimate_tokens(out) > budget:
        for i, m in enumerate(out):
            if m.get("role") != "system":
                del out[i]
                break
    return out
