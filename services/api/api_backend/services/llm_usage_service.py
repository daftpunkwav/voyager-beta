"""LLM 用量记录与聚合。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from api_backend.models.llm_usage import LlmUsageEvent
from api_backend.services.llm_usage_parse import parse_usage_details
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_TOP_MODELS_PER_DAY = 6

# litellm 路由前缀（model 字符串左段）；剥离后才是真实模型名
_ROUTE_PREFIXES = frozenset(
    {
        "openai",
        "anthropic",
        "gemini",
        "ollama",
        "deepseek",
        "minimax",
        "azure",
        "bedrock",
        "vertex_ai",
        "litellm",
    }
)

# 常被误当成「供应商」写入的 API 格式名
_API_FORMAT_ALIASES = frozenset(
    {
        "openai",
        "anthropic",
        "gemini",
        "google",
        "ollama",
        "azure",
        "bedrock",
        "vertex_ai",
    }
)

# 模型名 → 真实 preset 供应商（修复历史 litellm / api_format 脏数据）
_MODEL_PROVIDER_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^minimax", re.I), "minimax"),
    (re.compile(r"^claude", re.I), "anthropic"),
    (re.compile(r"^gpt-", re.I), "openai"),
    (re.compile(r"^o[1-9]", re.I), "openai"),
    (re.compile(r"^gemini", re.I), "google"),
    (re.compile(r"^deepseek", re.I), "deepseek"),
    (re.compile(r"^glm-", re.I), "zhipu"),
)


def normalize_model_name(model: str) -> str:
    """去掉 anthropic/openai 等路由前缀，得到真实模型名。"""
    m = (model or "").strip() or "(unknown)"
    if "/" not in m:
        return m
    left, right = m.split("/", 1)
    if left.lower() in _ROUTE_PREFIXES and right:
        return right
    return m


def infer_provider_from_model(model: str) -> str | None:
    """从模型名推断 preset 供应商。"""
    m = normalize_model_name(model)
    for pat, prov in _MODEL_PROVIDER_HINTS:
        if pat.search(m):
            return prov
    return None


def normalize_provider_name(provider: str, *, model: str = "") -> str:
    """规范化供应商名；勿把 litellm / API 格式当真实供应商。"""
    p = (provider or "").strip()
    inferred = infer_provider_from_model(model) if model else None
    pl = p.lower()

    if not p or pl in ("litellm", "unknown"):
        return inferred or "unknown"

    # 落库成 anthropic 但模型是 MiniMax-*：改用推断的真实供应商
    if inferred and pl in _API_FORMAT_ALIASES and inferred != pl:
        return inferred

    return p


def format_provider_model(provider: str, model: str) -> str:
    """展示用：提供商/模型。"""
    m = normalize_model_name(model)
    p = normalize_provider_name(provider, model=model)
    if p and p != "unknown":
        return f"{p}/{m}"
    return m


def _empty_totals() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "prompt_cached_tokens": 0,
        "prompt_uncached_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "calls": 0,
    }


def _row_breakdown(
    *,
    prompt: int,
    cached: int,
    uncached: int,
    completion: int,
    total: int,
    calls: int,
) -> dict[str, int]:
    return {
        "prompt_tokens": prompt,
        "prompt_cached_tokens": cached,
        "prompt_uncached_tokens": uncached,
        "completion_tokens": completion,
        "total_tokens": total,
        "calls": calls,
    }


async def record_usage(
    db: AsyncSession,
    *,
    model: str,
    prompt_tokens: int = 0,
    prompt_cached_tokens: int = 0,
    prompt_uncached_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    provider: str = "",
    session_id: str | None = None,
    agent_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """写入用量事件；调用方应吞掉异常以免影响主路径。"""
    prompt = int(prompt_tokens or 0)
    cached = int(prompt_cached_tokens or 0)
    uncached = int(prompt_uncached_tokens or 0)
    if uncached <= 0 and prompt > 0:
        uncached = max(0, prompt - cached)
    if prompt <= 0:
        prompt = cached + uncached
    completion = int(completion_tokens or 0)
    total = int(total_tokens or 0) or (prompt + completion)

    ev = LlmUsageEvent(
        id=uuid4(),
        created_at=datetime.utcnow(),
        model=normalize_model_name(model)[:128],
        provider=normalize_provider_name(provider, model=model)[:64],
        session_id=(session_id or None),
        agent_id=(agent_id or None),
        prompt_tokens=prompt,
        prompt_cached_tokens=cached,
        prompt_uncached_tokens=uncached,
        completion_tokens=completion,
        total_tokens=total,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    db.add(ev)
    await db.commit()


def record_usage_fire_and_forget(**kwargs: Any) -> None:
    """同步上下文尽力落库（Agent LLM 回调）。"""
    try:
        import asyncio

        from api_backend.database import get_session_factory

        async def _run() -> None:
            factory = get_session_factory()
            async with factory() as db:
                await record_usage(db, **kwargs)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            asyncio.run(_run())
    except Exception:
        logger.debug("LLM 用量写入跳过", exc_info=True)


def record_parsed_usage_fire_and_forget(
    raw_usage: Any,
    *,
    model: str,
    provider: str = "",
    session_id: str | None = None,
    agent_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """解析 usage 后 fire-and-forget 落库。"""
    parsed = parse_usage_details(raw_usage)
    if not any(
        parsed[k]
        for k in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cached_tokens",
        )
    ):
        return
    record_usage_fire_and_forget(
        model=model,
        provider=provider,
        session_id=session_id,
        agent_id=agent_id,
        prompt_tokens=parsed["prompt_tokens"],
        prompt_cached_tokens=parsed["prompt_cached_tokens"],
        prompt_uncached_tokens=parsed["prompt_uncached_tokens"],
        completion_tokens=parsed["completion_tokens"],
        total_tokens=parsed["total_tokens"],
        meta=meta,
    )


async def usage_summary(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=max(1, days))

    # 按 (provider, model) 聚合，便于「提供商/模型」展示与合并历史脏数据
    pair_q = await db.execute(
        select(
            LlmUsageEvent.provider,
            LlmUsageEvent.model,
            func.sum(LlmUsageEvent.prompt_tokens),
            func.sum(LlmUsageEvent.prompt_cached_tokens),
            func.sum(LlmUsageEvent.prompt_uncached_tokens),
            func.sum(LlmUsageEvent.completion_tokens),
            func.sum(LlmUsageEvent.total_tokens),
            func.count(),
        )
        .where(LlmUsageEvent.created_at >= since)
        .group_by(LlmUsageEvent.provider, LlmUsageEvent.model)
    )

    # 合并规范化后的模型 / 供应商
    model_acc: dict[str, dict[str, int]] = {}
    provider_acc: dict[str, dict[str, int]] = {}
    pair_acc: dict[tuple[str, str], dict[str, int]] = {}

    def _add(dst: dict[str, int], row_vals: tuple[int, int, int, int, int, int]) -> None:
        dst["prompt_tokens"] = dst.get("prompt_tokens", 0) + row_vals[0]
        dst["prompt_cached_tokens"] = dst.get("prompt_cached_tokens", 0) + row_vals[1]
        dst["prompt_uncached_tokens"] = dst.get("prompt_uncached_tokens", 0) + row_vals[2]
        dst["completion_tokens"] = dst.get("completion_tokens", 0) + row_vals[3]
        dst["total_tokens"] = dst.get("total_tokens", 0) + row_vals[4]
        dst["calls"] = dst.get("calls", 0) + row_vals[5]

    for row in pair_q.all():
        raw_provider, raw_model = row[0] or "", row[1] or ""
        model = normalize_model_name(raw_model)
        provider = normalize_provider_name(raw_provider, model=raw_model)
        vals = (
            int(row[2] or 0),
            int(row[3] or 0),
            int(row[4] or 0),
            int(row[5] or 0),
            int(row[6] or 0),
            int(row[7] or 0),
        )
        _add(model_acc.setdefault(model, {}), vals)
        _add(provider_acc.setdefault(provider, {}), vals)
        _add(pair_acc.setdefault((provider, model), {}), vals)

    def _sorted_rows(
        acc: dict[str, dict[str, int]], key_name: str
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for k, v in acc.items():
            items.append(
                {
                    key_name: k,
                    **_row_breakdown(
                        prompt=v.get("prompt_tokens", 0),
                        cached=v.get("prompt_cached_tokens", 0),
                        uncached=v.get("prompt_uncached_tokens", 0),
                        completion=v.get("completion_tokens", 0),
                        total=v.get("total_tokens", 0),
                        calls=v.get("calls", 0),
                    ),
                }
            )
        items.sort(key=lambda x: int(x["total_tokens"]), reverse=True)
        return items

    by_provider = _sorted_rows(provider_acc, "provider")

    # 每个模型取 token 最多的供应商，用于 label
    model_best_provider: dict[str, str] = {}
    for (prov, model), v in pair_acc.items():
        tok = v.get("total_tokens", 0)
        prev = model_best_provider.get(model)
        if prev is None:
            model_best_provider[model] = prov
            continue
        # 已有则比 token
        prev_tok = pair_acc.get((prev, model), {}).get("total_tokens", 0)
        if tok > prev_tok:
            model_best_provider[model] = prov

    by_model: list[dict[str, Any]] = []
    for k, v in model_acc.items():
        prov = model_best_provider.get(k, "unknown")
        by_model.append(
            {
                "model": k,
                "label": format_provider_model(prov, k),
                **_row_breakdown(
                    prompt=v.get("prompt_tokens", 0),
                    cached=v.get("prompt_cached_tokens", 0),
                    uncached=v.get("prompt_uncached_tokens", 0),
                    completion=v.get("completion_tokens", 0),
                    total=v.get("total_tokens", 0),
                    calls=v.get("calls", 0),
                ),
            }
        )
    by_model.sort(key=lambda x: x["total_tokens"], reverse=True)

    top_pair: dict[str, Any] | None = None
    if pair_acc:
        (prov, model), top_v = max(
            pair_acc.items(), key=lambda kv: kv[1].get("total_tokens", 0)
        )
        top_pair = {
            "provider": prov,
            "model": model,
            "label": format_provider_model(prov, model),
            "total_tokens": top_v.get("total_tokens", 0),
            "calls": top_v.get("calls", 0),
        }

    day_q = await db.execute(
        select(
            func.date(LlmUsageEvent.created_at),
            func.sum(LlmUsageEvent.prompt_cached_tokens),
            func.sum(LlmUsageEvent.prompt_uncached_tokens),
            func.sum(LlmUsageEvent.completion_tokens),
            func.sum(LlmUsageEvent.total_tokens),
            func.count(),
        )
        .where(LlmUsageEvent.created_at >= since)
        .group_by(func.date(LlmUsageEvent.created_at))
        .order_by(func.date(LlmUsageEvent.created_at))
    )
    day_rows = day_q.all()

    day_model_q = await db.execute(
        select(
            func.date(LlmUsageEvent.created_at),
            LlmUsageEvent.model,
            func.sum(LlmUsageEvent.total_tokens),
        )
        .where(LlmUsageEvent.created_at >= since)
        .group_by(func.date(LlmUsageEvent.created_at), LlmUsageEvent.model)
    )
    day_model_map: dict[str, dict[str, int]] = {}
    for d, model, tok in day_model_q.all():
        key = str(d)
        nm = normalize_model_name(model or "")
        bucket = day_model_map.setdefault(key, {})
        bucket[nm] = bucket.get(nm, 0) + int(tok or 0)

    by_day: list[dict[str, Any]] = []
    for row in day_rows:
        date_s = str(row[0])
        models = sorted(
            day_model_map.get(date_s, {}).items(), key=lambda x: x[1], reverse=True
        )
        top = models[:_TOP_MODELS_PER_DAY]
        rest = sum(t for _, t in models[_TOP_MODELS_PER_DAY:])
        by_model_day = [{"model": m, "total_tokens": t} for m, t in top]
        if rest > 0:
            by_model_day.append({"model": "其他模型", "total_tokens": rest})
        by_day.append(
            {
                "date": date_s,
                "prompt_cached_tokens": int(row[1] or 0),
                "prompt_uncached_tokens": int(row[2] or 0),
                "completion_tokens": int(row[3] or 0),
                "total_tokens": int(row[4] or 0),
                "calls": int(row[5] or 0),
                "by_model": by_model_day,
            }
        )

    heatmap: list[dict[str, Any]] = []
    calls_by_date = {d["date"]: d["calls"] for d in by_day}
    max_calls = max(calls_by_date.values(), default=0)
    day_count = max(1, days)
    for i in range(day_count - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date()
        key = str(d)
        calls = int(calls_by_date.get(key, 0))
        intensity = (calls / max_calls) if max_calls > 0 else 0.0
        heatmap.append({"date": key, "calls": calls, "intensity": round(intensity, 4)})

    recent = await db.execute(
        select(LlmUsageEvent)
        .where(LlmUsageEvent.created_at >= since)
        .order_by(LlmUsageEvent.created_at.desc())
        .limit(50)
    )
    recent_items = []
    for e in recent.scalars().all():
        model = normalize_model_name(e.model)
        provider = normalize_provider_name(e.provider or "", model=e.model)
        recent_items.append(
            {
                "id": str(e.id),
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "model": model,
                "provider": provider,
                "label": format_provider_model(provider, model),
                "session_id": e.session_id,
                "agent_id": e.agent_id,
                "prompt_tokens": e.prompt_tokens,
                "prompt_cached_tokens": e.prompt_cached_tokens,
                "prompt_uncached_tokens": e.prompt_uncached_tokens,
                "completion_tokens": e.completion_tokens,
                "total_tokens": e.total_tokens,
            }
        )

    totals = _empty_totals()
    for x in by_model:
        totals["prompt_tokens"] += x["prompt_tokens"]
        totals["prompt_cached_tokens"] += x["prompt_cached_tokens"]
        totals["prompt_uncached_tokens"] += x["prompt_uncached_tokens"]
        totals["completion_tokens"] += x["completion_tokens"]
        totals["total_tokens"] += x["total_tokens"]
        totals["calls"] += x["calls"]

    if top_pair and totals["total_tokens"] > 0:
        top_pair["share"] = round(
            int(top_pair["total_tokens"]) / int(totals["total_tokens"]), 4
        )
    elif top_pair:
        top_pair["share"] = 0.0

    return {
        "days": days,
        "totals": totals,
        "top": top_pair,
        "by_model": by_model,
        "by_provider": by_provider,
        "by_day": by_day,
        "heatmap": heatmap,
        "recent": recent_items,
    }
