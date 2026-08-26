"""code-exec 执行器:容器优先,无 docker 时回退宿主进程。

产物目录挂载 workspace/sandbox/;网络默认关闭。一次性执行,不持久环境状态(§8.5)。
运行时配置来自设置(数据侧),执行前一律过白名单校验,防配置注入执行参数。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "code-exec"

# 镜像名/命令 token 白名单:覆盖 docker 引用与常见参数字符,
# 显式排除空格与 ;|$`&()<> 等 shell/注入元字符。
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]*$")
_CMD_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/@:=,+-]+$")
_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,10}$")

# 宿主回退仅放行已知解释器;自定义运行时必须走容器。
_HOST_INTERPRETERS: dict[str, list[str]] = {
    "python": ["python"],
    "node": ["node"],
    "shell": ["bash"],
}


def _validate_runtime(runtime: dict[str, Any]) -> None:
    """校验运行时配置字段;任一非法即拒绝执行(INVALID_INPUT)。"""
    image = str(runtime.get("image") or "")
    if not _IMAGE_RE.match(image):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"非法运行时镜像名: {image!r}")
    cmd = runtime.get("cmd")
    if (not isinstance(cmd, list) or not cmd
            or not all(isinstance(c, str) and _CMD_TOKEN_RE.match(c) for c in cmd)):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"非法运行时命令清单: {cmd!r}")
    ext = str(runtime.get("file_ext") or "")
    if not _EXT_RE.match(ext):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"非法文件后缀: {ext!r}")


@dataclass
class RunResult:
    """执行结果:退出码、输出、产物目录。"""

    status: str
    exit_code: int
    stdout: str
    stderr: str
    artifact_dir: str


async def run_in_runtime(
    runtime: dict[str, Any],
    code: str,
    *,
    timeout: int,
    memory_mb: int,
    network: bool,
    use_host_fallback: bool,
    workspace: Path,
) -> RunResult:
    """按运行时配置执行代码片段。

    容器沙箱为最终形态(§8.5)。当前实现:
    - docker 可用时,起一次性容器运行;
    - 否则在 use_host_fallback=True 时于宿主起一个受限子进程(开发/测试用),
      同时 stderr 打印一条警告,提醒生产环境应启用容器。
    """
    _validate_runtime(runtime)
    exec_id = uuid.uuid4().hex[:12]
    artifact_dir = workspace / "sandbox" / "artifacts" / exec_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ext = runtime.get("file_ext", ".txt")
    src = artifact_dir / f"main{ext}"
    src.write_text(code, encoding="utf-8")

    has_docker = shutil.which("docker") is not None
    if has_docker:
        return await _run_docker(
            runtime, src, artifact_dir, timeout=timeout,
            memory_mb=memory_mb, network=network,
        )
    if use_host_fallback:
        return await _run_host(runtime, src, artifact_dir, timeout=timeout)
    return RunResult(
        status="failed",
        exit_code=-1,
        stdout="",
        stderr="docker 不可用且 host 回退已关闭;无法执行代码",
        artifact_dir=str(artifact_dir),
    )


async def _run_docker(
    runtime: dict[str, Any],
    src: Path,
    artifact_dir: Path,
    *,
    timeout: int,
    memory_mb: int,
    network: bool,
) -> RunResult:
    image = runtime["image"]
    cmd = runtime.get("cmd", [])
    args = [
        "docker", "run", "--rm",
        "--network", "host" if network else "none",
        "-m", f"{memory_mb}m",
        "-v", f"{artifact_dir}:/workspace",
        "-w", "/workspace",
        image,
        *cmd, "main" + src.suffix,
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return RunResult(
            status="timeout", exit_code=-1,
            stdout="", stderr="执行超时",
            artifact_dir=str(artifact_dir),
        )
    return RunResult(
        status="completed" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode or 0,
        stdout=stdout_b.decode(errors="replace"),
        stderr=stderr_b.decode(errors="replace"),
        artifact_dir=str(artifact_dir),
    )


async def _run_host(
    runtime: dict[str, Any],
    src: Path,
    artifact_dir: Path,
    *,
    timeout: int,
) -> RunResult:
    interpreter = str(runtime.get("id") or "")
    args = _HOST_INTERPRETERS.get(interpreter)
    if args is None:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            f"宿主回退仅支持 {'/'.join(_HOST_INTERPRETERS)} 运行时"
            f"(自定义运行时需 docker): {interpreter}",
        )
    args = [*args, str(src)]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(artifact_dir),
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return RunResult(
            status="timeout", exit_code=-1,
            stdout="", stderr="执行超时",
            artifact_dir=str(artifact_dir),
        )
    warning = (
        "WARN: 当前以宿主进程回退执行,未启用容器沙箱;"
        "生产环境请安装 docker 并关闭 use_host 回退。\n"
    )
    return RunResult(
        status="completed" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode or 0,
        stdout=stdout_b.decode(errors="replace"),
        stderr=warning + stderr_b.decode(errors="replace"),
        artifact_dir=str(artifact_dir),
    )
