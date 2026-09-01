"""phase-39:lifespan 里 mcp.start() 后台挂载,不挡 gateway ready。

慢 start(monkeypatch sleep 2s)下 TestClient 进入仍 <1s、/health 六域 up;
shutdown 时 cancel + await 干净收尾,不泄漏 pending task。
"""

import asyncio
import time

from fastapi.testclient import TestClient

from agent.clients.pool import McpClientPool
from deploy.backend import build

DOMAINS = {"llm", "sources", "notes", "graph", "settings", "agent"}


def test_slow_mcp_start_does_not_block_ready(tmp_path, monkeypatch) -> None:
    """start 慢连 2s:gateway 进入 <1s 即 ready;/health 正常;退出干净取消。"""
    cancelled: list[bool] = []

    async def slow_start(self) -> None:
        self._started = True  # 保持幂等语义
        try:
            await asyncio.sleep(2)  # 模拟慢 preview(单台 CONNECT_TIMEOUT=15s)
        except asyncio.CancelledError:
            cancelled.append(True)  # shutdown 走 cancel 而非等满 2s
            raise

    monkeypatch.setattr(McpClientPool, "start", slow_start)

    app = build(tmp_path / "data", tmp_path / "ws")
    t0 = time.monotonic()
    with TestClient(app) as client:
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"TestClient 进入耗时 {elapsed:.2f}s,start 挡住了 ready"
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert DOMAINS <= set(body["services"])
        assert all(s["status"] == "up" for s in body["services"].values())
    # 退出 with 不抛 = shutdown 干净;后台任务是被取消的,不是等完 2s
    assert cancelled == [True]
