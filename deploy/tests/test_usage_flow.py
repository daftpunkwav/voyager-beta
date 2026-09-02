"""对话计量链路集成:agent 推理经 llm.complete 能力 -> usage 表累计 ->
get_usage_stats 汇总非零。

注入方式(对应阶段手册坑 1"绕过能力直连 client 会漏计量"):
不用 build(llm=FakeLLM)(那会让 agent 绕过 llm 服务能力,漏计量),
而是替换服务内底层 client 返回固定补全——能力守卫链与计量直写全真。

以上仅指 llm 服务 usage 表口径(下 TestUsageMetering);phase-65 起另有
TestResourceQuotaFlow 断言 agent 进程内 Meter 口径,那一条链不经 llm
服务能力,反用 build(llm=FakeLLM) 注入,两条流水不合并(§9.9 任务书钉死)。
"""

import time

import pytest
from fastapi.testclient import TestClient

from agent.llm import FakeLLM, LLMReply, Usage
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


class TestResourceQuotaFlow:
    def test_get_resource_quota_grows_with_chat(self, tmp_path) -> None:
        """agent Meter 配额能力随对话增长(phase-65,§9.9 资源维):
        build(llm=FakeLLM) 注入的 client 仍经 build_agent 的 metered_llm 包装,
        每轮 complete 的 usage 计入当日用量,get_resource_quota 读同一份 Meter。

        注意口径:这里断言的是 agent Meter(进程内),与上面 TestUsageMetering
        断言的 llm 服务 usage 表(经 llm.complete 能力持久化)是两条独立流水,
        不合并(任务书钉死)。"""
        llm = FakeLLM(dynamic=lambda m, t: LLMReply(
            text="好的。", usage=Usage(input_tokens=12, output_tokens=6)
        ))
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        with TestClient(app) as client:
            # 配额设为大数,避免对话中途被拦(user_only 项;测试身份即本机用户)
            r = client.post("/api/agent/capabilities/set_setting",
                            json={"key": "agent.resource.daily_tokens",
                                  "value": 1_000_000})
            assert r.status_code == 200

            client.post("/api/chat/messages", json={"content": "在吗"})

            # agent 处理是异步的:轮询等 meter 计入
            deadline = time.time() + 8
            quota = {}
            while time.time() < deadline:
                quota = client.post("/api/agent/capabilities/get_resource_quota",
                                    json={}).json()["result"]
                if quota.get("tokens_used_today", 0) > 0:
                    break
                time.sleep(0.05)
            assert quota["tokens_used_today"] >= 18, f"配额未随对话增长: {quota}"
            assert quota["daily_tokens"] == 1_000_000  # 热读设置生效
