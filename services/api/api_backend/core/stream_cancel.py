"""会话流取消信号 —— 跨 worker 共享。

背景：旧实现 `_session_stream_cancel` 是进程内 dict，仅在单 worker 部署下有效。
多 worker (uvicorn `--workers >1`) 部署时，取消/抢占语义形同虚设。

本模块用一张轻量表 `agent_session_cancel_tokens` 实现跨 worker 信号：
- `begin()`  写入新 token 并取消同一 session 的旧 token（同事务原子）
- `poll()`   流循环每 N 个 chunk 调用一次，检查自身 token 是否被新 token 取代
- `clear()`  结束流时清理 token

为什么不用 Redis：项目当前未引入 Redis 依赖。表方案足够；接入 Redis 时只需把
本模块替换为 redis-based 实现即可（接口签名不变）。
"""
from __future__ import annotations

import secrets
from datetime import datetime
from uuid import UUID

from api_backend.models.agent import AgentSessionCancelToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def begin(db: AsyncSession, session_id: UUID) -> str:
    """为新流登记 token，自动覆盖同 session 的旧 token。

    返回的 token 用于后续 `poll()` 比较。
    """
    new_token = secrets.token_urlsafe(24)
    # 原子覆盖：先清旧，再插新；唯一约束 (session_id) 兜底并发。
    old = await db.execute(
        select(AgentSessionCancelToken).where(
            AgentSessionCancelToken.session_id == session_id
        )
    )
    row = old.scalar_one_or_none()
    if row is not None:
        row.cancel_token = new_token
        row.updated_at = datetime.utcnow()
    else:
        db.add(
            AgentSessionCancelToken(
                session_id=session_id,
                cancel_token=new_token,
            )
        )
    try:
        await db.flush()
    except IntegrityError:
        # 并发场景下唯一约束触发；重试 select-then-update 一次
        await db.rollback()
        old = await db.execute(
            select(AgentSessionCancelToken).where(
                AgentSessionCancelToken.session_id == session_id
            )
        )
        row = old.scalar_one()
        row.cancel_token = new_token
        row.updated_at = datetime.utcnow()
        await db.flush()
    return new_token


async def poll(db: AsyncSession, session_id: UUID, my_token: str) -> bool:
    """轮询：若 token 已被取代（其他 worker / 协程写入新 token），返回 True。

    True 表示本流应当让步终止。
    """
    row = (
        await db.execute(
            select(AgentSessionCancelToken.cancel_token).where(
                AgentSessionCancelToken.session_id == session_id
            )
        )
    ).scalar_one_or_none()
    return row is not None and row != my_token


async def clear(db: AsyncSession, session_id: UUID, my_token: str) -> None:
    """结束流时清理。仅当 token 仍是自身时才删除（避免误删新流的 token）。

    若 token 已被取代，则本流本就是被取消的，无副作用。
    """
    row = (
        await db.execute(
            select(AgentSessionCancelToken).where(
                AgentSessionCancelToken.session_id == session_id
            )
        )
    ).scalar_one_or_none()
    if row is not None and row.cancel_token == my_token:
        await db.delete(row)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
