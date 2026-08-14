"""可观测(§7.8 / §9.1):每次 LLM/tool call 计量,供用量页(§10.9)与审计。"""

from __future__ import annotations

import time
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


def metered_llm(llm: LLMClient, meter: Meter, *, model: str = "default") -> LLMClient:
    """包一层:每次 complete 记录耗时与 token。"""

    class _Metered:
        async def complete(self, messages, tools=None) -> LLMReply:
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
