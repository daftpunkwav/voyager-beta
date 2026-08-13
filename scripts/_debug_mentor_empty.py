"""复现 Mentor 空正文路径（FakeLLM + 真实 tool registry）"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from agent_core.agents.react import ReActEngine
from agent_core.agents.registry import get_registry
from agent_core.llm.provider import LLMChunk, LLMCompleteResult, LLMProvider
from agent_core.memory.context import AgentRunContext
from agent_core.tools.builtin import ensure_tools_loaded
from agent_core.tools.registry import global_registry


class FakeLLM(LLMProvider):
    def __init__(self, script: list[dict]):
        super().__init__(None)
        self.script = list(script)
        self.i = 0

    @property
    def available(self) -> bool:
        return True

    async def complete(
        self,
        messages,
        *,
        tools=None,
        temperature=0.7,
        max_tokens=4096,
        stream=False,
        model_override=None,
    ):
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        print(
            f"  [llm#{self.i}] stream={stream} has_tools={bool(tools)} "
            f"n_tools={len(tools or [])} text_len={len(step.get('text') or '')} "
            f"tcalls={len(step.get('tool_calls') or [])}"
        )
        if stream:

            async def gen():
                text = step.get("text") or ""
                for i in range(0, max(len(text), 1), 20):
                    if text:
                        yield LLMChunk(type="text", text=text[i : i + 20])
                if step.get("fail"):
                    yield LLMChunk(type="error", error="fake fail")
                    return
                yield LLMChunk(type="done", usage={})

            return gen()
        return LLMCompleteResult(
            text=step.get("text") or "",
            tool_calls=step.get("tool_calls") or [],
            usage={"total_tokens": 1},
            failed=bool(step.get("fail")),
        )


async def run_case(name: str, script: list[dict]) -> str:
    print(f"\n=== {name} ===")
    engine = ReActEngine()
    agent = get_registry().get("mentor")
    llm = FakeLLM(script)
    ctx = AgentRunContext(
        user_id=uuid4(),
        session_id=uuid4(),
        agent_id="mentor",
        db=None,  # type: ignore
        llm=llm,
        llm_config=None,
        memory=None,  # type: ignore
        tool_registry=global_registry,
    )
    ctx.extra["disable_questions"] = True
    messages = [
        {"role": "system", "content": "you are mentor"},
        {"role": "user", "content": "分析项目 foo/bar"},
    ]
    texts: list[str] = []
    async for item in engine.run(
        agent_def=agent, ctx=ctx, messages=messages, emit_sse=True
    ):
        if isinstance(item, str):
            if "event: text_delta" in item:
                data = item.split("data: ", 1)[1].strip().split("\n")[0]
                texts.append(json.loads(data).get("content") or "")
            if "event: error" in item:
                print("  ERROR", item[:180])
        else:
            print(
                f"  EngineResult len={len(item.text or '')} "
                f"iter={item.iterations} preview={(item.text or '')[:80]!r}"
            )
    joined = "".join(texts)
    print(f"  joined_text_len={len(joined)} preview={joined[:120]!r}")
    return joined


def main() -> None:
    ensure_tools_loaded()
    names = [t.name for t in global_registry.get_tools_for_agent("mentor")]
    print("mentor tools:", names)

    tc = [
        {
            "id": "c1",
            "type": "function",
            "function": {
                "name": "get_project_detail",
                "arguments": '{"project_id":"00000000-0000-0000-0000-000000000001"}',
            },
        }
    ]
    asyncio.run(
        run_case(
            "A: tools then empty body (expect force final)",
            [
                {"kind": "tools", "text": "", "tool_calls": tc},
                {"kind": "empty", "text": "", "tool_calls": []},
                {"kind": "final", "text": "# Mentor 分析\n完整正文", "tool_calls": []},
            ],
        )
    )
    asyncio.run(
        run_case(
            "B: tools only x3 (expect force stream final)",
            [
                {"kind": "tools", "text": "", "tool_calls": tc},
                {"kind": "tools", "text": "", "tool_calls": tc},
                {"kind": "tools", "text": "", "tool_calls": tc},
                {"kind": "final", "text": "收口正文应该出现", "tool_calls": []},
            ],
        )
    )
    asyncio.run(
        run_case(
            "C: empty non-stream then force",
            [
                {"kind": "empty", "text": "", "tool_calls": []},
            ],
        )
    )


if __name__ == "__main__":
    main()
