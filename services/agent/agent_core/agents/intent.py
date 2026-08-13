"""意图分类 —— 规则 + 多意图 + LLM"""
from __future__ import annotations

import json
import logging
import os  # §4.2.8 多意图关键词 env 覆盖
import re
from dataclasses import dataclass, field
from typing import Any

from agent_core.agents.registry import get_registry
from agent_core.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# 规则优先级：同一条消息命中多个 Agent 时靠前的优先（与历史行为保持一致）。
# 正则本体收敛在 AgentDefinition.intent_patterns，此处只声明顺序。
_FAST_RULE_ORDER = ("scout", "navigator", "mentor", "curator", "scribe", "atlas")


def _derive_fast_rules() -> list[tuple[re.Pattern[str], str]]:
    """从 AgentDefinition.intent_patterns 派生意图规则（加 Agent 只需补注册表）。"""
    reg = get_registry()
    rules: list[tuple[re.Pattern[str], str]] = []
    for agent_id in _FAST_RULE_ORDER:
        try:
            agent_def = reg.get(agent_id)
        except KeyError:
            continue
        for p in agent_def.intent_patterns:
            rules.append((p, agent_id))
    return rules


@dataclass
class SubIntent:
    agent_id: str
    message: str
    reason: str


@dataclass
class IntentResult:
    agent_id: str
    confidence: float
    is_multi: bool = False
    sub_intents: list[SubIntent] = field(default_factory=list)
    plan_summary: str = ""


class IntentClassifier:
    """Hub 意图识别。"""

    FAST_RULES: list[tuple[re.Pattern[str], str]] = _derive_fast_rules()

    # §4.2.8: 多意图连接词；可经 INTENT_KEYWORDS 环境变量覆盖（逗号分隔）
    _BASE_MULTI_KEYWORDS = ("并且", "同时", "另外", "还有", "以及", "并帮我", "再帮我", "然后")
    MULTI_KEYWORDS = list(_BASE_MULTI_KEYWORDS)
    _OVERRIDE_KW = os.environ.get("INTENT_KEYWORDS")
    if _OVERRIDE_KW:
        MULTI_KEYWORDS = [k.strip() for k in _OVERRIDE_KW.split(",") if k.strip()]

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm

    @staticmethod
    def _split_segments(message: str, keywords: list[str]) -> list[str]:
        """按多意图连接词切分子句（先按最长关键词切，避免「并帮我」被「并」截断）。"""
        kws = sorted(keywords, key=len, reverse=True)
        pattern = re.compile("(" + "|".join(re.escape(k) for k in kws) + ")")
        parts = pattern.split(message)
        segments: list[str] = []
        buf = ""
        for i, part in enumerate(parts):
            if i % 2 == 0:
                buf += part
            else:
                # 遇到连接词：收口当前段（连接词本身丢弃）
                if buf.strip():
                    segments.append(buf)
                buf = ""
        if buf.strip():
            segments.append(buf)
        return segments

    async def classify(
        self, message: str, context: dict[str, Any] | None = None
    ) -> IntentResult:
        msg = (message or "").strip()
        if not msg:
            return IntentResult(agent_id="hub", confidence=1.0)

        # 多意图
        multi = self._rule_multi(msg)
        if multi:
            return IntentResult(
                agent_id="hub",
                confidence=0.85,
                is_multi=True,
                sub_intents=multi,
                plan_summary=" → ".join(s.agent_id for s in multi),
            )

        # 快速规则
        for pattern, agent_id in self.FAST_RULES:
            if pattern.search(msg):
                return IntentResult(agent_id=agent_id, confidence=0.9)

        # LLM 分类
        if self.llm and self.llm.available:
            try:
                return await self._llm_classify(msg, context)
            except (json.JSONDecodeError, ValueError, RuntimeError) as e:
                # complete_json 失败已记日志并兜底 {}；此处捕获解析/类型异常，回退规则
                logger.warning("LLM classify failed, fallback to hub: %s", e)

        return IntentResult(agent_id="hub", confidence=0.5)

    def _rule_multi(self, message: str) -> list[SubIntent] | None:
        if not any(kw in message for kw in self.MULTI_KEYWORDS):
            return None
        # 按连接词切分后逐段匹配：每个 sub_intent 带对应子句，
        # 专家能区分自己该处理哪部分（而非整句原文）
        segments = self._split_segments(message, self.MULTI_KEYWORDS)
        hits: list[SubIntent] = []
        for segment in segments:
            seg = segment.strip()
            if not seg:
                continue
            for pattern, agent_id in self.FAST_RULES:
                if pattern.search(seg):
                    hits.append(
                        SubIntent(
                            agent_id=agent_id,
                            message=seg,
                            reason=f"规则匹配 {agent_id}",
                        )
                    )
                    break  # 每段只取第一个命中
        # 去重 agent
        seen = set()
        unique: list[SubIntent] = []
        for h in hits:
            if h.agent_id not in seen and h.agent_id != "hub":
                seen.add(h.agent_id)
                unique.append(h)
        return unique if len(unique) >= 2 else None

    async def _llm_classify(
        self, message: str, context: dict[str, Any] | None
    ) -> IntentResult:
        assert self.llm is not None
        # agent 列表动态生成：注册表加 Agent 后 LLM 分类自动适配
        agents = ", ".join(
            f"{d.id}({d.description})"
            for d in get_registry().list_all()
            if d.id != "hub"
        )
        prompt = (
            "判断用户消息应由哪个 Agent 处理。只返回 JSON。\n"
            f"可选: {agents}。\n"
            f"用户消息: {message}\n"
            '格式: {"agent_id":"...","confidence":0.0,"is_multi":false,'
            '"sub_intents":[{"agent_id":"...","message":"...","reason":"..."}]}'
        )
        data = await self.llm.complete_json(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400,
        )
        agent_id = data.get("agent_id") or "hub"
        conf = float(data.get("confidence") or 0.6)
        sub_raw = data.get("sub_intents") or []
        subs = [
            SubIntent(
                agent_id=s.get("agent_id", "hub"),
                message=s.get("message", message),
                reason=s.get("reason", ""),
            )
            for s in sub_raw
            if isinstance(s, dict)
        ]
        is_multi = bool(data.get("is_multi")) and len(subs) >= 2
        return IntentResult(
            agent_id=agent_id,
            confidence=conf,
            is_multi=is_multi,
            sub_intents=subs,
        )
