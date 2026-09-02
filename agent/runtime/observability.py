"""可观测(§7.8 / §9.1):每次 LLM/tool call 计量,供用量页(§10.9)与审计。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent.llm import LLMClient, LLMReply, Usage


@dataclass(frozen=True)
class MeterRecord:
    kind: str  # "llm" | "tool"
    name: str  # 模型名或工具名
    ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    ok: bool = True
    ts: float = field(default_factory=time.time)


class Meter:
    """内存计量;持久化(→ 用量页)由 sink 回调承接。"""

    def __init__(self, sink: Any = None) -> None:
        self.records: list[MeterRecord] = []
        self._sink = sink

    def record(self, rec: MeterRecord) -> None:
        self.records.append(rec)
        if self._sink is not None:
            self._sink(rec)

    def totals(self) -> dict[str, int]:
        return {
            "llm_calls": sum(1 for r in self.records if r.kind == "llm"),
            "tool_calls": sum(1 for r in self.records if r.kind == "tool"),
            "input_tokens": sum(r.input_tokens for r in self.records),
            "output_tokens": sum(r.output_tokens for r in self.records),
        }

    def tokens_used_today(self, *, now: float | None = None) -> int:
        """当日已用 token(input+output 合计);自然日按 UTC 切日(单测钉死)。

        MeterRecord.ts 是 time.time() 秒级 UNIX 时间戳,换算成 UTC (年,月,日)
        后聚合;now 供测试注入当前时刻,不传取真实时钟。
        """
        current = time.time() if now is None else now
        today = time.gmtime(current)[:3]
        return sum(
            r.input_tokens + r.output_tokens
            for r in self.records
            if time.gmtime(r.ts)[:3] == today
        )


#: 日配额超限的降级文本:与 ServiceLLM 的错误呈现同款(LLMReply 可读文本,
#: 不打断 agent 循环),不抛异常。
_QUOTA_EXCEEDED = (
    "（今日 LLM token 配额已用完:明天自动恢复,或在设置里调高/关闭日配额。）"
)


def is_quota_exceeded_reply(text: str | None) -> bool:
    """识别文本是否为配额超限降级句(§9.9)。

    metered_llm 超限时返回可读降级文本而非异常,调用方(如 proactive 问候)
    需要区分「真回复」与「降级句」。按「配额」+「用完」两个关键子串判定,
    与 _QUOTA_EXCEEDED 措辞解耦:改文案不动检测。
    """
    if not text:
        return False
    return "配额" in text and "用完" in text


def metered_llm(
    llm: LLMClient,
    meter: Meter,
    *,
    model: str = "default",
    quota_fn: Callable[[], int] | None = None,
) -> LLMClient:
    """包一层:每次 complete 前查 token 日配额,之后记录耗时与 token。

    quota_fn 热读当日 token 上限(如 agent.resource.daily_tokens),每次
    complete 现读——设置页改配额下一句生效;None 或返回 0 = 不限。
    超限不发起真实调用、不记 meter,直接返回降级文本。
    """

    class _Metered:
        async def complete(self, messages, tools=None) -> LLMReply:
            if quota_fn is not None:
                try:
                    limit = int(quota_fn())
                except (TypeError, ValueError):
                    limit = 0  # 脏值当不限,与轮数上限的容错同风格
                if limit > 0 and meter.tokens_used_today() >= limit:
                    return LLMReply(text=_QUOTA_EXCEEDED)
            start = time.perf_counter()
            reply: LLMReply | None = None
            ok = True
            try:
                reply = await llm.complete(messages, tools)
                return reply
            except Exception:
                ok = False
                raise
            finally:
                ms = (time.perf_counter() - start) * 1000
                usage = reply.usage if reply is not None else Usage()
                meter.record(
                    MeterRecord(
                        kind="llm",
                        name=model,
                        ms=ms,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        ok=ok,
                    )
                )

    return _Metered()
