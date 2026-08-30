"""clients 骨架测试(phase-11,§9.13):发现 services/*/service.json;连接池为空。"""

import json
from pathlib import Path

from agent.clients import McpClientPool, discover_services

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
        """空池是合法稳态:外接 MCP 是 11b,不往 Toolbelt 塞工具。"""
        pool = McpClientPool()
        assert pool.list_servers() == []
        assert pool.list_tools("notes") == []
