"""API → Agent 独立进程 SSE 代理。"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator
from uuid import UUID

import httpx
from api_backend.config import get_settings

logger = logging.getLogger(__name__)


async def proxy_agent_chat_sse(
    *,
    session_id: UUID,
    message: str,
    project_id: UUID | None = None,
) -> AsyncIterator[bytes]:
    """将对话转发到 AGENT_BASE_URL，透传 SSE 字节流。"""
    settings = get_settings()
    base = (settings.agent_base_url or "").rstrip("/")
    token = (settings.agent_internal_token or "").strip()
    if not base or not token:
        raise RuntimeError("agent_base_url / agent_internal_token 未配置")

    url = f"{base}/v1/sessions/{session_id}/chat"
    headers = {
        "X-Agent-Internal-Token": token,
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "message": message,
    }
    if project_id is not None:
        payload["project_id"] = str(project_id)

    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")[:500]
                logger.error("agent proxy HTTP %s: %s", resp.status_code, body)
                _err = json.dumps(
                    {'code': 'AGENT_PROXY_ERROR', 'message': f'Agent 进程返回 HTTP {resp.status_code}'},
                    ensure_ascii=False,
                )
                yield ('event: error' + chr(10) + 'data: ' + _err + chr(10) + chr(10)).encode('utf-8')
                return
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk
