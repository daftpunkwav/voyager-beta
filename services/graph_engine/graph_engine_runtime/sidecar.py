"""
图谱 C 引擎 sidecar 生命周期：健康检查与按需拉起本仓 graph-engine。
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from graph_engine_runtime.context import get_runtime_context

logger = logging.getLogger(__name__)

_proc: Optional[subprocess.Popen] = None


def _default_bin_candidates() -> list[Path]:
    base = (
        get_runtime_context().repo_root
        / "services"
        / "graph_engine"
        / "graph_engine_core"
        / "build"
        / "c"
    )
    names = (
        "graph-engine.exe",
        "graph-engine",
    )
    return [base / n for n in names]


def resolve_engine_bin() -> Optional[Path]:
    """解析可执行文件：GRAPH_ENGINE_BIN > 约定构建产物路径。"""
    settings = get_runtime_context().settings
    configured = (settings.graph_engine_bin or "").strip()
    if configured:
        p = Path(configured)
        if p.is_file():
            return p.resolve()
        logger.warning("GRAPH_ENGINE_BIN 不存在：%s", configured)
    for cand in _default_bin_candidates():
        if cand.is_file():
            return cand.resolve()
    return None


def _port_from_url(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port:
        return int(parsed.port)
    return 9750


async def sidecar_healthy(base_url: str, *, timeout: float = 2.0) -> bool:
    """与 GraphEngineClient 一致：原生引擎用 /api/ui-config，自研用 /health。"""
    base = (base_url or "").rstrip("/")
    if not base:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for path in ("/api/ui-config", "/health"):
                try:
                    resp = await client.get(f"{base}{path}")
                    if resp.status_code == 200:
                        return True
                except Exception:
                    continue
    except Exception:
        return False
    return False


async def ensure_graph_engine_sidecar() -> bool:
    """若配置了引擎 URL 且不健康，尝试拉起本仓二进制。返回是否最终健康。"""
    global _proc
    ctx = get_runtime_context()
    settings = ctx.settings
    url = (settings.graph_engine_url or "").strip()
    if not url:
        return False
    if await sidecar_healthy(url):
        return True

    bin_path = resolve_engine_bin()
    if not bin_path:
        logger.info(
            "图谱 sidecar 不健康且未找到 graph-engine 二进制；将回退进程内 Python（若可用）"
        )
        return False

    port = _port_from_url(url)
    cache_dir = Path(
        settings.graph_cache_dir
        or (ctx.repo_root / "data" / "graph-engine-cache")
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    allowed = settings.graph_allowed_root or str(
        ctx.repo_root / "data"
    )

    env = os.environ.copy()
    # C 引擎源码内 getenv 读取 ENGINE_CACHE_DIR / ENGINE_ALLOWED_ROOT（唯一权威名）。
    # GRAPH_* 是应用层配置契约（config.py / .env），由本适配器在"应用配置 → 引擎
    # 进程 env"边界翻译为 ENGINE_*；不做双写，避免两套名字漂移失配。
    env["ENGINE_CACHE_DIR"] = str(cache_dir.resolve())
    env["ENGINE_ALLOWED_ROOT"] = str(Path(allowed).resolve())

    cmd = [
        str(bin_path),
        f"--port={port}",
    ]
    logger.info("启动图谱 C 引擎：%s（port=%s cache=%s）", bin_path, port, cache_dir)
    try:
        # Windows：CREATE_NEW_PROCESS_GROUP 便于后续终止；Unix：start_new_session
        kwargs: dict = {
            "env": env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "cwd": str(bin_path.parent),
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        _proc = subprocess.Popen(cmd, **kwargs)
    except Exception as exc:
        logger.warning("拉起图谱引擎失败：%s", exc)
        _proc = None
        return False

    for _ in range(40):
        await asyncio.sleep(0.5)
        if await sidecar_healthy(url):
            logger.info("图谱 C 引擎已就绪：%s", url)
            return True
        if _proc.poll() is not None:
            logger.warning("图谱引擎进程已退出 code=%s", _proc.returncode)
            break
    logger.warning("等待图谱引擎就绪超时：%s", url)
    return False


async def stop_graph_engine_sidecar() -> None:
    """仅终止由本进程拉起的 sidecar（不杀用户自启的外部引擎）。"""
    global _proc
    if _proc is None:
        return
    try:
        if _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _proc.kill()
    except Exception:
        logger.debug("停止图谱 sidecar 时忽略异常", exc_info=True)
    finally:
        _proc = None
