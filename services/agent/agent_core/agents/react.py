"""ReAct / Plan-Execute / Reflexion 执行引擎"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from agent_core.agents.question import _normalize_question
from agent_core.agents.registry import AgentDefinition
from agent_core.agents.stream_events import StreamEvent, format_sse
from agent_core.agents.types import AgentEngineConfig, Messages, Workflow
from agent_core.llm.provider import LLMCompleteResult, LLMProvider
from agent_core.memory.context import AgentRunContext

logger = logging.getLogger(__name__)


def _is_stream_frame(item: Any) -> bool:
    """SSE 字符串或 typed StreamEvent（非 LCR / EngineResult）。"""
    return isinstance(item, (str, StreamEvent))


@dataclass
class EngineResult:
    text: str = ""
    agent_id: str = "hub"
    usage: dict[str, int] = field(default_factory=dict)
    iterations: int = 0
    question: dict[str, Any] | None = None
    dispatches: list[dict[str, Any]] = field(default_factory=list)
    pending_status: str | None = None


def _strip_think_markers(text: str) -> str:
    """去掉 THINK 标记，保留内部与正文。"""
    from agent_core.agents.think_stream import THINK_END, THINK_START

    s = text or ""
    s = s.replace(THINK_START, "").replace(THINK_END, "")
    return s.strip()


def _emit_text_deltas(text: str, *, emit_sse: bool, step: int = 24) -> list[str]:
    """把长文本切片为 text_delta SSE 事件列表（统一切片步长，避免魔数散落）。"""
    if not emit_sse or not text:
        return []
    return [
        format_sse("text_delta", {"content": text[i : i + step]})
        for i in range(0, len(text), step)
    ]


class ReActEngine:
    MAX_ITERATIONS = AgentEngineConfig().max_iterations

    def __init__(
        self,
        max_iterations: int | None = None,
        config: AgentEngineConfig | None = None,
    ):
        self.config = config or AgentEngineConfig()
        self.max_iterations = max_iterations or self.config.max_iterations

    def _effective_max_iter(self, agent_def: AgentDefinition) -> int:
        """优先使用 Agent 定义的 max_iterations。"""
        defined = getattr(agent_def, "max_iterations", None)
        if isinstance(defined, int) and defined > 0:
            return min(defined, self.max_iterations)
        return self.max_iterations

    def _prefer_token_stream(self, agent_def: AgentDefinition, tools: list) -> bool:
        """
        direct / 无工具：直接真流式吐 token。
        cot 仅在无工具时走两阶段流式；有工具则走工具环。
        ReAct 有工具时：工具轮非流式，最终回答轮再流式（见循环内分支）。
        """
        if not getattr(agent_def, "streaming", True):
            return False
        wf = Workflow((agent_def.workflow or "react").lower())
        if wf == Workflow.DIRECT:
            return True
        if not tools:
            return True
        return False

    async def _stream_plain_text(
        self,
        *,
        llm: LLMProvider,
        messages: list[dict[str, Any]],
        agent_def: AgentDefinition,
        emit_sse: bool,
        channel: str = "text",
        max_tokens: int | None = None,
    ) -> AsyncIterator[str | Any]:
        """纯流式：channel=text→text_delta，channel=thinking→thinking。最后 yield LLMCompleteResult。"""
        from agent_core.llm.provider import LLMChunk
        from agent_core.llm.provider import LLMCompleteResult as LCR

        full = ""
        usage: dict[str, int] = {}
        event_name = "thinking" if channel == "thinking" else "text_delta"
        try:
            stream = await llm.complete(
                messages,
                tools=None,
                temperature=agent_def.temperature,
                max_tokens=max_tokens or agent_def.max_tokens,
                stream=True,
                model_override=agent_def.model_override,
            )
            assert not isinstance(stream, LCR)
            async for chunk in stream:
                if not isinstance(chunk, LLMChunk):
                    continue
                if chunk.type == "text" and chunk.text:
                    full += chunk.text
                    if emit_sse:
                        yield format_sse(event_name, {"content": chunk.text})
                elif chunk.type == "thinking" and chunk.text:
                    # 原生 reasoning：
                    # - channel=thinking：计入 full（规划注入）并进 thinking SSE
                    # - channel=text：推理模型常把全文放 reasoning；提升为正文，避免气泡空白
                    if channel == "thinking":
                        full += chunk.text
                        if emit_sse:
                            yield format_sse("thinking", {"content": chunk.text})
                    else:
                        full += chunk.text
                        if emit_sse:
                            yield format_sse("text_delta", {"content": chunk.text})
                elif chunk.type == "done":
                    usage = chunk.usage or {}
                elif chunk.type == "error":
                    err = chunk.error or "LLM 流式错误"
                    code = (
                        "LLM_TIMEOUT"
                        if "超时" in err
                        else "LLM_REQUEST_FAILED"
                    )
                    if emit_sse:
                        yield format_sse("error", {"code": code, "message": err})
                    yield LCR(text=full or err, usage=usage, failed=True)
                    return
        except Exception as e:
            logger.exception("LLM stream error in engine")
            err = f"LLM 调用失败：{e}"
            code = "LLM_TIMEOUT" if "超时" in str(e) else "LLM_REQUEST_FAILED"
            if emit_sse:
                yield format_sse("error", {"code": code, "message": err})
            yield LCR(text=full or err, usage=usage, failed=True)
            return
        yield LCR(text=full, usage=usage, failed=False)

    async def _cot_two_phase_stream(
        self,
        *,
        llm: LLMProvider,
        messages: list[dict[str, Any]],
        agent_def: AgentDefinition,
        emit_sse: bool,
        total_usage: dict[str, int],
    ) -> AsyncIterator[str | EngineResult]:
        """
        CoT 两阶段（不依赖模型自觉写标记）：
        1) 流式生成短推理 → thinking 通道
        2) 流式生成正文 → text_delta 通道
        """
        if emit_sse:
            # workflow 可能是 Workflow 枚举（registry）或裸字符串（apply_*_mode replace）
            raw_wf = agent_def.workflow or "cot"
            wf_label = raw_wf.value if isinstance(raw_wf, Workflow) else str(raw_wf)
            yield format_sse(
                "thinking",
                {
                    "content": (
                        f"[状态] {agent_def.name} · {wf_label}\n"
                        f"[阶段 1/2] 生成分析思路…\n"
                    )
                },
            )

        think_messages = list(messages) + [
            {
                "role": "user",
                "content": (
                    "先只输出分析思路（3-6 句要点），说明你会看哪些方面、结论方向。"
                    "不要写最终完整正文，不要标题装饰，不要 emoji。"
                ),
            }
        ]
        think_text = ""
        phase1_failed = False
        async for item in self._stream_plain_text(
            llm=llm,
            messages=think_messages,
            agent_def=agent_def,
            emit_sse=emit_sse,
            channel="thinking",
            max_tokens=min(320, agent_def.max_tokens),
        ):
            if _is_stream_frame(item):
                yield item
            else:
                think_text = (item.text or "").strip()
                phase1_failed = bool(getattr(item, "failed", False))
                for k in total_usage:
                    total_usage[k] = total_usage.get(k, 0) + (item.usage or {}).get(k, 0)

        if phase1_failed:
            if emit_sse:
                yield format_sse(
                    "done",
                    {
                        "usage": {
                            "tokens": total_usage.get("total_tokens", 0),
                            **total_usage,
                        },
                        "iterations": 1,
                        "agent_id": agent_def.id,
                        "failed": True,
                    },
                )
            yield EngineResult(
                text=think_text or "LLM 调用失败",
                agent_id=agent_def.id,
                usage=total_usage,
                iterations=1,
            )
            return

        if emit_sse and not think_text:
            yield format_sse(
                "thinking",
                {"content": "（思路阶段无内容，继续生成正文）\n"},
            )
        elif emit_sse and think_text and not think_text.endswith("\n"):
            yield format_sse("thinking", {"content": "\n"})

        if emit_sse:
            yield format_sse(
                "thinking",
                {"content": "[阶段 2/2] 基于思路流式输出正文…\n"},
            )

        answer_messages = list(messages)
        if think_text:
            answer_messages = list(messages) + [
                {
                    "role": "assistant",
                    "content": f"分析思路：\n{think_text}",
                },
                {
                    "role": "user",
                    "content": (
                        "请基于上述思路输出完整正文（Markdown）。"
                        "不要重复思路段落，不要 emoji，直接给用户可读结论。"
                    ),
                },
            ]

        final_text = ""
        async for item in self._stream_plain_text(
            llm=llm,
            messages=answer_messages,
            agent_def=agent_def,
            emit_sse=emit_sse,
            channel="text",
            max_tokens=agent_def.max_tokens,
        ):
            if _is_stream_frame(item):
                yield item
            else:
                final_text = (item.text or "").strip()
                for k in total_usage:
                    total_usage[k] = total_usage.get(k, 0) + (item.usage or {}).get(k, 0)

        if not final_text:
            final_text = (
                f"我是 {agent_def.name}，已收到你的消息。"
                "请补充更具体的需求（例如技术栈、学习目标），我会继续帮你。"
            )
            if emit_sse:
                yield format_sse("text_delta", {"content": final_text})

        if emit_sse:
            yield format_sse(
                "done",
                {
                    "usage": {
                        "tokens": total_usage.get("total_tokens", 0),
                        **total_usage,
                    },
                    "iterations": 2,
                    "agent_id": agent_def.id,
                    "streamed": True,
                    "cot_two_phase": True,
                },
            )
        yield EngineResult(
            text=final_text,
            agent_id=agent_def.id,
            usage=total_usage,
            iterations=2,
        )


    async def _plan_phase_to_thinking(
        self,
        *,
        llm: LLMProvider,
        messages: Messages,
        agent_def: AgentDefinition,
        emit_sse: bool,
        total_usage: dict[str, int],
        workflow: Workflow,
    ) -> AsyncIterator[str | list[dict[str, Any]]]:
        """多步工作流：先流式生成真实行动计划 → thinking，再把计划注入后续消息。"""
        if emit_sse:
            yield format_sse(
                "thinking",
                {
                    "content": (
                        f"[规划] {agent_def.name} · {workflow.value}\n"
                        "正在生成行动计划…\n\n"
                    )
                },
            )

        if workflow == Workflow.PLAN_EXECUTE:
            plan_prompt = (
                "先只输出本轮行动计划（3-6 条短句要点），说明："
                "1) 用户意图理解；2) 是否需要调度专家（谁/为何）；"
                "3) 自己直接回答什么。不要写给用户看的最终正文，不要 emoji。"
            )
            exec_prompt = (
                "请按上述计划立刻执行，不要再复述或改写「执行计划」列表。"
                "需要调度专家时必须调用 dispatch_agent（可一次多个，默认≤2）；"
                "可直接回答则输出用户可见的完整正文（Markdown）。"
                "禁止只宣布计划；禁止输出「收到，这就调度…」之类空承诺正文"
                "（不调工具、不写完整答复就结束）；禁止 emoji。"
            )
        elif workflow == Workflow.TOT:
            plan_prompt = (
                "先只输出讲解路径比较（2-3 条）并标明将展开哪一条。"
                "不要写完整讲解正文，不要 emoji。"
            )
            exec_prompt = (
                "请按选定路径立刻写出用户可见的完整 Markdown 正文。"
                "仅可使用你当前可用的工具白名单；禁止调用或提及 dispatch_agent。"
                "禁止只宣布计划、禁止 emoji。"
            )
        else:
            plan_prompt = (
                "先只输出方案要点与自我检查清单（3-5 条）。"
                "不要写最终建议正文，不要 emoji。"
            )
            exec_prompt = (
                "请按检查清单立刻写出用户可见的完整 Markdown 正文。"
                "仅可使用你当前可用的工具白名单；禁止调用或提及 dispatch_agent。"
                "禁止只宣布计划、禁止 emoji。"
            )

        # 高置信快速编排：压缩规划 token；tot 讲解路径需要略宽
        plan_cap = min(self.config.plan_cap_default, agent_def.max_tokens)
        if workflow == Workflow.TOT:
            plan_cap = min(self.config.plan_cap_tot, agent_def.max_tokens)
        blob = " ".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "user"
        )
        if "[快速编排]" in blob:
            plan_cap = min(280, plan_cap)
            plan_prompt = (
                "用 ≤3 条极短要点写出行动计划（意图 / 调度谁 / 是否自答），"
                "不要最终正文，不要 emoji。"
            )

        plan_messages = list(messages) + [{"role": "user", "content": plan_prompt}]
        plan_text = ""
        async for item in self._stream_plain_text(
            llm=llm,
            messages=plan_messages,
            agent_def=agent_def,
            emit_sse=emit_sse,
            channel="thinking",
            max_tokens=plan_cap,
        ):
            if _is_stream_frame(item):
                yield item
            else:
                plan_text = (item.text or "").strip()
                for k in total_usage:
                    total_usage[k] = total_usage.get(k, 0) + (item.usage or {}).get(k, 0)

        if emit_sse:
            yield format_sse("thinking", {"content": "\n[规划完成] 开始执行…\n"})

        next_messages = list(messages)
        if plan_text:
            next_messages = list(messages) + [
                {"role": "assistant", "content": f"行动计划：\n{plan_text}"},
                {"role": "user", "content": exec_prompt},
            ]
        yield next_messages

    async def run(
        self,
        *,
        agent_def: AgentDefinition,
        ctx: AgentRunContext,
        messages: list[dict[str, Any]],
        emit_sse: bool = True,
    ) -> AsyncIterator[str | EngineResult]:
        """
        执行推理循环。yield SSE 字符串；最后 yield EngineResult。

        只做分派：
        - 降级检查（无 LLM）
        - 工具白名单准备 + workflow_hint 注入
        - cot / direct / 无工具 → 真 token 流式（_run_direct_stream / _cot_two_phase_stream）
        - plan_execute / tot / reflexion → 先规划再工具环（_run_tool_loop + _run_closing_reply）
        """
        llm = ctx.llm
        if not llm.available:
            async for item in self._run_degraded(agent_def, messages, emit_sse):
                yield item
            return

        tools = self._prepare_tools(agent_def, ctx)
        # direct = 汇总/强制无工具快路径；cot 保留工具能力（由白名单决定）
        wf = Workflow((agent_def.workflow or "react").lower())
        if wf == Workflow.DIRECT:
            tools = []

        # 工作流提示注入
        workflow_hint = self._workflow_hint(agent_def)
        if workflow_hint:
            messages = list(messages)
            messages.insert(1, {"role": "system", "content": workflow_hint})

        total_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        # —— 流式快路径 ——
        # cot：两阶段；direct / 其它无工具：单次正文流式
        if self._prefer_token_stream(agent_def, tools):
            if wf == Workflow.COT:
                async for item in self._cot_two_phase_stream(
                    llm=llm,
                    messages=messages,
                    agent_def=agent_def,
                    emit_sse=emit_sse,
                    total_usage=total_usage,
                ):
                    yield item
                return
            async for item in self._run_direct_stream(
                llm=llm,
                messages=messages,
                agent_def=agent_def,
                emit_sse=emit_sse,
                total_usage=total_usage,
            ):
                yield item
            return

        # —— 多步工作流：先流式输出真实规划到 thinking，再进入工具环 ——
        if wf in (Workflow.PLAN_EXECUTE, Workflow.TOT, Workflow.REFLEXION):
            async for item in self._plan_phase_to_thinking(
                llm=llm,
                messages=messages,
                agent_def=agent_def,
                emit_sse=emit_sse,
                total_usage=total_usage,
                workflow=wf,
            ):
                if isinstance(item, list):
                    messages = item
                elif _is_stream_frame(item):
                    yield item

        # —— 工具环 + 收口 ——
        # _run_tool_loop 收尾 yield (final_text, dispatches, iteration)；
        # 终态分支（LLM 异常 / 反问拦截）已产出 EngineResult，yield ("__abort__",) 跳过收口
        outcome: tuple | None = None
        async for item in self._run_tool_loop(
            llm=llm,
            messages=messages,
            agent_def=agent_def,
            ctx=ctx,
            emit_sse=emit_sse,
            total_usage=total_usage,
            tools=tools,
            wf=wf,
        ):
            if isinstance(item, tuple):
                outcome = item
            else:
                yield item
        if outcome == ("__abort__",):
            return
        assert outcome is not None
        final_text, dispatches, iteration = outcome
        async for item in self._run_closing_reply(
            llm=llm,
            messages=messages,
            agent_def=agent_def,
            emit_sse=emit_sse,
            total_usage=total_usage,
            final_text=final_text,
            dispatches=dispatches,
            iteration=iteration,
        ):
            yield item

    def _prepare_tools(self, agent_def: AgentDefinition, ctx: AgentRunContext) -> list:
        """仅暴露 AgentDefinition.tools 白名单，避免 registry 里 allowed_agents 过宽。"""
        tools = ctx.tool_registry.openai_tools_for(agent_def.id)
        if agent_def.tools:
            allow = set(agent_def.tools)
            tools = [
                t
                for t in tools
                if (t.get("function") or {}).get("name") in allow
            ]
        else:
            tools = []
        return tools

    async def _run_degraded(
        self,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        emit_sse: bool,
    ) -> AsyncIterator[str | EngineResult]:
        """降级模式（无 LLM）：固定文案切片发出后直接返回 EngineResult。"""
        text = self._degraded_reply(agent_def, messages)
        if emit_sse:
            for _sse in _emit_text_deltas(text, emit_sse=emit_sse):
                yield _sse
            yield format_sse(
                "done",
                {"usage": {"tokens": len(text)}, "iterations": 0, "degraded": True},
            )
        yield EngineResult(text=text, agent_id=agent_def.id, iterations=0)

    async def _run_direct_stream(
        self,
        *,
        llm: LLMProvider,
        messages: list[dict[str, Any]],
        agent_def: AgentDefinition,
        emit_sse: bool,
        total_usage: dict[str, int],
    ) -> AsyncIterator[str | EngineResult]:
        """direct / 无工具：单次正文真流式，最后发 done + EngineResult。"""
        # Hub 汇总轮已有「汇总中」状态，勿再叠「生成中」
        if emit_sse and agent_def.id != "hub":
            yield format_sse(
                "thinking",
                {
                    "content": f"[状态] {agent_def.name} · 生成中\n",
                },
            )
        final_text = ""
        async for item in self._stream_plain_text(
            llm=llm,
            messages=messages,
            agent_def=agent_def,
            emit_sse=emit_sse,
            channel="text",
        ):
            if _is_stream_frame(item):
                yield item
            else:
                final_text = (item.text or "").strip()
                for k in total_usage:
                    total_usage[k] = total_usage.get(k, 0) + (
                        item.usage or {}
                    ).get(k, 0)
                if getattr(item, "failed", False):
                    if emit_sse:
                        yield format_sse(
                            "done",
                            {
                                "usage": total_usage,
                                "iterations": 1,
                                "agent_id": agent_def.id,
                                "failed": True,
                            },
                        )
                    yield EngineResult(
                        text=final_text or "LLM 调用失败",
                        agent_id=agent_def.id,
                        usage=total_usage,
                        iterations=1,
                    )
                    return
        if emit_sse:
            yield format_sse(
                "done",
                {
                    "usage": {
                        "tokens": total_usage.get("total_tokens", 0),
                        **total_usage,
                    },
                    "iterations": 1,
                    "agent_id": agent_def.id,
                    "streamed": True,
                },
            )
        yield EngineResult(
            text=final_text,
            agent_id=agent_def.id,
            usage=total_usage,
            iterations=1,
        )

    async def _run_tool_loop(
        self,
        *,
        llm: LLMProvider,
        messages: list[dict[str, Any]],
        agent_def: AgentDefinition,
        ctx: AgentRunContext,
        emit_sse: bool,
        total_usage: dict[str, int],
        tools: list,
        wf: Workflow,
    ) -> AsyncIterator[str | tuple]:
        """多步工作流的工具轮循环：yield SSE；收尾 yield (final_text, dispatches, iteration)。"""
        final_text = ""
        dispatches: list[dict[str, Any]] = []
        iteration = 0
        max_iter = self._effective_max_iter(agent_def)
        # plan_execute 偶发把「执行计划」当最终答复；最多纠正 2 次
        plan_nudge_used = 0

        while iteration < max_iter:
            iteration += 1
            if emit_sse:
                yield format_sse(
                    "thinking",
                    {
                        "content": (
                            f"[状态] 执行 · {agent_def.name} · "
                            f"{iteration}/{max_iter}\n"
                        ),
                        "iteration": iteration,
                    },
                )

            try:
                result = await llm.complete(
                    messages,
                    tools=tools if tools else None,
                    temperature=agent_def.temperature,
                    max_tokens=agent_def.max_tokens,
                    stream=False,
                    model_override=agent_def.model_override,
                )
            except Exception as e:
                logger.exception("LLM error in ReAct")
                err = f"LLM 调用失败：{e}"
                code = "LLM_TIMEOUT" if "超时" in str(e) else "LLM_REQUEST_FAILED"
                if emit_sse:
                    yield format_sse("error", {"code": code, "message": err})
                yield EngineResult(text=err, agent_id=agent_def.id, iterations=iteration)
                yield ("__abort__",)
                return

            assert isinstance(result, LLMCompleteResult)
            for k in total_usage:
                total_usage[k] = total_usage.get(k, 0) + result.usage.get(k, 0)

            # 原生 reasoning 立刻进思考区（工具轮非流式时尤其重要）
            native_reason = (getattr(result, "reasoning", None) or "").strip()
            if native_reason and emit_sse:
                yield format_sse(
                    "thinking",
                    {"content": f"[中间推理]\n{native_reason}\n"},
                )

            # assistant message
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": result.text or None,
            }
            if result.tool_calls:
                assistant_msg["tool_calls"] = result.tool_calls
            messages.append(assistant_msg)

            # 工具轮若附带部分正文，先记入思考区，避免信息丢失
            if result.tool_calls and result.text and emit_sse:
                yield format_sse(
                    "thinking",
                    {"content": f"[中间推理]\n{(result.text or '').strip()}\n"},
                )

            # 推理模型常见：长文在 reasoning、text 为空且无工具 → 直接提升为正文
            if (
                not result.tool_calls
                and not (result.text or "").strip()
                and native_reason
            ):
                final_text = native_reason
                for _sse in _emit_text_deltas(final_text, emit_sse=emit_sse):
                    yield _sse
                break

            if result.text and not result.tool_calls:
                from agent_core.agents.think_stream import split_complete_text

                think, body = split_complete_text(result.text)
                # 未闭合 THINK 时 split 会把全文当 thinking、body 为空；
                # 此时仍应用全文作正文，避免「思考区有货、气泡空白」
                if think and not (body or "").strip():
                    candidate = _strip_think_markers(result.text).strip() or result.text.strip()
                    think = ""
                else:
                    candidate = (body or result.text or "").strip()
                # Hub/plan_execute：只宣布「执行计划」而未调工具 → 纠正后继续，避免假完成
                if (
                    wf == Workflow.PLAN_EXECUTE
                    and iteration < max_iter
                    and plan_nudge_used < 2
                    and is_plan_announcement(
                        candidate,
                        agent_id=agent_def.id,
                        had_tool_calls=bool(result.tool_calls),
                    )
                ):
                    plan_nudge_used += 1
                    if emit_sse:
                        yield format_sse(
                            "thinking",
                            {
                                "content": (
                                    f"[纠正] 检测到仅宣布计划、未真正执行"
                                    f"（第 {plan_nudge_used} 次），要求继续…\n"
                                    f"{candidate[:500]}\n"
                                )
                            },
                        )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "上一段只是在复述/宣布计划或空承诺调度，对用户没有完成交付。"
                                "请立刻执行：要么调用 dispatch_agent（可一次多个）"
                                "调度计划中的专家；要么直接输出完整可用的 Markdown 答复。"
                                "禁止再只输出「执行计划」列表，"
                                "禁止「收到，这就调度…」这类不调工具的空承诺。"
                            ),
                        }
                    )
                    continue
                # 纠正次数用尽仍是空承诺：勿当作最终正文发出（避免前端假完成）
                if (
                    wf == Workflow.PLAN_EXECUTE
                    and is_plan_announcement(
                        candidate,
                        agent_id=agent_def.id,
                        had_tool_calls=bool(result.tool_calls),
                    )
                ):
                    if emit_sse:
                        yield format_sse(
                            "thinking",
                            {
                                "content": (
                                    "[纠正] 空承诺调度仍未执行，丢弃该段正文并继续重试…\n"
                                )
                            },
                        )
                    if iteration < max_iter:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "最后一次机会：必须调用 dispatch_agent 或写出完整 Markdown。"
                                    "禁止任何调度宣告句。"
                                ),
                            }
                        )
                        continue
                    final_text = (
                        "编排未完成：Hub 未能真正调度专家。"
                        "请重试，或换一种更具体的问法（例如「用 Mentor 讲解 CrewAI 入门路径」）。"
                    )
                    for _sse in _emit_text_deltas(final_text, emit_sse=emit_sse):
                        yield _sse
                    break
                if think and emit_sse:
                    yield format_sse("thinking", {"content": think + "\n"})
                final_text = candidate or result.text
                for _sse in _emit_text_deltas(final_text, emit_sse=emit_sse):
                    yield _sse
                break

            if not result.tool_calls:
                # 无工具调用且正文为空：不要在这里填弱占位并结束。
                # 弱占位会让 final_text 非空，从而跳过循环后的「强制无工具收口」，
                # 这是 Mentor/ToT 工具轮后空正文的主要失败路径。
                break

            # 处理工具调用
            question_payload = None
            for tc in result.tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                tc_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"

                if emit_sse:
                    yield format_sse(
                        "tool_call",
                        {
                            "call_id": tc_id,
                            "id": tc_id,
                            "name": name,
                            "status": "running",
                            "args": args,
                        },
                    )

                tool_result = await ctx.tool_registry.execute(name, args, ctx)

                # 反问拦截
                if isinstance(tool_result, dict) and tool_result.get("__question__"):
                    # 嵌入式导入助手等场景禁用反问面板 → 转成文字追问
                    if ctx.extra.get("disable_questions"):
                        q = _normalize_question(tool_result, agent_id=agent_def.id)
                        title = ""
                        intro = q.get("intro") or {}
                        if isinstance(intro, dict):
                            title = intro.get("content") or ""
                        qs = q.get("questions") or []
                        lines = [title or "想再确认几点："]
                        for item in qs[:5]:
                            if isinstance(item, dict):
                                lines.append(f"- {item.get('text') or item.get('prompt') or ''}")
                        text_q = "\n".join([ln for ln in lines if ln]).strip()
                        if emit_sse:
                            yield format_sse(
                                "tool_result",
                                {
                                    "call_id": tc_id,
                                    "id": tc_id,
                                    "name": name,
                                    "status": "success",
                                    "preview": "转为文字追问",
                                    "result": {"converted": True},
                                },
                            )
                            if text_q:
                                for _sse in _emit_text_deltas(
                                    text_q, emit_sse=emit_sse
                                ):
                                    yield _sse
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": json.dumps(
                                    {
                                        "ok": True,
                                        "message": "反问已转为文字，请直接用自然语言继续回答用户",
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        )
                        final_text = text_q
                        # 继续循环让模型基于「反问已转文字」生成完整答复
                        continue

                    question_payload = _normalize_question(
                        tool_result, agent_id=agent_def.id
                    )
                    if emit_sse:
                        yield format_sse(
                            "tool_result",
                            {
                                "call_id": tc_id,
                                "id": tc_id,
                                "name": name,
                                "status": "success",
                                "preview": "等待用户回答",
                                "result": {"status": "waiting_user"},
                            },
                        )
                        yield format_sse("question", question_payload)
                        # 有结构化反问面板时，不再追加 text_delta，避免前端出现
                        # 「弹窗 + 半截回复」叠在一起，以及后续轮次状态错乱
                        yield format_sse(
                            "done",
                            {
                                "usage": total_usage,
                                "iterations": iteration,
                                "agent_id": agent_def.id,
                                "pending_question": True,
                            },
                        )
                    # 持久化 pending 到 extra
                    ctx.extra["pending_question"] = question_payload
                    yield EngineResult(
                        text="",
                        agent_id=agent_def.id,
                        usage=total_usage,
                        iterations=iteration,
                        question=question_payload,
                        pending_status="pending_question",
                    )
                    yield ("__abort__",)
                    return

                # Hub 调度拦截
                if isinstance(tool_result, dict) and tool_result.get("__dispatch__"):
                    dispatches.append(tool_result)
                    if emit_sse:
                        yield format_sse(
                            "tool_result",
                            {
                                "call_id": tc_id,
                                "id": tc_id,
                                "name": name,
                                "status": "success",
                                "preview": f"调度 {tool_result.get('target_agent')}",
                                "result": tool_result,
                            },
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps(
                                {
                                    "ok": True,
                                    "message": f"已记录调度 {tool_result.get('target_agent')}",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                    continue

                # 会话项目上下文变更 → 前端刷新右栏
                if isinstance(tool_result, dict) and tool_result.get("__session_projects__"):
                    if emit_sse:
                        yield format_sse(
                            "tool_result",
                            {
                                "call_id": tc_id,
                                "id": tc_id,
                                "name": name,
                                "status": "success",
                                "preview": f"上下文项目 {tool_result.get('count', 0)} 个",
                                "result": tool_result,
                            },
                        )
                        yield format_sse(
                            "session_projects",
                            {
                                "project_ids": tool_result.get("project_ids") or [],
                                "action": tool_result.get("action") or "add",
                                "count": tool_result.get("count") or 0,
                            },
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps(
                                {
                                    "ok": True,
                                    "project_ids": tool_result.get("project_ids") or [],
                                    "message": "已更新会话项目上下文",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                    continue

                # 导入助手：勾选仓库（前端同步左侧 checkbox）
                if isinstance(tool_result, dict) and tool_result.get("__select_repos__"):
                    if emit_sse:
                        yield format_sse(
                            "tool_result",
                            {
                                "call_id": tc_id,
                                "id": tc_id,
                                "name": name,
                                "status": "success",
                                "preview": f"勾选 {tool_result.get('count', 0)} 个仓库",
                                "result": tool_result,
                            },
                        )
                        yield format_sse(
                            "select_repos",
                            {
                                "repo_keys": tool_result.get("repo_keys") or [],
                                "action": tool_result.get("action") or "set",
                                "reason": tool_result.get("reason") or "",
                                "count": tool_result.get("count") or 0,
                            },
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps(
                                {
                                    "ok": True,
                                    "selected": tool_result.get("repo_keys") or [],
                                    "message": "已在界面勾选，请用文字向用户说明清单",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                    continue

                preview = self._preview(tool_result)
                if emit_sse:
                    yield format_sse(
                        "tool_result",
                        {
                            "call_id": tc_id,
                            "id": tc_id,
                            "name": name,
                            "status": "success"
                            if not (
                                isinstance(tool_result, dict)
                                and tool_result.get("error")
                            )
                            else "error",
                            "preview": preview,
                            "result": tool_result
                            if self._small_enough(tool_result)
                            else {"preview": preview},
                        },
                    )
                # §4.2.4: 回灌给 LLM 的 tool 消息显式标注 ok/error，
                # 让 LLM 能区分成功 / 失败（之前 SSE 已 status 区分，但 messages 未携带）
                is_tool_error = isinstance(tool_result, dict) and bool(
                    tool_result.get("error")
                )
                tool_content = (
                    {"ok": False, "error": tool_result.get("error"), "tool": name}
                    if is_tool_error
                    else tool_result
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(
                            tool_content, ensure_ascii=False, default=str
                        )[: self.config.tool_result_truncate],
                    }
                )

            # 若本轮有 dispatch，结束循环让 Hub 外层编排
            if dispatches:
                # 让模型再生成一句说明，或直接结束
                if not final_text:
                    final_text = ""
                break

        # 若有 dispatch：正文预告由 Hub._handle_dispatches 发出，此处不占位
        if dispatches and not final_text:
            final_text = ""
        yield (final_text, dispatches, iteration)

    async def _run_closing_reply(
        self,
        *,
        llm: LLMProvider,
        messages: list[dict[str, Any]],
        agent_def: AgentDefinition,
        emit_sse: bool,
        total_usage: dict[str, int],
        final_text: str,
        dispatches: list[dict[str, Any]],
        iteration: int,
    ) -> AsyncIterator[str | EngineResult]:
        """收口：工具轮结束仍无正文且无 dispatch 时强制无工具再答一轮，最后 done + EngineResult。"""
        # 工具轮结束后仍无正文：强制无工具再答一轮（Mentor/ToT 常见只调工具不写正文）
        if not (final_text or "").strip() and not dispatches:
            if emit_sse:
                yield format_sse(
                    "thinking",
                    {
                        "content": (
                            f"[收口] {agent_def.name} 工具轮结束仍无正文，"
                            "改为直接生成分析…\n"
                        )
                    },
                )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "请停止调用任何工具，直接用中文输出完整分析正文（Markdown）。"
                        "基于上文已有的工具结果与项目上下文作答。"
                        "必须写完：完整句、完整列表与闭合括号；不要半截收尾。"
                        "不要 emoji，不要只写一句话敷衍。"
                    ),
                }
            )
            # 收口正文单独抬高 token 下限，避免专家 max_tokens 偏紧时半截截断
            close_tokens = max(
                int(agent_def.max_tokens or 0), self.config.closing_min_tokens
            )
            async for item in self._stream_plain_text(
                llm=llm,
                messages=messages,
                agent_def=agent_def,
                emit_sse=emit_sse,
                channel="text",
                max_tokens=close_tokens,
            ):
                if _is_stream_frame(item):
                    yield item
                else:
                    final_text = (item.text or "").strip()
                    for k in total_usage:
                        total_usage[k] = total_usage.get(k, 0) + (
                            item.usage or {}
                        ).get(k, 0)

            if not (final_text or "").strip():
                final_text = (
                    f"【{agent_def.name}】本轮未能生成分析正文。"
                    "可能是模型只调用了工具或返回为空；请重试，或先用 Scout 快速分析。"
                )
                for _sse in _emit_text_deltas(final_text, emit_sse=emit_sse):
                    yield _sse

        if emit_sse:
            yield format_sse(
                "done",
                {
                    "usage": {
                        "tokens": total_usage.get("total_tokens", 0),
                        **total_usage,
                    },
                    "iterations": iteration,
                    "agent_id": agent_def.id,
                },
            )

        yield EngineResult(
            text=final_text,
            agent_id=agent_def.id,
            usage=total_usage,
            iterations=iteration,
            dispatches=dispatches,
        )

    def _preview(self, result: Any, limit: int | None = None) -> str:
        limit = limit or self.config.preview_limit
        try:
            s = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            s = str(result)
        return s[:limit]

    def _small_enough(self, result: Any, limit: int | None = None) -> bool:
        limit = limit or self.config.tool_result_sse_limit
        try:
            return len(json.dumps(result, default=str)) < limit
        except Exception:
            return False

    def _workflow_hint(self, agent_def: AgentDefinition) -> str:
        wf = Workflow((agent_def.workflow or "react").lower())
        return _WORKFLOW_HINTS.get(wf, _WORKFLOW_HINTS[Workflow.REACT])

    def _degraded_reply(
        self, agent_def: AgentDefinition, messages: list[dict[str, Any]]
    ) -> str:
        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
        last = user_msgs[-1] if user_msgs else ""
        return (
            f"【降级模式 · {agent_def.name}】未配置 LLM API Key。\n\n"
            f"已收到：{last[:300]}\n\n"
            "系统将仅使用规则/图谱/GitHub 公开数据能力。"
            "请前往设置页配置 BYOK API Key 以启用完整多 Agent 推理。"
        )


# 工作流提示文案查表（消除 _workflow_hint 的 if 链）
_WORKFLOW_HINTS: dict[Workflow, str] = {
    Workflow.COT: (
        "工作流: Chain-of-Thought（快速）。"
        "直接基于已有上下文给出答案，优先速度与信息密度；"
        "不要假装调用工具，不要输出 emoji；"
        "不要向用户复述内部规则或工具清单。"
    ),
    Workflow.DIRECT: (
        "工作流: Chain-of-Thought（快速）。"
        "直接基于已有上下文给出答案，优先速度与信息密度；"
        "不要假装调用工具，不要输出 emoji；"
        "不要向用户复述内部规则或工具清单。"
    ),
    Workflow.PLAN_EXECUTE: (
        "工作流: Plan-and-Execute。规划只在思考区；执行阶段必须真正行动："
        "需要专家时调用 dispatch_agent，可直接答则写完整 Markdown 正文。"
        "禁止把「执行计划」列表当作最终答复；"
        "禁止「收到/好的，这就调度某某」这类不调工具的空承诺。"
        "不要一次调度超过 3 个 Agent。禁止 emoji。"
    ),
    Workflow.REFLEXION: (
        "工作流: Reflexion。提出方案 → 自我评估（重复/命名/过细）→ 反思改进，"
        "最多 2 轮，最终给出建议。禁止 emoji。"
    ),
    Workflow.TOT: (
        "工作流: Tree-of-Thoughts。对复杂问题在内部比较 2-3 种路径，"
        "只展开最适合用户的一种；输出最终讲解即可。禁止 emoji。"
    ),
    Workflow.REACT: (
        "工作流: ReAct。需要数据时先调用工具再回答；"
        "能直接答则不要硬调工具。禁止 emoji。"
    ),
}


_PLAN_HEADER_RE = re.compile(
    r"(?m)^\s*(执行计划|行动计划|计划步骤)\s*[:：]?",
)
_DISPATCH_HINT_RE = re.compile(
    r"(调度|分派|dispatch).{0,24}(mentor|curator|navigator|scout|scribe|atlas)",
    re.IGNORECASE,
)
_PLAN_ANNOUNCE_RE = re.compile(
    r"(开始分派|开始执行|现开始|接下来将调度|正在调度|这就调度|这就分派|"
    r"马上调度|立即调度|我来调度|先调度|待\s*\d+\s*位专家)",
)
# 「无需再调度 mentor」等收口句，不是空承诺
_DISPATCH_NEGATION_RE = re.compile(
    r"(无需|不用|不必|不再|无须).{0,8}(调度|分派)",
)
# 有实质交付结构时，不因提到「调度」就当空承诺
_DELIVERY_STRUCTURE_RE = re.compile(
    r"(?m)^#{1,3}\s|\n[-*]\s+\S|```|\|.+\|",
)


# §4.2.7: is_plan_announcement 长度阈值（魔数收敛）
_HUB_LONG_PLAN_MAX_CHARS = 1200        # Hub 长计划 + 多 dispatch 视为实交付
_ANNOUNCE_PLAN_MAX_CHARS = 800        # 含 "执行计划/收到" 等关键词的短上限
_HUB_SHORT_HINT_MAX_CHARS = 280      # Hub 单次提到调度但无交付结构的极短空承诺



def is_plan_announcement(
    text: str, *, agent_id: str = "", had_tool_calls: bool = False
) -> bool:
    """判断正文是否像「宣布执行计划」而非用户可见的完整交付。

    Hub 在 plan_execute 下常输出「执行计划：1.调度 mentor…」或
    「收到，这就调度 Mentor…」后直接结束，前端会停在第 1 轮，看起来像卡住。
    had_tool_calls=True（本轮已真正调用工具）时直接判定为实交付，正则只作辅助。
    """
    # 主信号：本轮调了工具就不是空承诺
    if had_tool_calls:
        return False
    t = (text or "").strip()
    if len(t) < 12:
        return False
    has_header = bool(_PLAN_HEADER_RE.search(t)) or t.startswith(
        ("执行计划", "行动计划", "计划步骤")
    )
    dispatch_hits = len(_DISPATCH_HINT_RE.findall(t))
    announce = bool(_PLAN_ANNOUNCE_RE.search(t))
    if has_header and (dispatch_hits >= 1 or announce):
        return True
    if agent_id == "hub" and dispatch_hits >= 2 and len(t) < _HUB_LONG_PLAN_MAX_CHARS:
        return True
    if announce and dispatch_hits >= 1 and len(t) < _ANNOUNCE_PLAN_MAX_CHARS:
        return True
    # Hub 短空承诺：提到要调度专家，但几乎无交付结构（用户可见的「卡住」主因）
    if (
        agent_id == "hub"
        and dispatch_hits >= 1
        and len(t) < _HUB_SHORT_HINT_MAX_CHARS
        and not _DISPATCH_NEGATION_RE.search(t)
        and not _DELIVERY_STRUCTURE_RE.search(t)
    ):
        return True
    return False


