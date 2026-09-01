"""上下文压缩(§9.12):超预算时压缩/剪枝——先压缩最旧的工具结果,再按成对单元剪最旧的消息(phase-42)。"""

from __future__ import annotations

from typing import Any

#: 压缩预算(粗 token 估);接线上只提为常量,不开设置项(phase-15)
COMPRESS_BUDGET = 6000


#: 粗略 token 估算:中文约 1 字 ≈ 1 token,英文约 4 字符 ≈ 1 token;取保守值
def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = str(m.get("content", ""))
        total += max(len(content) // 2, 4)
    return total


def _prune_span(messages: list[dict[str, Any]], start: int) -> tuple[int, int]:
    """从 start 起定位最旧的可剪单元,返回待删的半开区间 (begin, end)。

    按成对形状(§9.1)整组删除,永不拆散工具对:
    - 跳过 system;user / 无 tool_calls 的 assistant / 孤立 tool 各删 1 条;
    - assistant 带 tool_calls 时连同其后**连续**的 tool 行一起删,
      不会留下「有 tool_calls 的 assistant 缺 tool 行」或「孤立 tool 行」。
    """
    i = start
    n = len(messages)
    while i < n and messages[i].get("role") == "system":
        i += 1
    if i >= n:
        return (i, i)  # 只剩 system:无可剪枝对象
    end = i + 1
    m = messages[i]
    if m.get("role") == "assistant" and m.get("tool_calls"):
        while end < n and messages[end].get("role") == "tool":
            end += 1
    return (i, end)


def compress(
    messages: list[dict[str, Any]], budget: int = COMPRESS_BUDGET,
    *, prune: bool = True,
) -> list[dict[str, Any]]:
    """返回压缩后的副本,不改原列表。system 消息永不压缩。

    prune=False 时只走第一刀(截断旧 tool 文本),不删消息条目——供 ReAct
    在同一回合的 transcript 上原地压缩:assistant(带 tool_calls) 与随后
    tool 行必须成对存在,剪掉任一侧端点会 400(phase-15)。
    """
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
    if not prune:
        return out
    # 第二刀:按成对/成组单元丢弃最旧的消息(phase-42),保留最近 8 条
    while len(out) > 8 and estimate_tokens(out) > budget:
        begin, end = _prune_span(out, 0)
        if end == begin:
            break  # 只剩 system 消息且仍超预算:无可剪枝对象,防死循环
        del out[begin:end]
    return out
