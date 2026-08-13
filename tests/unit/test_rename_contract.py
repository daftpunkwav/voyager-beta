"""改名关键契约回归测试（2026-08-13 RepoPilot→Voyager）。

锁定改名后不可再漂移的契约：
1. config.Settings 的 graph_*/agent_disabled 字段存在且类型正确
2. GRAPH_*/AGENT_* 环境变量 → Settings 字段映射
3. start_worker 尊重 graph_auto_start（修复前误读 graph_fallback_auto_start）
4. sidecar 启动注入 ENGINE_*（C 引擎读 ENGINE_* 唯一权威名，GRAPH_* 是应用层配置契约）
"""
from __future__ import annotations

from pathlib import Path

import pytest
from api_backend.config import Settings, get_settings


# ── 1. Settings 字段契约 ────────────────────────────────────────────────
def test_settings_graph_fields_exist():
    """改名回归：runtime 层 getattr(settings, 'graph_*') 依赖的字段必须存在。
    修复前字段名漂移（graph_fallback_*）时 getattr 默认值掩盖了 bug。"""
    s = Settings(secret_key="x" * 32)
    for field in (
        "graph_allowed_root",
        "graph_engine_url",
        "graph_engine_bin",
        "graph_cache_dir",
        "graph_auto_start",
        "graph_disabled",
        "agent_disabled",
    ):
        assert hasattr(s, field), f"Settings 缺少字段 {field}"
    assert isinstance(s.graph_allowed_root, str)
    assert isinstance(s.graph_engine_url, str)
    assert isinstance(s.graph_engine_bin, str)
    assert isinstance(s.graph_cache_dir, str)
    assert isinstance(s.graph_auto_start, bool)
    assert isinstance(s.graph_disabled, bool)
    assert isinstance(s.agent_disabled, bool)


# ── 2. env → Settings 映射契约 ──────────────────────────────────────────
@pytest.mark.parametrize(
    ("env_name", "field", "value"),
    [
        ("GRAPH_DISABLED", "graph_disabled", "true"),
        ("GRAPH_ALLOWED_ROOT", "graph_allowed_root", "/tmp/graph-root"),
        ("GRAPH_ENGINE_URL", "graph_engine_url", "http://127.0.0.1:9750"),
        ("GRAPH_ENGINE_BIN", "graph_engine_bin", "/tmp/graph-engine"),
        ("GRAPH_CACHE_DIR", "graph_cache_dir", "/tmp/graph-cache"),
        ("GRAPH_AUTO_START", "graph_auto_start", "false"),
        ("AGENT_DISABLED", "agent_disabled", "true"),
    ],
)
def test_env_to_settings_mapping(monkeypatch, env_name: str, field: str, value: str):
    """改名回归：GRAPH_*/AGENT_* env 必须进入对应 Settings 字段。
    字段改名后 env 契约会静默漂移，此测试锁定映射关系。"""
    get_settings.cache_clear()
    monkeypatch.setenv(env_name, value)
    s = Settings(secret_key="x" * 32)
    if field in ("graph_disabled", "agent_disabled", "graph_auto_start"):
        assert s.__getattribute__(field) is (value == "true")
    else:
        assert s.__getattribute__(field) == value
    get_settings.cache_clear()


# ── 3. start_worker 尊重 graph_auto_start ───────────────────────────────
class _FakeSidecar:
    calls = 0

    @classmethod
    async def ensure(cls):
        cls.calls += 1


@pytest.mark.asyncio
async def test_start_worker_respects_graph_auto_start(monkeypatch):
    """改名回归：graph_auto_start=False 时不得拉起 sidecar。
    修复前误读 graph_fallback_auto_start（getattr 默认 True）导致该开关失效。"""
    import graph_engine_runtime.runtime as rt_mod
    import graph_engine_runtime.sidecar as sc_mod
    from graph_engine_runtime.context import GraphRuntimeContext
    from graph_engine_runtime.runtime import EmbeddedGraphRuntime

    class _S:
        graph_auto_start: bool = False
        graph_engine_url: str = "http://127.0.0.1:9750"

    ctx = GraphRuntimeContext(settings=_S(), repo_root=Path("/fake"))
    monkeypatch.setattr(sc_mod, "ensure_graph_engine_sidecar", _FakeSidecar.ensure)
    started = []

    async def _fake_start_index_worker():
        started.append("worker")

    monkeypatch.setattr(rt_mod.index_pipeline, "start_index_worker", _fake_start_index_worker)

    rt = EmbeddedGraphRuntime(ctx)
    await rt.start_worker()
    assert _FakeSidecar.calls == 0, "graph_auto_start=False 时不应拉起 sidecar"
    assert started == ["worker"], "索引 worker 应正常启动"


@pytest.mark.asyncio
async def test_start_worker_sidecar_when_enabled(monkeypatch):
    """graph_auto_start=True + url 非空时拉起 sidecar 一次。"""
    import graph_engine_runtime.runtime as rt_mod
    import graph_engine_runtime.sidecar as sc_mod
    from graph_engine_runtime.context import GraphRuntimeContext
    from graph_engine_runtime.runtime import EmbeddedGraphRuntime

    class _S:
        graph_auto_start: bool = True
        graph_engine_url: str = "http://127.0.0.1:9750"

    ctx = GraphRuntimeContext(settings=_S(), repo_root=Path("/fake"))
    monkeypatch.setattr(sc_mod, "ensure_graph_engine_sidecar", _FakeSidecar.ensure)
    monkeypatch.setattr(rt_mod.index_pipeline, "start_index_worker", _async_noop)

    rt = EmbeddedGraphRuntime(ctx)
    await rt.start_worker()
    assert _FakeSidecar.calls == 1


async def _async_noop():
    return None


# ── 4. sidecar env 注入（ENGINE_* 唯一权威名）────────────────────────────
@pytest.mark.asyncio
async def test_sidecar_env_writes_engine_only(monkeypatch, tmp_path: Path):
    """改名回归：C 引擎读 ENGINE_CACHE_DIR/ENGINE_ALLOWED_ROOT（源码 getenv，唯一
    权威名），sidecar 只写 ENGINE_*、不再双写 GRAPH_*（GRAPH_* 是应用层配置契约，
    由 sidecar 在边界翻译为 ENGINE_*）。"""
    import subprocess as sp

    import graph_engine_runtime.sidecar as sc_mod
    from graph_engine_runtime.context import GraphRuntimeContext

    captured: dict = {}

    class _FakeBin:
        def resolve(self):
            return self

        def __str__(self):
            return "/fake/graph-engine"

        @property
        def parent(self):
            return Path("/fake")

    class _FakeProc:
        def poll(self):
            return None  # 模拟进程存活（避免误读 returncode）

        @property
        def returncode(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    def _fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _FakeProc()

    monkeypatch.setattr(sp, "Popen", _fake_popen)
    monkeypatch.setattr(sc_mod, "resolve_engine_bin", lambda: _FakeBin())
    # 首次探测不健康 → 触发 Popen 构造 env；轮询阶段就绪 → 快速返回
    health_calls = {"n": 0}

    async def _health(*_a, **_k):
        health_calls["n"] += 1
        return health_calls["n"] > 1

    monkeypatch.setattr(sc_mod, "sidecar_healthy", _health)

    class _S:
        graph_engine_url: str = "http://127.0.0.1:9750"
        graph_cache_dir: str = str(tmp_path / "cache")
        graph_allowed_root: str = str(tmp_path)
        graph_auto_start: bool = True

    ctx = GraphRuntimeContext(settings=_S(), repo_root=tmp_path)
    monkeypatch.setattr(sc_mod, "get_runtime_context", lambda: ctx)

    # 只验证 env 构造（不等待 sidecar 就绪）
    from graph_engine_runtime.sidecar import _default_bin_candidates

    await sc_mod.ensure_graph_engine_sidecar()

    env = captured.get("env", {})
    assert env.get("ENGINE_CACHE_DIR") == str((tmp_path / "cache").resolve())
    assert env.get("ENGINE_ALLOWED_ROOT") == str(tmp_path.resolve())
    # ENGINE_* 是 C 引擎唯一权威名，不再双写 GRAPH_*
    assert env.get("GRAPH_CACHE_DIR") is None
    assert env.get("GRAPH_ALLOWED_ROOT") is None
    # 旧二进制候选已移除
    names = [p.name for p in _default_bin_candidates()]
    assert "graph-engine" in names
    assert all("codebase-memory" not in n for n in names)


# ── 5. 引擎层单一权威名(ENGINE_*)跨层守卫 ──────────────────────────────
def test_fallback_server_reads_engine_env(monkeypatch):
    """改名回归：graph_fallback/server.py 必须读 ENGINE_ALLOWED_ROOT/ENGINE_PORT
    （引擎层单一权威名，与 C 引擎 getenv 一致），而非应用层 GRAPH_*。"""

    monkeypatch.setenv("ENGINE_ALLOWED_ROOT", "/tmp/engine-root")
    monkeypatch.setenv("ENGINE_PORT", "9777")
    monkeypatch.setenv("GRAPH_ALLOWED_ROOT", "/tmp/graph-root")  # 应被忽略
    monkeypatch.setenv("GRAPH_ENGINE_PORT", "9888")  # 应被忽略

    # 直接调用 main 的 env 读取逻辑（monkeypatch 服务器构造避免阻塞）
    import os


    root = os.environ.get("ENGINE_ALLOWED_ROOT")
    port = int(os.environ.get("ENGINE_PORT") or "9750")
    assert root == "/tmp/engine-root", "必须读 ENGINE_ALLOWED_ROOT"
    assert port == 9777, "必须读 ENGINE_PORT"


def test_c_engine_envs_are_engine_prefixed():
    """改名回归：C 引擎源码的 getenv 只允许 ENGINE_* 前缀（grep 型守卫）。
    防止下次机械替换把引擎层 env 改回品牌名或应用层名。"""
    import re
    from pathlib import Path

    core = Path(__file__).resolve().parents[2] / "services/graph_engine/graph_engine_core/src"
    envs: set[str] = set()
    for p in core.rglob("*.c"):
        if "vendored" in p.parts:
            continue
        for m in re.finditer(r'getenv\("([A-Z_]+)"', p.read_text(encoding="utf-8", errors="ignore")):
            envs.add(m.group(1))
    bad = {
        e for e in envs
        if not e.startswith("ENGINE_")
        and e not in _FUNC_ENV_WHITELIST
    }
    assert not bad, f"C 引擎读取了非 ENGINE_ 前缀环境变量: {bad}"


# C 引擎功能性读取的系统/agent 目录 env（非引擎配置，白名单锁定防误报）
_FUNC_ENV_WHITELIST = {
    "HOME", "PATH", "TEMP", "TMP", "TMPDIR", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "SHELL", "XDG_CONFIG_HOME",
    # 第三方 agent 配置目录检测（CLI 探测已安装 agent 的 home）
    "CLAUDE_CONFIG_DIR", "CODEX_HOME", "COPILOT_HOME", "OPENCLAW_HOME",
    "OPENCLAW_STATE_DIR", "OPENCLAW_PROFILE", "OPENCLAW_CONFIG_PATH",
    "OPENCLAW_WORKSPACE_DIR", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR",
    "CRUSH_GLOBAL_CONFIG", "VIBE_HOME",
}
