"""对话计量链路集成:agent 推理经 llm.complete 能力 -> usage 表累计 ->
get_usage_stats 汇总非零。

注入方式(对应阶段手册坑 1"绕过能力直连 client 会漏计量"):
不用 build(llm=FakeLLM)(那会让 agent 绕过 llm 服务能力,漏计量),
而是替换服务内底层 client 返回固定补全——能力守卫链与计量直写全真。
"""

import time

import pytest
from fastapi.testclient import TestClient

from deploy.backend import build


@pytest.fixture()
def stub_llm_client(monkeypatch):
    """替换 services/llm 直连 client:不触网,返回固定补全(经能力计量)。"""
    from services.llm import capabilities as llm_caps
    from services.llm.client import CompleteResult

    hits: list[str] = []

    async def fake_complete(provider, *, api_key, model, messages,
                            max_tokens=4096, temperature=0.7, tools=None):
        hits.append(model)
        return CompleteResult(text="好的。", input_tokens=12, output_tokens=6,
                              model=model, tool_calls=())

    monkeypatch.setattr(llm_caps, "llm_complete", fake_complete)
    return hits


class TestUsageMetering:
    def test_two_turns_metered_through_capability(self, tmp_path, monkeypatch,
                                                  stub_llm_client) -> None:
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "usage-test-material")
        app = build(tmp_path / "data", tmp_path / "ws")
        with TestClient(app) as client:
            # 配一个可用提供商:元数据经能力写,key 仅用户本人(铁律 7)
            pid = client.post("/api/llm/capabilities/add_provider", json={
                "display_name": "计量测试", "base_url": "http://127.0.0.1:9",
                "api_format": "chat", "models": ["meter-model"],
            }).json()["result"]["id"]
            resp = client.post("/api/llm/capabilities/set_api_key", json={
                "provider_id": pid, "api_key": "sk-meter",
            })
            assert resp.status_code == 200

            # 两轮对话:agent 的全部推理经 ServiceLLM -> llm.complete 能力
            for _ in range(2):
                r = client.post("/api/chat/messages", json={"content": "在吗"})
                assert r.status_code in (200, 202)

            deadline = time.time() + 8
            stats = {}
            while time.time() < deadline:
                stats = client.post("/api/llm/capabilities/get_usage_stats",
                                    json={"days": 30}).json()["result"]
                if stats.get("calls", 0) >= 2:
                    break
                time.sleep(0.05)
            assert stats.get("calls", 0) >= 2, f"计量未累计: {stats}"
            assert stats["input_tokens"] >= 24  # 每轮至少 12 输入 token
            assert stats["output_tokens"] >= 12
            models = {m["model"] for m in stats["by_model"]}
            assert "meter-model" in models  # 按模型分组可用(用量页表数据源)
            assert len(stub_llm_client) >= 2  # 底层确实被调,链路闭合
