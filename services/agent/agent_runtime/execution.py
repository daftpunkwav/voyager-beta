"""Agent 执行逻辑：会话流控 / SSE 编排 / 持久化副作用（阶段 4 从 api_backend.agent_service 迁入）。

依赖方向：本模块（agent_runtime）依赖 agent_core 与 api_backend 的业务模块；
api_backend 只经 agent_service re-export 壳或 AgentRuntimeInterface 调用，不再直接 import。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import UUID

from agent_core.agents.hub import HubService
from agent_core.agents.stream_events import StreamEvent, encode_stream_item, format_sse
from agent_core.llm.config import build_llm_config_from_user
from agent_core.memory.service import MemoryService
from agent_core.tools.builtin import ensure_tools_loaded
from api_backend.core import stream_cancel
from api_backend.models.agent import AgentMessage, AgentSession, agent_session_projects
from api_backend.schemas.agent import (
    AgentMessageOut,
    AgentSessionDetailOut,
    AgentSessionOut,
    ContextWindowSegmentOut,
    ContextWindowStatsOut,
)
from api_backend.services.project_service import get_project
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ensure_tools_loaded()

# 会话级流控：同 session 新流会 set 旧 Event，旧流停止 yield 与最终落库
_session_stream_cancel: dict[UUID, asyncio.Event] = {}

# 单会话最多绑定项目数，避免上下文膨胀
MAX_SESSION_PROJECTS = 8


def _begin_session_stream(session_id: UUID) -> asyncio.Event:
    prev = _session_stream_cancel.get(session_id)
    if prev is not None:
        prev.set()
    ev = asyncio.Event()
    _session_stream_cancel[session_id] = ev
    return ev


def _end_session_stream(session_id: UUID, ev: asyncio.Event) -> None:
    if _session_stream_cancel.get(session_id) is ev:
        _session_stream_cancel.pop(session_id, None)


async def _begin_session_cancel_token(
    db: AsyncSession, session_id: UUID
) -> str:
    """在 Event 之上叠加跨 worker token；返回本次流的 token。

    调用后端会刷新 agent_session_cancel_tokens 表中同 session 的 token；
    任何其他 worker / 协程若再调用 begin 就会让本 token 失效。
    """
    return await stream_cancel.begin(db, session_id)


async def _is_session_cancel_observed(
    db: AsyncSession,
    session_id: UUID,
    my_token: str,
    local_ev: asyncio.Event,
) -> bool:
    """跨 worker 取消判定：本地 Event 被 set 或 DB 中 token 已变更均视为取消。

    注意：DB 轮询存在刷新窗口，建议每 8-16 个 chunk 调用一次。
    """
    if local_ev.is_set():
        return True
    return await stream_cancel.poll(db, session_id, my_token)


async def _end_session_cancel_token(
    db: AsyncSession, session_id: UUID, my_token: str
) -> None:
    await stream_cancel.clear(db, session_id, my_token)


async def get_session_project_ids(db: AsyncSession, session_id: UUID) -> list[UUID]:
    """读取会话绑定的全部项目 ID；无关联表数据时回退到 session.project_id。"""
    rows = (
        await db.execute(
            select(agent_session_projects.c.project_id).where(
                agent_session_projects.c.session_id == session_id
            )
        )
    ).scalars().all()
    ids = list(rows)
    if ids:
        return ids
    session = await db.get(AgentSession, session_id)
    if session and session.project_id:
        return [session.project_id]
    return []


async def set_session_projects(
    db: AsyncSession,
    session: AgentSession,
    project_ids: list[UUID],
) -> list[UUID]:
    """整体替换会话项目绑定；校验归属；同步主 project_id。"""
    # 去重保序
    seen: set[UUID] = set()
    unique: list[UUID] = []
    for pid in project_ids:
        if pid in seen:
            continue
        seen.add(pid)
        unique.append(pid)
    unique = unique[:MAX_SESSION_PROJECTS]

    owned: list[UUID] = []
    for pid in unique:
        p = await get_project(db, pid)
        if not p:
            raise ValueError("PROJECT_NOT_OWNED")
        owned.append(pid)

    await db.execute(
        delete(agent_session_projects).where(
            agent_session_projects.c.session_id == session.id
        )
    )
    if owned:
        from sqlalchemy import insert as sa_insert

        await db.execute(
            sa_insert(agent_session_projects),
            [{"session_id": session.id, "project_id": pid} for pid in owned],
        )
    session.project_id = owned[0] if owned else None
    return owned


async def add_session_project(
    db: AsyncSession, session: AgentSession, project_id: UUID
) -> list[UUID]:
    current = await get_session_project_ids(db, session.id)
    if project_id not in current:
        current.append(project_id)
    return await set_session_projects(db, session, current)


async def remove_session_project(
    db: AsyncSession, session: AgentSession, project_id: UUID
) -> list[UUID]:
    current = [p for p in await get_session_project_ids(db, session.id) if p != project_id]
    return await set_session_projects(db, session, current)


async def session_to_out(db: AsyncSession, session: AgentSession) -> AgentSessionOut:
    project_ids = await get_session_project_ids(db, session.id)
    source = (session.source or "chat").strip().lower() or "chat"
    return AgentSessionOut(
        id=session.id,
        title=session.title or "新对话",
        agent=session.active_agent or "hub",
        updated_at=(session.updated_at or session.created_at).isoformat() + "Z",
        unread=False,
        project_id=session.project_id or (project_ids[0] if project_ids else None),
        project_ids=project_ids,
        source=source,
    )


def message_to_out(msg: AgentMessage) -> AgentMessageOut:
    meta: dict = {}
    if msg.message_meta:
        try:
            parsed = json.loads(msg.message_meta)
            if isinstance(parsed, dict):
                meta = parsed
        except (json.JSONDecodeError, TypeError):
            meta = {}

    question = meta.get("question") if isinstance(meta.get("question"), dict) else None
    question_answer = (
        meta.get("question_answer")
        if isinstance(meta.get("question_answer"), dict)
        else None
    )
    # 兼容：content_type=question 时整份 metadata 即 AgentQuestion
    if not question and (msg.content_type == "question" or meta.get("question_id")):
        if meta.get("question_id") and meta.get("questions"):
            question = meta

    thinking_raw = meta.get("thinking")
    thinking = (
        thinking_raw.strip()
        if isinstance(thinking_raw, str) and thinking_raw.strip()
        else None
    )
    tool_calls = meta.get("tool_calls")
    if not isinstance(tool_calls, list):
        tool_calls = None
    subagents = meta.get("subagents")
    if not isinstance(subagents, list):
        subagents = None

    return AgentMessageOut(
        id=msg.id,
        session_id=msg.session_id,
        agent=msg.agent_id or "hub",
        role=msg.role,
        content=msg.content,
        content_type=msg.content_type or "text",
        thinking=thinking,
        tool_calls=tool_calls,
        subagents=subagents,
        question=question,
        question_answer=question_answer,
        created_at=msg.created_at.isoformat() + "Z",
    )


async def list_sessions(db: AsyncSession) -> list[AgentSessionOut]:
    result = await db.execute(
        select(AgentSession).order_by(AgentSession.updated_at.desc())
    )
    sessions = list(result.scalars().all())
    return [await session_to_out(db, s) for s in sessions]


async def get_session_detail(
    db: AsyncSession, session_id: UUID
) -> AgentSessionDetailOut | None:
    session = await db.get(AgentSession, session_id)
    if not session:
        return None
    msgs = (
        await db.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.asc())
        )
    ).scalars().all()
    base = await session_to_out(db, session)
    return AgentSessionDetailOut(
        **base.model_dump(),
        messages=[message_to_out(m) for m in msgs],
    )


async def create_session(
    db: AsyncSession,
    *,
    project_id: UUID | None = None,
    project_ids: list[UUID] | None = None,
    title: str = "新对话",
    source: str = "chat",
) -> AgentSessionOut:
    session = AgentSession(
                title=title,
        active_agent="hub",
        project_id=None,
        source=source or "chat",
    )
    db.add(session)
    await db.flush()
    ids = list(project_ids or [])
    if project_id and project_id not in ids:
        ids.insert(0, project_id)
    if ids:
        await set_session_projects(db, session, ids)
    await db.commit()
    await db.refresh(session)
    return await session_to_out(db, session)


async def update_session(
    db: AsyncSession,
    session_id: UUID,
    *,
    title: str | None = None,
    project_id: UUID | None = None,
    project_ids: list[UUID] | None = None,
    clear_project: bool = False,
    active_agent: str | None = None,
) -> AgentSessionOut | None:
    """更新会话。返回 None 表示会话不存在；非法字段抛 ValueError。"""
    from agent_core.agents.registry import AGENT_DEFINITIONS

    session = await db.get(AgentSession, session_id)
    if not session:
        return None
    if title is not None:
        session.title = title
    if clear_project:
        await set_session_projects(db, session, [])
    elif project_ids is not None:
        await set_session_projects(db, session, project_ids)
    elif project_id is not None:
        # 单项目替换：兼容旧前端点击绑定
        await set_session_projects(db, session, [project_id])
    if active_agent is not None:
        agent_id = active_agent.strip().lower()
        if agent_id not in AGENT_DEFINITIONS:
            raise ValueError("INVALID_ACTIVE_AGENT")
        session.active_agent = agent_id
    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return await session_to_out(db, session)


async def delete_session(db: AsyncSession, session_id: UUID) -> bool:
    session = await db.get(AgentSession, session_id)
    if not session:
        return False
    await db.execute(
        delete(agent_session_projects).where(
            agent_session_projects.c.session_id == session_id
        )
    )
    msgs = await db.execute(
        select(AgentMessage).where(AgentMessage.session_id == session_id)
    )
    for msg in msgs.scalars().all():
        await db.delete(msg)
    await db.delete(session)
    await db.commit()
    return True


async def append_message(
    db: AsyncSession,
    session: AgentSession,
    *,
    role: str,
    content: str,
    agent_id: str | None = None,
    content_type: str = "text",
    metadata: dict | None = None,
) -> AgentMessage:
    msg = AgentMessage(
        session_id=session.id,
        role=role,
        agent_id=agent_id or session.active_agent or "hub",
        content=content,
        content_type=content_type,
        message_meta=json.dumps(metadata or {}, ensure_ascii=False),
    )
    db.add(msg)
    session.updated_at = datetime.utcnow()
    if role == "user" and (not session.title or session.title == "新对话"):
        session.title = content[:32] + ("…" if len(content) > 32 else "")
    await db.commit()
    await db.refresh(msg)
    return msg


# 单段思考落库上限，避免 metadata 膨胀
_THINKING_META_MAX = 24000


class _AgentSegmentBuffer:
    """按 agent_switch 分段收集 text_delta / thinking，各自落库为独立 assistant 气泡。"""

    def __init__(self, *, agent_id: str = "hub"):
        self.parts: list[str] = []
        self.think_parts: list[str] = []
        self.agent_id = agent_id
        self.usage: dict[str, Any] = {}
        self.flushed = False
        self.tool_calls: dict[str, dict[str, Any]] = {}
        self.subagents: dict[str, dict[str, Any]] = {}

    def append_delta(self, content: str) -> None:
        if content:
            self.parts.append(content)

    def append_thinking(self, content: str) -> None:
        if content:
            self.think_parts.append(content)

    def note_tool_call(
        self, call_id: str, name: str, args: dict[str, Any] | None = None
    ) -> None:
        if not call_id or name == "ask_user":
            return
        prev = self.tool_calls.get(call_id) or {}
        self.tool_calls[call_id] = {
            "name": name or prev.get("name") or "tool",
            "args": args if isinstance(args, dict) else (prev.get("args") or {}),
            **(
                {"result": prev["result"]}
                if "result" in prev
                else {}
            ),
        }

    def note_tool_result(self, call_id: str, result: Any, name: str | None = None) -> None:
        if not call_id:
            return
        prev = self.tool_calls.get(call_id) or {
            "name": name or "tool",
            "args": {},
        }
        if name:
            prev["name"] = name
        if prev.get("name") == "ask_user":
            return
        prev["result"] = result
        self.tool_calls[call_id] = prev

    def note_subagent_start(
        self, agent_id: str, *, task: str | None = None, reason: str | None = None
    ) -> None:
        if not agent_id:
            return
        prev = self.subagents.get(agent_id) or {}
        self.subagents[agent_id] = {
            "agentId": agent_id,
            "task": task if task is not None else prev.get("task"),
            "reason": reason if reason is not None else prev.get("reason"),
            "status": "running",
        }

    def note_subagent_done(
        self,
        agent_id: str,
        status: str = "ok",
        *,
        thinking: str | None = None,
        output: str | None = None,
    ) -> None:
        if not agent_id:
            return
        prev = self.subagents.get(agent_id) or {"agentId": agent_id}
        st = status if status in ("ok", "question", "error") else "ok"
        prev["status"] = st
        if thinking is not None and str(thinking).strip():
            prev["thinking"] = str(thinking).strip()[:_THINKING_META_MAX]
        if output is not None and str(output).strip():
            prev["output"] = str(output).strip()[:100_000]
        self.subagents[agent_id] = prev

    def note_subagent_delta(
        self, agent_id: str, *, thinking: str = "", output: str = ""
    ) -> None:
        if not agent_id:
            return
        prev = self.subagents.get(agent_id) or {
            "agentId": agent_id,
            "status": "running",
        }
        if thinking:
            prev["thinking"] = (str(prev.get("thinking") or "") + thinking)[
                :_THINKING_META_MAX
            ]
        if output:
            prev["output"] = (str(prev.get("output") or "") + output)[:100_000]
        self.subagents[agent_id] = prev

    def _extract_expert_thinking(self, full: str, agent_id: str) -> str:
        import re

        name = {
            "scout": "Scout",
            "mentor": "Mentor",
            "navigator": "Navigator",
            "curator": "Curator",
            "scribe": "Scribe",
            "atlas": "Atlas",
            "hub": "Hub",
        }.get(agent_id, agent_id[:1].upper() + agent_id[1:])
        m = re.search(
            rf"【{re.escape(name)}】\s*\n?([\s\S]*?)(?=\n【[^】]+】|$)",
            full,
        )
        return (m.group(1) if m else "").strip()

    async def flush(
        self,
        db: AsyncSession,
        session: AgentSession,
        *,
        metadata: dict | None = None,
    ) -> bool:
        text = "".join(self.parts).strip()
        thinking = "".join(self.think_parts).strip()
        tools = list(self.tool_calls.values())
        subs = []
        for sa in self.subagents.values():
            item = dict(sa)
            if item.get("status") == "running":
                item["status"] = "ok"
            # 已有嵌套 thinking 则保留；否则从 Hub 合流思考拆署名片段
            if not str(item.get("thinking") or "").strip():
                expert_think = self._extract_expert_thinking(
                    thinking, str(item.get("agentId") or "")
                )
                if expert_think:
                    item["thinking"] = expert_think
            subs.append(item)
        self.parts.clear()
        self.think_parts.clear()
        self.tool_calls.clear()
        self.subagents.clear()
        if not text and not thinking and not tools and not subs:
            return False
        meta = dict(metadata or {})
        if thinking:
            meta["thinking"] = thinking[:_THINKING_META_MAX]
        if tools:
            meta["tool_calls"] = tools
        if subs:
            meta["subagents"] = subs
        if self.usage:
            meta.setdefault("usage", self.usage)
        await append_message(
            db,
            session,
            role="assistant",
            content=text or "",
            agent_id=self.agent_id,
            metadata=meta or None,
        )
        self.flushed = True
        return True

    async def switch_agent(
        self,
        db: AsyncSession,
        session: AgentSession,
        new_agent: str,
    ) -> None:
        await self.flush(db, session)
        self.agent_id = new_agent or self.agent_id
        session.active_agent = self.agent_id




async def _apply_persistence_side_effects(
    *,
    buf: "_AgentSegmentBuffer",
    db: AsyncSession,
    session: AgentSession,
    event: StreamEvent | str,
    handle_question: bool = True,
) -> bool:
    """对 typed StreamEvent（或过渡期 SSE 字符串）做落库副作用。返回是否见到 question。"""
    ev = StreamEvent.coerce(event)
    if ev is None:
        return False
    event_kind = ev.kind
    data = ev.data
    saw_question = False
    try:
        if event_kind == "text_delta":
            buf.append_delta(data.get("content") or "")
        elif event_kind == "thinking":
            buf.append_thinking(data.get("content") or "")
        elif event_kind == "agent_switch":
            new_agent = data.get("agent_id") or buf.agent_id
            await buf.switch_agent(db, session, new_agent)
        elif event_kind == "tool_call":
            call_id = data.get("call_id") or data.get("id") or ""
            buf.note_tool_call(
                str(call_id),
                str(data.get("name") or "tool"),
                data.get("args") if isinstance(data.get("args"), dict) else {},
            )
        elif event_kind == "tool_result":
            call_id = data.get("call_id") or data.get("id") or ""
            buf.note_tool_result(
                str(call_id),
                data.get("result", data.get("preview")),
                str(data.get("name") or "") or None,
            )
        elif event_kind == "subagent_start":
            buf.note_subagent_start(
                str(data.get("agent_id") or ""),
                task=data.get("task") if isinstance(data.get("task"), str) else None,
                reason=(
                    data.get("reason")
                    if isinstance(data.get("reason"), str)
                    else None
                ),
            )
        elif event_kind == "subagent_thinking":
            buf.note_subagent_delta(
                str(data.get("agent_id") or ""),
                thinking=str(data.get("content") or ""),
            )
        elif event_kind == "subagent_text":
            buf.note_subagent_delta(
                str(data.get("agent_id") or ""),
                output=str(data.get("content") or ""),
            )
        elif event_kind == "subagent_done":
            buf.note_subagent_done(
                str(data.get("agent_id") or ""),
                str(data.get("status") or "ok"),
                thinking=(
                    str(data["thinking"])
                    if isinstance(data.get("thinking"), str)
                    else None
                ),
                output=(
                    str(data["output"])
                    if isinstance(data.get("output"), str)
                    else None
                ),
            )
        elif event_kind == "done":
            buf.usage = data.get("usage") or {}
        elif event_kind == "question" and handle_question:
            session.status = "pending_question"
            await buf.flush(db, session)
            intro = data.get("intro") or {}
            title = (
                intro.get("content")
                if isinstance(intro, dict)
                else None
            ) or data.get("title") or "结构化反问"
            title_plain = str(title).replace("**", "").strip() or "结构化反问"
            await append_message(
                db,
                session,
                role="assistant",
                content=f"发起反问：{title_plain}（请在弹窗中选择）",
                agent_id=buf.agent_id,
                content_type="question",
                metadata=data,
            )
            # 落库成功后才标记 saw_question，避免调用方据半态跳过最终 flush 丢消息
            saw_question = True
    except Exception:
        # 落库副作用失败不应静默：记日志暴露 DB 锁/事务错误，流继续但用户可查日志定位
        logger.exception("Agent 流事件落库副作用失败 event_kind=%s", event_kind)
    return saw_question


async def stream_chat(
    db: AsyncSession,
    session_id: UUID,
    message: str,
    *,
    project_id: UUID | None = None,
    force_local: bool = False,
) -> AsyncIterator[str]:
    from api_backend.config import get_settings

    settings = get_settings()
    # 独立 Agent 进程：API 只做会话归属预检后代理；落库与 Hub 在 Agent 侧执行
    if (settings.agent_base_url or "").strip() and not force_local:
        session = await db.get(AgentSession, session_id)
        if not session:
            yield encode_stream_item(
                format_sse("error", {"code": "AGENT_SESSION_NOT_FOUND", "message": "会话不存在"})
            )
            return
        if not (settings.agent_internal_token or "").strip():
            yield encode_stream_item(
                format_sse(
                    "error",
                    {
                        "code": "AGENT_MISCONFIGURED",
                        "message": "已配置 AGENT_BASE_URL 但缺少 agent_internal_token",
                    },
                )
            )
            return
        from api_backend.services.agent_proxy import proxy_agent_chat_sse

        async for raw in proxy_agent_chat_sse(
            session_id=session_id,
                        message=message,
            project_id=project_id,
        ):
            yield raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        return

    session = await db.get(AgentSession, session_id)
    if not session:
        yield encode_stream_item(
            format_sse("error", {"code": "AGENT_SESSION_NOT_FOUND", "message": "会话不存在"})
        )
        return

    # 消息级 project_id：追加到会话多项目上下文（不替换已有）
    if project_id is not None:
        try:
            await add_session_project(db, session, project_id)
            await db.commit()
        except ValueError:
            yield encode_stream_item(
                format_sse(
                    "error",
                    {"code": "AGENT_SESSION_PROJECT_DENIED", "message": "无权绑定该项目到会话"},
                )
            )
            return

    await append_message(db, session, role="user", content=message, agent_id="hub")

    cancel_ev = _begin_session_stream(session_id)
    # 跨 worker token：把本次流的标识写到 agent_session_cancel_tokens 表，
    # 流循环每 N 步与 DB 当前 token 比对，确保多 worker 部署下取消信号仍生效。
    cancel_token = await _begin_session_cancel_token(db, session_id)
    hub = HubService(db)
    buf = _AgentSegmentBuffer(agent_id="hub")
    aborted = False
    # question 已落库时，不再把同轮 text_delta 再写成 assistant 气泡
    saw_question = False
    bound_ids = await get_session_project_ids(db, session_id)
    primary_project_id = session.project_id or (bound_ids[0] if bound_ids else None)

    # 跨 worker 取消轮询节流：每 8 个 chunk 查一次 DB
    _CANCEL_POLL_INTERVAL = 8
    _chunk_idx = 0

    try:
        async for chunk in hub.handle_chat(
                        session_id=session_id,
            message=message,
            project_id=primary_project_id,
        ):
            # 每 N 个 chunk 跨 worker 取消检查；本地 Event 命中走快路径
            if (_chunk_idx % _CANCEL_POLL_INTERVAL == 0 and
                    await _is_session_cancel_observed(
                        db, session_id, cancel_token, cancel_ev
                    )):
                aborted = True
                break
            if cancel_ev.is_set():
                aborted = True
                break
            _chunk_idx += 1
            if await _apply_persistence_side_effects(
                buf=buf, db=db, session=session, event=chunk
            ):
                saw_question = True
            yield encode_stream_item(chunk)
        # 客户端断开或被同会话新流抢占：尽量落库已完成分段，半截当前段丢弃
        if aborted or cancel_ev.is_set():
            return

        # 已有 question 消息时跳过剩余文本落库，避免同轮双气泡
        if saw_question:
            return

        if await buf.flush(db, session, metadata={"usage": buf.usage}):
            session.active_agent = buf.agent_id
            session.status = "active"
            await db.commit()
        elif buf.flushed:
            session.active_agent = buf.agent_id
            session.status = "active"
            await db.commit()
    except asyncio.CancelledError:
        # 传输层取消：已 flush 的分段保留；当前未完成段不落库
        raise
    except Exception as e:
        logger.exception("stream_chat 失败: %s", e)
        yield encode_stream_item(format_sse(
            "error",
            {"code": "AGENT_CHAT_FAILED", "message": f"对话失败: {e}"},
        ))
    finally:
        _end_session_stream(session_id, cancel_ev)
        try:
            await _end_session_cancel_token(db, session_id, cancel_token)
        except Exception:  # noqa: BLE001 — 资源清理失败不影响主流程
            pass


async def stream_question_answer(
    db: AsyncSession,
    session_id: UUID,
    question_id: str,
    answers: dict[str, Any],
    *,
    skipped: bool = False,
) -> AsyncIterator[str]:
    session = await db.get(AgentSession, session_id)
    if not session:
        yield encode_stream_item(format_sse("error", {"code": "AGENT_SESSION_NOT_FOUND", "message": "会话不存在"}))
        return

    # 找回原始反问结构，便于历史卡片展示
    question_payload: dict[str, Any] | None = None
    prior_msgs = (
        await db.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    for m in prior_msgs:
        if not m.message_meta:
            continue
        try:
            meta = json.loads(m.message_meta)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(meta, dict):
            continue
        q = meta.get("question") if isinstance(meta.get("question"), dict) else meta
        if isinstance(q, dict) and (
            q.get("question_id") == question_id or m.content_type == "question"
        ):
            if q.get("question_id") or q.get("questions"):
                question_payload = q
                break

    details: list[dict[str, str]] = []
    if question_payload and isinstance(question_payload.get("questions"), list):
        for qi in question_payload["questions"]:
            if not isinstance(qi, dict):
                continue
            qid = str(qi.get("id") or "")
            prompt = str(qi.get("text") or qi.get("prompt") or "")
            ans = answers.get(qid) if qid else None
            label = "（跳过）" if skipped else _format_answer_label(qi, ans)
            details.append({"question": prompt, "answer": label})
    summary = (
        "已跳过"
        if skipped
        else (
            " · ".join(d["answer"] for d in details[:3])
            if details
            else "已回答"
        )
    )
    if not skipped and details and len(details) > 3:
        summary = f"已回答 {len(details)} 题"

    answer_text = "[跳过反问]" if skipped else f"[反问回答] {summary}"
    await append_message(
        db,
        session,
        role="user",
        content=answer_text,
        agent_id="hub",
        content_type="question_answer",
        metadata={
            "question_answer": {
                "question": question_payload
                or {
                    "question_id": question_id,
                    "intro": {"type": "markdown", "content": "结构化反问"},
                    "questions": [],
                    "actions": {"submit": {"text": "提交", "style": "primary"}},
                    "allow_skip": True,
                    "timeout": None,
                },
                "answers": list(answers.values()),
                "skipped": skipped,
                "summary": summary,
                "details": details
                or [{"question": "（题目）", "answer": summary}],
            }
        },
    )
    session.status = "active"

    hub = HubService(db)
    buf = _AgentSegmentBuffer(agent_id=session.active_agent or "hub")

    async for chunk in hub.handle_question_answer(
                session_id=session_id,
        question_id=question_id,
        answers=answers,
        skipped=skipped,
        project_id=session.project_id,
    ):
        await _apply_persistence_side_effects(
            buf=buf, db=db, session=session, event=chunk
        )

        yield encode_stream_item(chunk)
    if await buf.flush(db, session, metadata={"usage": buf.usage}):
        session.active_agent = buf.agent_id
        session.status = "active"
        await db.commit()


def _format_answer_label(qi: dict[str, Any], ans: Any) -> str:
    """把单题答案格式化为可读文案。"""
    if not isinstance(ans, dict):
        return str(ans) if ans is not None else "（未答）"
    atype = ans.get("type")
    if atype == "radio":
        other = (ans.get("other_text") or "").strip()
        if other:
            return other
        val = str(ans.get("value") or "")
        for o in qi.get("options") or []:
            if isinstance(o, dict) and str(o.get("value")) == val:
                return str(o.get("label") or o.get("text") or val)
        return val or "（未答）"
    if atype == "checkbox":
        vals = ans.get("values") or []
        labels: list[str] = []
        opts = {str(o.get("value")): str(o.get("text") or o.get("label") or o.get("value"))
                for o in (qi.get("options") or []) if isinstance(o, dict)}
        for v in vals:
            labels.append(opts.get(str(v), str(v)))
        return "、".join(labels) if labels else "（未答）"
    if atype == "slider":
        return str(ans.get("value", ""))
    return json.dumps(ans, ensure_ascii=False)[:120]


_ANALYZE_PROMPTS: dict[str, str] = {
    "scout": (
        "请在 30 秒级给出项目速览：一句话定位、核心功能、技术栈、适合谁、学习门槛、下一步建议。"
        "控制篇幅，禁止 emoji。"
    ),
    "mentor": (
        "请深入讲解该项目的架构、核心设计与关键路径，按初学者到进阶分层说明。"
        "禁止 emoji。"
    ),
    "navigator": (
        "请为学习该项目制定分阶段计划：前置知识、阅读顺序、里程碑与练习。"
        "禁止 emoji。"
    ),
    "curator": (
        "请为该项目建议分类、标签与归类理由（对照常见预设：前端/后端/AI-ML/DevOps/其他）。"
        "禁止 emoji。"
    ),
    "scribe": (
        "请基于项目信息生成结构化学习笔记大纲（标题 + 小节要点），便于保存为笔记。"
        "禁止 emoji。"
    ),
    "atlas": (
        "请从知识图谱视角说明该项目与常见生态/技术栈的关联，以及可迁移学习路径。"
        "禁止 emoji。"
    ),
}


async def stream_analyze(
    db: AsyncSession,
    project_id: UUID,
    *,
    depth: str = "quick",
    agent_id: str | None = None,
) -> AsyncIterator[str]:
    from agent_core.agents.registry import get_registry
    from api_backend.services.project_service import get_project

    try:
        project = await get_project(db, project_id)
        if not project:
            yield encode_stream_item(format_sse(
                "error",
                {"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
            ))
            return

        # 解析 Agent：显式 agent_id 优先；否则 depth 兼容旧客户端
        resolved = (agent_id or "").strip().lower() or (
            "mentor" if depth == "deep" else "scout"
        )
        # 禁止 hub 作为详情分析入口；未知 id 回退 scout
        if resolved == "hub" or not get_registry().has(resolved):
            resolved = "scout"

        # 快速分析会话：标记 source=analyze，默认不在 Agent Chat 主列表展开
        session = AgentSession(
                        title=f"{resolved} · {project.name}",
            active_agent=resolved,
            project_id=project_id,
            source="analyze",
        )
        db.add(session)
        await db.flush()
        await set_session_projects(db, session, [project_id])
        await db.commit()
        await db.refresh(session)

        role_hint = _ANALYZE_PROMPTS.get(resolved, _ANALYZE_PROMPTS["scout"])
        prompt = (
            f"{role_hint}\n\n"
            f"项目: {project.name}\n"
            f"URL: {project.url}\n"
            f"描述: {project.description or '无'}\n"
            f"语言: {project.language or '未知'}\n"
            f"Stars: {project.stars}\n"
            f"学习进度: {project.progress}\n"
            "请用中文简洁输出，可用 Markdown。禁止任何 emoji。"
        )
        await append_message(db, session, role="user", content=prompt, agent_id="hub")

        # agent_switch 由 handle_direct_agent 统一发送，避免重复
        yield encode_stream_item(format_sse(
            "thinking",
            {
                "content": (
                    f"[状态] 角色={resolved} · 项目={project.name}\n"
                    f"[上下文] 语言={project.language or '未知'} · "
                    f"stars={project.stars} · 进度={project.progress}\n"
                )
            },
        ))

        hub = HubService(db)
        collected: list[str] = []
        async for chunk in hub.handle_direct_agent(
                        session_id=session.id,
            agent_id=resolved,
            message=prompt,
            project_id=project_id,
        ):
            ev = StreamEvent.coerce(chunk)
            if ev is not None and ev.kind == "text_delta":
                collected.append(str(ev.data.get("content") or ""))
            yield encode_stream_item(chunk)

        reply = "".join(collected)
        if reply:
            await append_message(db, session, role="assistant", content=reply, agent_id=resolved)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("stream_analyze 失败: %s", e)
        yield encode_stream_item(format_sse(
            "error",
            {"code": "AGENT_ANALYZE_FAILED", "message": f"分析失败: {e}"},
        ))


async def stream_import_assist(
    db: AsyncSession,
    message: str,
    context: dict[str, Any],
) -> AsyncIterator[str]:
    """导入助手：精简工具 + 寒暄快路径 + 空正文兜底。

    §4.2.11: 与 Hub 使用同一配置源 — build_llm_config_from_user + get_registry() +
    global_registry，与 _handle_chat / _handle_dispatches 同源；不重复读取 LLM Key。
"""
    import re
    from dataclasses import replace

    from agent_core.agents.react import EngineResult, ReActEngine
    from agent_core.agents.registry import get_registry
    from agent_core.agents.stream_events import format_sse
    from agent_core.llm.config import build_llm_config_from_user
    from agent_core.llm.provider import LLMProvider
    from agent_core.memory.context import ContextBuilder
    from agent_core.memory.service import MemoryService
    from agent_core.tools.registry import ToolRegistry, global_registry

    available = list(context.get("available_repo_keys") or [])
    selected = list(context.get("selected_repo_keys") or [])
    mode = context.get("mode") or "stars"
    available_repos = list(context.get("available_repos") or [])
    imported_from_client = list(context.get("imported_projects") or [])
    msg = (message or "").strip()

    # 服务端补齐：用户库项目 + Stars 缓存（即使前端未传也能回答）
    from api_backend.models.project import Project
    from sqlalchemy import func, select

    proj_rows = (
        await db.execute(
            select(Project)
            
            .order_by(Project.stars.desc())
            .limit(80)
        )
    ).scalars().all()
    imported_projects = imported_from_client or [
        {
            "name": p.name,
            "language": p.language,
            "progress": p.progress,
            "stars": p.stars,
            "description": (p.description or "")[:120],
        }
        for p in proj_rows
    ]
    progress_rows = (
        await db.execute(
            select(Project.progress, func.count())
            
            .group_by(Project.progress)
        )
    ).all()
    progress_stats = {str(prog or "none"): int(cnt) for prog, cnt in progress_rows}

    # Stars 缓存（settings_json.github_stars_cache）
    stars_cache_items: list[dict] = []
    try:
        from api_backend.services.app_state_service import get_or_create_app_state

        state = await get_or_create_app_state(db)
        settings_raw = json.loads(state.settings_json or "{}")
        cache = settings_raw.get("github_stars_cache") if isinstance(settings_raw, dict) else None
        if isinstance(cache, dict) and isinstance(cache.get("items"), list):
            stars_cache_items = cache["items"][:120]
    except (json.JSONDecodeError, TypeError):
        stars_cache_items = []

    if not available and stars_cache_items and mode == "stars":
        available = [
            f"{it.get('owner')}/{it.get('name') or it.get('repo')}"
            for it in stars_cache_items
            if it.get("owner") and (it.get("name") or it.get("repo"))
        ]
    if not available_repos and stars_cache_items:
        available_repos = [
            {
                "key": f"{it.get('owner')}/{it.get('name') or it.get('repo')}",
                "language": it.get("language"),
                "stars": it.get("stars", 0),
                "already_imported": False,
                "description": (it.get("description") or "")[:120],
            }
            for it in stars_cache_items
            if it.get("owner") and (it.get("name") or it.get("repo"))
        ][:80]

    def _emit_text(text: str):
        for i in range(0, len(text), 40):
            yield encode_stream_item(format_sse("text_delta", {"content": text[i : i + 40]}))

    def _keyword_hits(limit: int = 12) -> list[str]:
        q = msg.lower()
        parts = [p for p in re.split(r"[\s,，、/]+", q) if len(p) > 1]
        hits = [
            k
            for k in available
            if any(p in k.lower() for p in parts)
        ][:limit]
        return hits

    # —— 寒暄快路径：不调 LLM、不调外网工具 ——
    if re.fullmatch(
        r"(你好|您好|嗨|哈喽|hi|hello|hey|在吗|早上好|下午好|晚上好)[！!。.~～]*",
        msg,
        flags=re.I,
    ):
        n = len(available)
        n_imp = len(imported_projects)
        display = "local"
        try:
            from api_backend.services.app_state_service import get_or_create_app_state

            display = (await get_or_create_app_state(db)).display_name or "local"
        except Exception:
            pass
        text = (
            f"你好！我是导入助手（用户 **{display}**）。\n\n"
            f"左侧候选 **{n}** 个仓库；你库中已导入 **{n_imp}** 个项目。\n"
            "你可以直接说：\n"
            "- 「我 star 的项目都是什么类型」\n"
            "- 「推荐和我已学项目类似的仓库」\n"
            "- 「勾选前端相关 / 选 5 个高 star」\n\n"
            "我会结合 Stars、已导入与学习进度回答，并在左侧**自动勾选**。"
        )
        for chunk in _emit_text(text):
            yield encode_stream_item(chunk)
        yield encode_stream_item(format_sse("done", {"usage": {"tokens": len(text)}, "iterations": 0}))
        return

    # —— 无 LLM：规则降级 ——
    llm_cfg = await build_llm_config_from_user(db)
    if not llm_cfg:
        hits = _keyword_hits()
        if not hits and available:
            hits = available[:5]
        if hits:
            yield encode_stream_item(format_sse(
                "select_repos",
                {
                    "repo_keys": hits,
                    "action": "set",
                    "reason": "降级模式：按关键词匹配勾选",
                    "count": len(hits),
                },
            ))
        text = (
            "【降级模式】未检测到可用 LLM Key（设置页测试通过后若仍出现，请重新保存 Key 再试）。\n\n"
            + (
                f"已在左侧勾选 **{len(hits)}** 个仓库：\n"
                + "\n".join(f"- `{k}`" for k in hits)
                + "\n\n请确认后点击「导入选中」。"
                if hits
                else "左侧暂无候选仓库。请先同步 Stars 或完成搜索。"
            )
        )
        for chunk in _emit_text(text):
            yield encode_stream_item(chunk)
        yield encode_stream_item(format_sse(
            "done", {"usage": {"tokens": len(text)}, "iterations": 0, "degraded": True}
        ))
        return

    # —— LLM 路径：仅允许 select_import_repos，避免 fetch_github 超时导致空响应 ——
    session = AgentSession(
                title="导入助手",
        active_agent="curator",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    preview_keys = available[:80]
    # 语言分布（基于候选摘要）
    lang_counter: dict[str, int] = {}
    for r in available_repos[:120]:
        if not isinstance(r, dict):
            continue
        lang = (r.get("language") or "Unknown") or "Unknown"
        lang_counter[str(lang)] = lang_counter.get(str(lang), 0) + 1
    top_langs = sorted(lang_counter.items(), key=lambda x: -x[1])[:12]

    from api_backend.services.app_state_service import get_or_create_app_state

    ctx_text = json.dumps(
        {
            "user": {"username": (await get_or_create_app_state(db)).display_name or "local"},
            "mode": mode,
            "available_count": len(available),
            "available_repo_keys_preview": preview_keys,
            "available_repos_sample": available_repos[:40],
            "stars_language_distribution": top_langs,
            "selected_repo_keys": selected,
            "imported_count": len(imported_projects),
            "imported_projects_sample": imported_projects[:40],
            "progress_stats": progress_stats,
        },
        ensure_ascii=False,
    )
    prompt = (
        "你是 Voyager **导入助手**。用中文简洁回复。\n"
        "你掌握：① 用户 Stars/搜索候选 ② 左侧勾选 ③ 已导入项目与学习进度 ④ 用户名。\n"
        "能力：\n"
        "- 回答「star 了哪些类型 / 语言分布」：基于 stars_language_distribution 与 available_repos_sample。\n"
        "- 对比已学项目推荐类似仓库：用 imported_projects_sample + progress_stats。\n"
        "- 筛选/推荐并勾选：必须调用 select_import_repos，repo_keys 只能来自 available_repo_keys_preview。\n"
        "- 查询库内项目可用 query_user_projects / get_learning_stats（本地库，勿打外网）。\n"
        "勾选后请用户点「导入选中」；不要声称已完成导入。不要空回复。\n"
        f"上下文: {ctx_text}\n"
        f"用户: {msg}"
    )

    memory = MemoryService(db)
    builder = ContextBuilder(db, memory)
    llm = LLMProvider(llm_cfg)
    # 本地工具 + 勾选：不挂 fetch_github / fetch_readme，避免外网超时
    slim_tools = [
        "select_import_repos",
        "query_user_projects",
        "get_learning_stats",
        "get_project_detail",
    ]
    agent_def = replace(
        get_registry().get("curator"),
        max_tokens=1536,
        temperature=0.4,
        tools=slim_tools,
    )
    slim_reg = ToolRegistry()
    for tname in slim_tools:
        t = global_registry.get(tname)
        if t:
            slim_reg.register(t)

    ctx = await builder.build_run_context(
                session_id=session.id,
        agent_id="curator",
        llm=llm,
        llm_config=llm_cfg,
        speaking_style="default",
    )
    ctx.tool_registry = slim_reg
    ctx.extra["available_repo_keys"] = available
    ctx.extra["selected_repo_keys"] = selected
    ctx.extra["disable_questions"] = True  # 嵌入式 UI 无反问面板
    messages = await builder.build_messages(
        agent_def=agent_def,
        ctx=ctx,
        user_message=prompt,
        history=[],
    )

    yield encode_stream_item(format_sse(
        "agent_switch",
        {
            "agent_id": "curator",
            "from": "hub",
            "to": "curator",
            "reason": "导入助手",
        },
    ))
    yield encode_stream_item(format_sse(
        "thinking",
        {
            "content": (
                f"分析候选 {len(available)} 个、已导入 {len(imported_projects)} 个、"
                f"勾选 {len(selected)} 个；进度统计 {progress_stats}…"
            )
        },
    ))

    engine = ReActEngine(max_iterations=4)
    had_text = False
    try:
        async for item in engine.run(
            agent_def=agent_def, ctx=ctx, messages=messages, emit_sse=True
        ):
            if isinstance(item, EngineResult):
                if item.text and item.text.strip():
                    had_text = True
                continue
            if isinstance(item, str) and "event: text_delta" in item:
                had_text = True
            yield item
    except Exception as e:
        logger.exception("import assist failed")
        yield encode_stream_item(format_sse(
            "error",
            {"code": "AGENT_IMPORT_ASSIST_FAILED", "message": f"导入助手失败: {e}"},
        ))
        err = f"导入助手出错：{e}"
        for chunk in _emit_text(err):
            yield encode_stream_item(chunk)
        yield encode_stream_item(format_sse("done", {"usage": {"tokens": 0}, "iterations": 0}))
        return

    if not had_text:
        # 最后兜底：规则勾选 + 说明
        hits = _keyword_hits() or available[:5]
        if hits:
            yield encode_stream_item(format_sse(
                "select_repos",
                {
                    "repo_keys": hits,
                    "action": "set",
                    "reason": "自动兜底勾选",
                    "count": len(hits),
                },
            ))
        text = (
            "我在这边了。左侧候选 "
            f"**{len(available)}** 个"
            + (
                f"，已为你勾选 {len(hits)} 个示例：\n"
                + "\n".join(f"- `{k}`" for k in hits)
                + "\n\n可以说「只要 Python」或「前端框架」让我重新勾选。"
                if hits
                else "。请先加载 Stars/搜索结果，或直接描述想导入的技术栈。"
            )
        )
        for chunk in _emit_text(text):
            yield encode_stream_item(chunk)
        yield encode_stream_item(format_sse("done", {"usage": {"tokens": len(text)}, "iterations": 0}))


async def stream_graph_guide(
    db: AsyncSession,
    message: str,
    *,
    selected_node_id: str | None = None,
) -> AsyncIterator[str]:
    from agent_core.agents.stream_events import format_sse

    session = AgentSession(
                title="图谱向导",
        active_agent="atlas",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    prompt = message
    if selected_node_id:
        prompt = f"用户选中了图谱节点 project_id={selected_node_id}。\n{message}"

    hub = HubService(db)
    project_uuid = None
    if selected_node_id:
        try:
            project_uuid = UUID(selected_node_id)
        except ValueError:
            project_uuid = None

    had_text = False
    try:
        async for chunk in hub.handle_direct_agent(
                        session_id=session.id,
            agent_id="atlas",
            message=prompt,
            project_id=project_uuid,
        ):
            if isinstance(chunk, str) and "event: text_delta" in chunk:
                had_text = True
            yield encode_stream_item(chunk)
    except Exception as e:
        err = f"图谱向导出错：{e}"
        for i in range(0, len(err), 40):
            yield encode_stream_item(format_sse("text_delta", {"content": err[i : i + 40]}))
        yield encode_stream_item(format_sse("done", {"usage": {"tokens": 0}, "iterations": 0}))
        return

    if not had_text:
        text = (
            "我是 Atlas 图谱向导。请在左侧点选节点，或问我「这些项目怎么关联」。"
            "若持续无回复，请到设置确认 LLM 测试通过。"
        )
        for i in range(0, len(text), 40):
            yield encode_stream_item(format_sse("text_delta", {"content": text[i : i + 40]}))
        yield encode_stream_item(format_sse("done", {"usage": {"tokens": len(text)}, "iterations": 0}))


async def _run_direct_agent_stream(
    db: AsyncSession,
    *,
    session_id: UUID,
    agent_id: str,
    prompt: str,
    project_id: UUID | None = None,
    error_code: str,
    error_prefix: str,
) -> AsyncIterator[str]:
    """统一"直接 agent 流"执行：Hub 单 agent 直答 + 异常转 error SSE。

    stream_trending_scout / stream_classify_project / stream_generate_note 共用。
    错误契约：仅 Hub 调用（agent 执行）失败转 error SSE；调用方在进入 helper 前
    的 setup（会话创建/项目校验/prompt 拼装）失败直接抛出（与 stream_chat 的
    既有模式一致——try 从 Hub 调用开始，DB/setup 错误冒为 500）。
    注：stream_analyze 的 try 从 setup 开始（其失败同样转 error SSE），契约
    与此处不同，如需统一应另起 refactor。
    """
    try:
        hub = HubService(db)
        async for chunk in hub.handle_direct_agent(
            session_id=session_id,
            agent_id=agent_id,
            message=prompt,
            project_id=project_id,
        ):
            yield encode_stream_item(chunk)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("%s 失败: %s", error_prefix, e)
        yield encode_stream_item(format_sse(
            "error",
            {"code": error_code, "message": f"{error_prefix}失败: {e}"},
        ))


async def stream_trending_scout(
    db: AsyncSession,
    params: dict[str, Any],
) -> AsyncIterator[str]:
    session = AgentSession(
        title="Trending Scout",
        active_agent="scout",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    name = params.get("full_name") or params.get("name") or "unknown"
    prompt = (
        f"用 Scout 风格快速介绍 trending 仓库 {name}。\n"
        f"描述: {params.get('description') or '无'}\n"
        f"语言: {params.get('language') or '未知'} Stars: {params.get('stars') or 0}\n"
        f"URL: {params.get('url') or ''}\n"
        "说明是否值得加入用户学习库。"
    )
    async for chunk in _run_direct_agent_stream(
        db,
        session_id=session.id,
        agent_id="scout",
        prompt=prompt,
        error_code="AGENT_TRENDING_FAILED",
        error_prefix="趋势扫描",
    ):
        yield chunk


async def stream_classify_project(
    db: AsyncSession,
    project_id: UUID,
    *,
    user_hint: str | None = None,
) -> AsyncIterator[str]:
    """Curator 分类落库入口（prompt 留在 service，路由不拼字符串）。"""
    project = await get_project(db, project_id)
    if not project:
        yield encode_stream_item(format_sse(
            "error",
            {"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        ))
        return

    session = await create_session(
        db, project_id=project_id, title=f"分类 {project.name}"
    )
    hint = user_hint or ""
    prompt = (
        f"请为项目 {project.name} ({project.url}) 完成分类并落库。"
        f"描述: {project.description or ''} 语言: {project.language or ''}。"
        f"用户提示: {hint}。"
        f"project_id={project_id}。"
        "必须调用 set_project_category（必要时 set_project_tags）真正写入，"
        "不要只 suggest；最后用一两句话说明结果与分类名。"
    )
    async for chunk in _run_direct_agent_stream(
        db,
        session_id=session.id,
        agent_id="curator",
        prompt=prompt,
        project_id=project_id,
        error_code="AGENT_CLASSIFY_FAILED",
        error_prefix="分类",
    ):
        yield chunk


async def stream_generate_note(
    db: AsyncSession,
    project_id: UUID,
    *,
    mode: str = "project",
    topic: str | None = None,
) -> AsyncIterator[str]:
    """Scribe 笔记生成落库入口。"""
    project = await get_project(db, project_id)
    if not project:
        yield encode_stream_item(format_sse(
            "error",
            {"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        ))
        return

    session = await create_session(
        db, project_id=project_id, title=f"笔记 {project.name}"
    )
    mode_norm = mode if mode in ("project", "standalone") else "project"
    topic_text = topic or project.name
    prompt = (
        f"请以 Scribe {mode_norm} 模式为项目 {project.name} 生成学习笔记并保存到系统。"
        f"主题: {topic_text}。URL: {project.url}。project_id={project_id}。"
        f"{'检索相似已学项目做对比（仅当相似度高时），compare_project_ids 传入对比项' if mode_norm == 'project' else '独立成文，不对比'}。"
        "必须调用 create_note 写入数据库（title + 完整 Markdown content），"
        "不要只输出草稿；落库后简述笔记标题与已保存。"
    )
    async for chunk in _run_direct_agent_stream(
        db,
        session_id=session.id,
        agent_id="scribe",
        prompt=prompt,
        project_id=project_id,
        error_code="AGENT_NOTE_FAILED",
        error_prefix="笔记生成",
    ):
        yield chunk


async def get_context_window(
    db: AsyncSession, session_id: UUID | None
) -> ContextWindowStatsOut:
    memory = MemoryService(db)
    total = 0
    system_tokens = 800  # 估计 system prompt
    tool_tokens = 400
    memory_tokens = 0
    model = "gpt-4o"
    limit = 128_000

    llm_cfg = await build_llm_config_from_user(db)
    if llm_cfg:
        model = llm_cfg.model
        limit = llm_cfg.max_context_tokens

    if session_id:
        session = await db.get(AgentSession, session_id)
        if session:
            msgs = await memory.list_recent_messages(session_id, limit=100)
            total = sum(memory.estimate_tokens(m.content or "") for m in msgs)
            long_mem = await memory.get_long_memory()
            memory_tokens = sum(
                memory.estimate_tokens(str(m.get("content", ""))) for m in long_mem
            )

    segments = [
        ContextWindowSegmentOut(label="System / Soul", tokens=system_tokens, kind="system"),
        ContextWindowSegmentOut(label="长期记忆", tokens=memory_tokens, kind="memory"),
        ContextWindowSegmentOut(label="工具定义", tokens=tool_tokens, kind="tools"),
        ContextWindowSegmentOut(label="对话消息", tokens=total, kind="messages"),
    ]
    input_tokens = system_tokens + memory_tokens + tool_tokens + total
    return ContextWindowStatsOut(
        session_id=str(session_id) if session_id else None,
        model=model,
        context_limit=limit,
        input_tokens=input_tokens,
        output_tokens=0,
        total_tokens=input_tokens,
        segments=segments,
    )
