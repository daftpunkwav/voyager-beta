"""code-exec 服务设置项(§8.5):运行时镜像、资源限额与网络开关。

语言环境为数据;新增运行时只需改设置,不改动代码。
设置键使用 code_exec 下划线形式(§13.3 命名中性,且点分键只允许下划线)。
"""

from platform_settings import SettingDef, SettingType

_DEF_RUNTIMES = [
    {
        "id": "python",
        "name": "Python 3",
        "image": "python:3.11-slim",
        "file_ext": ".py",
        "cmd": ["python"],
    },
    {
        "id": "node",
        "name": "Node.js 20",
        "image": "node:20-slim",
        "file_ext": ".js",
        "cmd": ["node"],
    },
    {
        "id": "shell",
        "name": "Shell (bash)",
        "image": "bash:5.2",
        "file_ext": ".sh",
        "cmd": ["bash"],
    },
]

DEFS = [
    SettingDef(
        key="code_exec.runtimes",
        module="code_exec",
        type=SettingType.JSON,
        default=_DEF_RUNTIMES,
        description="可用运行时清单(id/name/image/file_ext/cmd)",
    ),
    SettingDef(
        key="code_exec.timeout_seconds",
        module="code_exec",
        type=SettingType.INT,
        default=60,
        min=1,
        max=3600,
        description="单次执行超时(秒)",
    ),
    SettingDef(
        key="code_exec.memory_mb",
        module="code_exec",
        type=SettingType.INT,
        default=512,
        min=64,
        max=8192,
        description="容器内存限额(MB)",
    ),
    SettingDef(
        key="code_exec.network",
        module="code_exec",
        type=SettingType.BOOL,
        default=False,
        description="默认是否允许容器出网(显式开通除外)",
    ),
    SettingDef(
        key="code_exec.use_host",
        module="code_exec",
        type=SettingType.BOOL,
        default=True,
        description="无 docker 时回退到宿主进程(开发/测试用)",
    ),
]
