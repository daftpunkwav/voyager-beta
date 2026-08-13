"""图谱适配层与流水线纯函数测试。"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from api_backend.services.index_data_adapter import adapt_layout
from graph_engine_runtime.index_pipeline import (
    _allowed_root,
    _build_credential_args,
    _git_pull,
    _git_shallow_clone,
    engine_project_name,
    parse_github_owner_repo,
)
from py_shared import error_codes as EC
from py_shared.exceptions import AppException


def test_parse_github_owner_repo():
    assert parse_github_owner_repo("https://github.com/foo/bar") == ("foo", "bar")
    assert parse_github_owner_repo("https://github.com/foo/bar.git") == ("foo", "bar")
    assert parse_github_owner_repo("git@github.com:acme/demo.git") == ("acme", "demo")


def test_engine_project_name():
    name = engine_project_name("Foo Org", "my repo!")
    assert name.startswith("graph-")
    assert " " not in name
    assert "rp-" not in name


def test_adapt_layout_maps_nodes_and_edges():
    raw = {
        "nodes": [
            {
                "id": 1,
                "x": 10,
                "y": 20,
                "z": 30,
                "label": "Function",
                "name": "hello",
                "file_path": "a.py",
                "qualified_name": "mod.hello",
                "size": 2,
                "color": "#00ff00",
                "status": "normal",
                "in_calls": 3,
            }
        ],
        "edges": [{"source": 1, "target": 1, "type": "CALLS"}],
        "total_nodes": 100,
    }
    data = adapt_layout(raw)
    assert data.stats.node_count == 1
    assert data.stats.total_nodes == 100
    assert data.nodes[0].kind == "Function"
    assert data.nodes[0].qualified_name == "mod.hello"
    assert data.edges[0].relation == "CALLS"
    assert data.edges[0].source == "1"


def test_parse_invalid_url_raises():
    with pytest.raises(ValueError):
        parse_github_owner_repo("https://example.com/not-github")


def test_git_shallow_clone_token_not_in_cmdline_and_helper_order(
    monkeypatch, tmp_path: Path
):
    """SEC-003 回归（纯逻辑，不依赖真实 git）：token 只经 env 注入绝不进
    命令行；-c 是累加语义，必须先清空系统级 helper 再注入内联 helper。
    """
    dest = tmp_path / "repo"
    url = "https://github.com/octocat/Hello-World"
    captured: dict = {}

    async def _fake_run_cmd(cmd, *, check=True, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        raise AssertionError("测试不应真正执行 git clone")

    monkeypatch.setattr("graph_engine_runtime.index_pipeline._run_cmd", _fake_run_cmd)

    with pytest.raises(AssertionError):
        asyncio.run(_git_shallow_clone(url, dest, token="ghp_TEST_TOKEN"))

    cmd = captured["cmd"]
    assert cmd, "应已构造 clone 命令"
    joined = " ".join(cmd)
    assert "ghp_TEST_TOKEN" not in joined, "token 不得进入命令行参数"
    assert captured["env"]["GRAPH_GIT_TOKEN"] == "ghp_TEST_TOKEN"

    # 注入的内联 helper（值含 $GRAPH_GIT_TOKEN 展开），与清空条目区分
    helper_entries = [
        c for c in cmd
        if c.startswith("credential.helper=") and "$GRAPH_GIT_TOKEN" in c
    ]
    assert len(helper_entries) == 1, "应注入唯一的内联 credential helper"
    idx = cmd.index(helper_entries[0])
    assert cmd.index("credential.helper=") < idx, "注入前必须先清空既有 helper"


@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="本机无 git，跳过 helper 语法离线验证",
)
def test_git_shallow_clone_helper_works_offline():
    """内联 credential helper 语法在本机 git（含 Git for Windows 默认 manager
    helper）下可用：`git credential fill` 离线验证（不联网，免 PAT 依赖）。
    复用生产函数 `_build_credential_args` 构造，避免测试复制实现。
    """
    credential_args, env = _build_credential_args("ghp_TEST_TOKEN")
    helper_entry = next(
        c for c in credential_args if "$GRAPH_GIT_TOKEN" in c
    )
    helper = helper_entry.removeprefix("credential.helper=")
    payload = "protocol=https\nhost=github.com\n\n"
    got = subprocess.run(
        [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            f"credential.helper={helper}",
            "credential",
            "fill",
        ],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert got.returncode == 0, f"credential fill 失败: {got.stderr}"
    assert "username=x-access-token" in got.stdout
    assert "password=ghp_TEST_TOKEN" in got.stdout


def test_git_shallow_clone_anonymous_no_helper(monkeypatch, tmp_path: Path):
    """匿名 clone（无 token）不进 credential helper 分支。"""
    dest = tmp_path / "repo"
    captured: dict = {}

    async def _fake_run_cmd(cmd, *, check=True, env=None):
        captured["cmd"] = cmd
        raise AssertionError("测试不应真正执行 git clone")

    monkeypatch.setattr("graph_engine_runtime.index_pipeline._run_cmd", _fake_run_cmd)

    with pytest.raises(AssertionError):
        asyncio.run(_git_shallow_clone("https://github.com/octocat/Hello-World", dest))

    assert "credential.helper" not in " ".join(captured["cmd"])


def test_git_pull_passes_token_via_env(monkeypatch, tmp_path: Path):
    """SEC-001 回归：refresh 路径 `_git_pull` 同样注入 credential helper，
    token 只经 env 传递，不进命令行（与 clone 路径一致）。
    """
    dest = tmp_path / "repo"
    captured: dict = {}

    async def _fake_run_cmd(cmd, *, check=True, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        raise AssertionError("测试不应真正执行 git fetch")

    monkeypatch.setattr("graph_engine_runtime.index_pipeline._run_cmd", _fake_run_cmd)

    with pytest.raises(AssertionError):
        asyncio.run(_git_pull(dest, token="ghp_TEST_TOKEN"))

    cmd = captured["cmd"]
    assert cmd, "应已构造 fetch 命令"
    joined = " ".join(cmd)
    assert "ghp_TEST_TOKEN" not in joined, "token 不得进入命令行参数"
    assert captured["env"]["GRAPH_GIT_TOKEN"] == "ghp_TEST_TOKEN"

    helper_entries = [
        c for c in cmd
        if c.startswith("credential.helper=") and "$GRAPH_GIT_TOKEN" in c
    ]
    assert len(helper_entries) == 1, "应注入唯一的内联 credential helper"
    idx = cmd.index(helper_entries[0])
    assert cmd.index("credential.helper=") < idx, "注入前必须先清空既有 helper"


@pytest.mark.parametrize(
    "url",
    [
        # 直接内网/元数据 IP
        "https://169.254.169.254/github.com/foo/bar",
        "https://10.0.0.1/foo/bar",
        # userinfo 欺骗：host 实际是 evil.com
        "https://github.com@evil.com/foo/bar",
        # 后缀/前缀混淆
        "https://github.com.evil.com/foo/bar",
        "https://notgithub.com/foo/bar",
        # 非 https scheme
        "http://github.com/foo/bar",
        "git://github.com/foo/bar",
        # 回环 / IPv6 回环
        "https://localhost/foo/bar",
        "https://[::1]/foo/bar",
        # 任意外部 host
        "https://evil.com/foo/bar",
    ],
    ids=[
        "meta-ip", "private-ip", "userinfo", "suffix", "prefix",
        "http-scheme", "git-scheme", "localhost", "ipv6-loopback", "external",
    ],
)
def test_git_shallow_clone_rejects_ssrf(tmp_path: Path, url: str):
    """SEC-007 回归（参数化）：各类 SSRF 绕过变体在入口即被拒绝，不执行 git clone。"""
    dest = tmp_path / "repo"
    with pytest.raises(AppException) as exc:
        asyncio.run(_git_shallow_clone(url, dest))
    assert exc.value.detail["code"] == EC.PROJECT_URL_INVALID


def test_allowed_root_reads_graph_allowed_root(monkeypatch):
    """改名回归：_allowed_root 必须读取 settings.graph_allowed_root。
    修复前曾误读 graph_fallback_allowed_root（不存在）导致 Path(None) 崩溃。
    用 monkeypatch 直接设置模块内 _global，测试后自动恢复原 context。"""
    from dataclasses import dataclass

    import graph_engine_runtime.context as ctx_mod
    from graph_engine_runtime.context import GraphRuntimeContext

    @dataclass
    class _FakeSettings:
        graph_allowed_root: str = "/fake/data"

    monkeypatch.setattr(
        ctx_mod,
        "_global",
        GraphRuntimeContext(
            settings=_FakeSettings(),
            repo_root=Path("/fake/repo"),
        ),
    )
    assert _allowed_root() == Path("/fake/data")
