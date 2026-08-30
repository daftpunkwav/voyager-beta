"""clients 测试(§9.13):发现 services/*/service.json;外接 MCP 配置校验与空池。"""

import json
from pathlib import Path

import pytest

from agent.clients import McpClientPool, discover_services, validate_server_config

REPO_ROOT = Path(__file__).parents[2]


class TestDiscovery:
    def test_discovers_real_services(self) -> None:
        cards = discover_services(REPO_ROOT / "services")
        names = {c["name"] for c in cards}
        assert "notes" in names
        assert "_template" not in names  # 下划线目录不是服务
        notes = next(c for c in cards if c["name"] == "notes")
        assert notes["port"] == 8020  # 模块卡字段原样透出

    def test_template_and_missing_card_skipped(self, tmp_path) -> None:
        good = tmp_path / "alpha"
        good.mkdir()
        (good / "service.json").write_text(
            json.dumps({"name": "alpha", "port": 1}), encoding="utf-8"
        )
        (tmp_path / "_template").mkdir()
        (tmp_path / "empty").mkdir()  # 有目录无卡:跳过不炸
        assert [c["name"] for c in discover_services(tmp_path)] == ["alpha"]

    def test_bad_json_skipped(self, tmp_path) -> None:
        bad = tmp_path / "beta"
        bad.mkdir()
        (bad / "service.json").write_text("{broken", encoding="utf-8")
        assert discover_services(tmp_path) == []


class TestPool:
    def test_pool_starts_empty(self) -> None:
        """空池是合法稳态:没有外接 MCP 配置时 list_state 为空,不往 Toolbelt 塞工具。"""
        pool = McpClientPool()
        assert pool.list_state() == []
        assert pool.configs() == []

    def test_validate_rejects_bad_config(self) -> None:
        """非法配置(id 形状 / file: URL / 空 command)在入口即拒。"""
        from platform_contracts import ServiceError

        with pytest.raises(ServiceError):
            validate_server_config({"id": "Bad_Id", "kind": "stdio", "command": "npx"})
        with pytest.raises(ServiceError):
            validate_server_config({"id": "ok", "kind": "url", "url": "file:///etc"})
        with pytest.raises(ServiceError):
            validate_server_config({"id": "ok", "kind": "stdio", "command": ""})
        # 合法形状:normalize 后字段齐全
        cfg = validate_server_config(
            {"id": "demo", "kind": "stdio", "command": "npx", "args": ["-y", "x"]}
        )
        assert cfg["name"] == "demo" and cfg["approval"] == "item" and cfg["enabled"]
