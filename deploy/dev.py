"""开发启动:backend(uvicorn :8000)+ web(vite :5173)。Ctrl+C 同退。

运行:仓库根 `python deploy/dev.py`。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _stop_tree(proc: subprocess.Popen) -> None:
    """终止进程树。Windows 下 shell=True 起的是 cmd.exe,node/npm 是其子进程,
    仅 terminate() 会留孤儿;taskkill /T 连子进程一起杀。"""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        proc.terminate()


def main() -> None:
    import uvicorn

    # Windows 下 npm 需要 shell=True
    web = subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "apps" / "web", shell=True)
    try:
        uvicorn.run("deploy.backend:build", factory=True, host="127.0.0.1",
                    port=8000, reload=False)
    finally:
        _stop_tree(web)


if __name__ == "__main__":
    main()
