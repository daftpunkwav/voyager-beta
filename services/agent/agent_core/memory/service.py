"""记忆系统 —— 短期/长期/画像提案与合并"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from py_shared.models.agent import AgentMessage, AgentSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_core import services as _agent_svc

logger = logging.getLogger(__name__)

# 允许写入偏好画像的键白名单：拒绝 LLM/用户输入中的任意 key 合并（如 {"admin": true}）
ALLOWED_PREF_KEYS = {"tech_stack", "level", "language", "goal", "speaking_style"}


class MemoryService:
    """Agent 记忆读写与合并。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_session(self, session_id: UUID) -> AgentSession | None:
        return await self.db.get(AgentSession, session_id)

    async def list_recent_messages(
        self, session_id: UUID, limit: int = 30
    ) -> list[AgentMessage]:
        result = await self.db.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.desc())
            .limit(limit)
        )
        msgs = list(result.scalars().all())
        msgs.reverse()
        return msgs

    async def get_user_profile_dict(self) -> dict[str, Any]:
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        out = _agent_svc.profile().profile_to_out(row)
        return out.model_dump()

    async def get_short_memory(self, agent_id: str) -> list[dict]:
        """Agent 私有短期记忆（存于 user_profiles.agent_prefs）。"""
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        short = prefs.get("short_memory", {})
        if not isinstance(short, dict):
            return []
        items = short.get(agent_id, [])
        return items if isinstance(items, list) else []

    async def append_short_memory(
        self, agent_id: str, entry: dict[str, Any], max_items: int = 12
    ) -> None:
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        short = prefs.setdefault("short_memory", {})
        if not isinstance(short, dict):
            short = {}
            prefs["short_memory"] = short
        items = list(short.get(agent_id) or [])
        items.append({**entry, "at": datetime.utcnow().isoformat() + "Z"})
        short[agent_id] = items[-max_items:]
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
        await self.db.commit()

    async def get_long_memory(self) -> list[dict]:
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        items = prefs.get("memory_items", []) if isinstance(prefs, dict) else []
        return items if isinstance(items, list) else []

    async def propose_memory(
        self,
        *,
        agent_id: str,
        value: str,
        confidence: float,
        evidence: list[str] | None = None,
        kind: str = "long_memory",
        apply: bool = False,
    ) -> dict[str, Any]:
        """
        Agent 提交记忆提案。

        - apply=False（默认，工具路径）：仅写入 pending，需用户确认后才合并。
        - apply=True（用户显式反问答案等）：立即合并。
        """
        import uuid as _uuid

        raw_value = str(value or "").strip()[:2000]
        proposal = {
            "id": f"prop_{_uuid.uuid4().hex[:12]}",
            "value": raw_value,
            "confidence": max(0.0, min(1.0, confidence)),
            "evidence": (evidence or [])[:8],
            "agent_id": agent_id,
            "kind": kind,
            "at": datetime.utcnow().isoformat() + "Z",
        }
        if not raw_value:
            return {**proposal, "status": "rejected", "applied": False, "error": "empty"}

        if not apply:
            await self._enqueue_pending_proposal(proposal)
            return {**proposal, "status": "pending", "applied": False}

        await self._apply_proposal(proposal)
        return {**proposal, "status": "applied", "applied": True}

    async def _enqueue_pending_proposal(
        self, proposal: dict[str, Any]
    ) -> None:
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        pending: list[dict] = list(prefs.get("pending_memory_proposals") or [])
        # 同内容去重：保留最新
        value = proposal["value"]
        pending = [
            p
            for p in pending
            if not (isinstance(p, dict) and str(p.get("value") or "") == value)
        ]
        pending.append(proposal)
        prefs["pending_memory_proposals"] = pending[-20:]
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
        await self.db.commit()

    async def accept_memory_proposal(
        self, proposal_id: str
    ) -> dict[str, Any]:
        """用户确认后合并提案。"""
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        pending: list[dict] = list(prefs.get("pending_memory_proposals") or [])
        found: dict | None = None
        rest: list[dict] = []
        for p in pending:
            if isinstance(p, dict) and str(p.get("id")) == proposal_id:
                found = p
            elif isinstance(p, dict):
                rest.append(p)
        if not found:
            return {"ok": False, "error": "提案不存在或已处理"}
        prefs["pending_memory_proposals"] = rest
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
        await self.db.commit()
        await self._apply_proposal(found)
        return {"ok": True, "applied": True, "proposal": found}

    async def reject_memory_proposal(
        self, proposal_id: str
    ) -> dict[str, Any]:
        """用户拒绝提案。"""
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        pending: list[dict] = list(prefs.get("pending_memory_proposals") or [])
        new_pending = [
            p
            for p in pending
            if not (isinstance(p, dict) and str(p.get("id")) == proposal_id)
        ]
        if len(new_pending) == len(pending):
            return {"ok": False, "error": "提案不存在或已处理"}
        prefs["pending_memory_proposals"] = new_pending
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
        await self.db.commit()
        return {"ok": True, "applied": False}

    async def _apply_proposal(self, proposal: dict[str, Any]) -> None:
        kind = str(proposal.get("kind") or "long_memory")
        if kind == "long_memory":
            await self._merge_long_memory(proposal)
        elif kind == "profile_tech":
            await self._merge_tech_profile(proposal)
        elif kind == "preference":
            await self._merge_preference(proposal)

    async def _merge_long_memory(self, proposal: dict) -> None:
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs = self._parse(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        items: list[dict] = list(prefs.get("memory_items") or [])
        value = str(proposal["value"]).strip()
        # 冲突检测：语义近似用子串/相等
        for existing in items:
            if not isinstance(existing, dict):
                continue
            ev = str(existing.get("content") or existing.get("value") or "")
            if ev == value or value in ev or ev in value:
                # 保留高置信度
                old_c = float(existing.get("confidence", 0.5))
                if proposal["confidence"] >= old_c:
                    existing["content"] = value
                    existing["confidence"] = proposal["confidence"]
                    existing["source_agent"] = proposal["agent_id"]
                    existing["updated_at"] = proposal["at"]
                row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
                await self.db.commit()
                return
        items.append(
            {
                "id": f"mem_{len(items)+1}_{int(datetime.utcnow().timestamp())}",
                "category": "summary",
                "content": value,
                "confidence": proposal["confidence"],
                "source_agent": proposal["agent_id"],
                "evidence": proposal.get("evidence", []),
                "created_at": proposal["at"],
            }
        )
        # 上限 100 条
        prefs["memory_items"] = items[-100:]
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
        # 同步 history_summary 摘要
        if not row.history_summary:
            row.history_summary = value[:200]
        await self.db.commit()

    async def _merge_tech_profile(self, proposal: dict) -> None:
        """技术熟练度：证据加权，并同步到侧栏 tech memory_items。"""
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        tech = self._parse(row.tech_profile, {})
        if not isinstance(tech, dict):
            tech = {}
        # value 格式: "Python:80" 或 JSON
        value = proposal["value"]
        conf = proposal["confidence"]
        try:
            if value.strip().startswith("{"):
                patch = json.loads(value)
            elif ":" in value:
                k, v = value.split(":", 1)
                patch = {k.strip(): float(v.strip())}
            else:
                return
        except (ValueError, json.JSONDecodeError):
            return
        for k, v in patch.items():
            old = float(tech.get(k, 50))
            # 加权平均：新证据 * conf + 旧值 * (1-conf)
            tech[k] = round(old * (1 - conf) + float(v) * conf, 1)
        row.tech_profile = json.dumps(tech, ensure_ascii=False)

        # 同步到 memory_items（category=tech），供侧栏展示
        prefs = self._parse(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        items: list[dict] = list(prefs.get("memory_items") or [])
        for k, score in tech.items():
            content = f"{k}: {score}"
            found = False
            for existing in items:
                if not isinstance(existing, dict):
                    continue
                if existing.get("category") == "tech" and str(
                    existing.get("content", "")
                ).startswith(f"{k}:"):
                    existing["content"] = content
                    existing["confidence"] = conf
                    existing["updated_at"] = proposal["at"]
                    found = True
                    break
            if not found:
                items.append(
                    {
                        "id": f"tech_{k}_{int(datetime.utcnow().timestamp())}",
                        "category": "tech",
                        "content": content,
                        "confidence": conf,
                        "source_agent": proposal["agent_id"],
                        "created_at": proposal["at"],
                    }
                )
        prefs["memory_items"] = items[-100:]
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
        await self.db.commit()

    async def _merge_preference(self, proposal: dict) -> None:
        row = await _agent_svc.profile().get_or_create_profile(self.db)
        prefs_data = self._parse(row.preferences, {})
        if not isinstance(prefs_data, dict):
            prefs_data = {}
        value = str(proposal.get("value") or "").strip()
        if not value:
            return

        # 拒绝把答题 JSON / ask_user 结构直接塞进偏好
        readable = self._preference_readable(value)
        if readable is None:
            return

        try:
            if value.startswith("{") and '"type"' not in value[:80]:
                parsed = json.loads(value)
                if isinstance(parsed, dict) and not self._looks_like_answer_dump(parsed):
                    # 白名单合并：拒绝任意 key 写进偏好画像
                    for k, v in parsed.items():
                        if k in ALLOWED_PREF_KEYS:
                            prefs_data[k] = v
                        else:
                            logger.warning("rejected unknown pref key: %s", k)
                else:
                    prefs_data["note"] = readable
            elif ":" in value and not value.startswith("{"):
                k, v = value.split(":", 1)
                k = k.strip()
                if k in ALLOWED_PREF_KEYS:
                    prefs_data[k] = v.strip()
                else:
                    logger.warning("rejected unknown pref key: %s", k)
            else:
                prefs_data["note"] = readable
        except json.JSONDecodeError:
            prefs_data["note"] = readable
        row.preferences = json.dumps(prefs_data, ensure_ascii=False)

        # 同步偏好词条到侧栏（只存可读文案）
        agent_prefs = self._parse(row.agent_prefs, {})
        if not isinstance(agent_prefs, dict):
            agent_prefs = {}
        items: list[dict] = list(agent_prefs.get("memory_items") or [])
        content = readable[:500]
        if not any(
            isinstance(m, dict)
            and m.get("category") == "preference"
            and m.get("content") == content
            for m in items
        ):
            items.append(
                {
                    "id": f"pref_{int(datetime.utcnow().timestamp())}",
                    "category": "preference",
                    "content": content,
                    "confidence": proposal["confidence"],
                    "source_agent": proposal["agent_id"],
                    "created_at": proposal["at"],
                }
            )
            agent_prefs["memory_items"] = items[-100:]
            row.agent_prefs = json.dumps(agent_prefs, ensure_ascii=False)
        await self.db.commit()

    @staticmethod
    def _looks_like_answer_dump(obj: dict) -> bool:
        """判断是否为答题结果 / ask_user 结构，不应作为偏好原文。"""
        if "items" in obj or "questions" in obj or "question_id" in obj:
            return True
        vals = list(obj.values())
        if not vals:
            return False
        sample = vals[0]
        return isinstance(sample, dict) and "type" in sample and (
            "value" in sample or "values" in sample
        )

    @classmethod
    def _preference_readable(cls, value: str) -> str | None:
        """把偏好提案转成侧栏可读短句；无法识别的答题 JSON 则丢弃。"""
        t = value.strip()
        if not t:
            return None
        if t.startswith("{") or t.startswith("["):
            try:
                parsed = json.loads(t)
            except json.JSONDecodeError:
                return t[:200]
            if isinstance(parsed, dict) and cls._looks_like_answer_dump(parsed):
                # 尽量抽几条 value 做成摘要，而不是整段 JSON
                bits: list[str] = []
                for v in parsed.values():
                    if isinstance(v, dict):
                        label = v.get("other_text") or v.get("value") or v.get("values")
                        if isinstance(label, list):
                            bits.append("、".join(str(x) for x in label[:3]))
                        elif label:
                            bits.append(str(label))
                    elif isinstance(v, (str, int, float)):
                        bits.append(str(v))
                    if len(bits) >= 3:
                        break
                if bits:
                    return "答题偏好 · " + " · ".join(bits)
                return None
            if isinstance(parsed, dict):
                # 普通偏好 dict → key: value 摘要
                parts = [f"{k}: {v}" for k, v in list(parsed.items())[:4]]
                return "；".join(parts) if parts else None
        return t[:200]
    async def compress_history_if_needed(
        self,
        messages: list[dict[str, Any]],
        *,
        max_messages: int = 24,
        keep_recent: int = 12,
    ) -> list[dict[str, Any]]:
        """简单上下文压缩：保留 system + 最近 N 条，中间摘要。"""
        if len(messages) <= max_messages:
            return messages
        system = [m for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        if len(rest) <= keep_recent:
            return messages
        old = rest[:-keep_recent]
        recent = rest[-keep_recent:]
        summary_parts = []
        for m in old:
            role = m.get("role", "?")
            content = (m.get("content") or "")[:400]
            if content:
                summary_parts.append(f"{role}: {content}")
        summary = {
            "role": "system",
            "content": "[历史对话摘要]\n" + "\n".join(summary_parts[-20:]),
        }
        return system + [summary] + recent

    @staticmethod
    def _parse(text: str | None, fallback: Any) -> Any:
        try:
            value = json.loads(text or "")
            return value if isinstance(value, (dict, list)) else fallback
        except json.JSONDecodeError:
            return fallback

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """粗略 token 估计：中文约 1.5 字/token，英文约 4 字符/token。"""
        if not text:
            return 0
        # 混合估算
        return max(1, len(text) // 3)
