"""文件工具(fs jail,§9.9/§9.10)与 agent 默认工作目录(§9.10)。

双层防护:本模块内部强制 jail(路径必须落在 roots 内),
外层 Toolbelt 再过 PolicyEngine 四维判定。
附加只读根(phase-53,§9.9):read_roots 仅对读工具(read_file/list_dir)
放行,写/删仍限 roots——与 policy 层(_decide_fs)同语义,双层一致。
jail 内的 skills/ 子树对写/删类 fs 工具只读(phase-32):禁写禁删由
policy 层(_decide_fs)执行,read_file / list_dir 仍可;不在 handler 里再拦,
避免和 L2 确认顺序打架。SkillOrganizer 经用户确认后直写磁盘不受影响。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agent.tools.base import AgentTool

#: agent 默认工作目录的自建分类(§9.10)
DEFAULT_CATEGORIES = ("repo", "books", "news", "exports", "imports", "sandbox")


def ensure_workdir(root: str | Path) -> Path:
    """确保 agent 默认工作目录与分类子目录存在。"""
    root = Path(root)
    for category in DEFAULT_CATEGORIES:
        (root / category).mkdir(parents=True, exist_ok=True)
    return root


def fs_tools(
    roots: list[str | Path],
    read_roots: list[str | Path] | None = None,
    *,
    read_roots_fn: Callable[[], list[str | Path]] | None = None,
) -> dict[str, AgentTool]:
    """生成 jailed 文件工具组。roots 之外的路径一律拒绝;
    read_roots 仅放宽读工具的 jail 判定(写/删仍限 roots)。
    read_roots_fn 优先(热读 settings 时用),与 policy._fs_policy 同语义。"""
    jail = [Path(r).resolve() for r in roots]

    def _extra_read_roots() -> list[Path]:
        raw = read_roots_fn() if read_roots_fn is not None else (read_roots or ())
        return [Path(r).resolve() for r in raw]

    def _resolve(path: str, *, allow_read_roots: bool = False) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = jail[0] / candidate
        resolved = candidate.resolve()
        allowed = jail + (_extra_read_roots() if allow_read_roots else [])
        if not any(resolved == r or r in resolved.parents for r in allowed):
            raise ValueError(f"路径在工作目录之外: {resolved}")
        return resolved

    def read_file(path: str, max_chars: int = 8000) -> str:
        text = _resolve(path, allow_read_roots=True).read_text(encoding="utf-8", errors="replace")
        return text if len(text) <= max_chars else text[:max_chars] + "\n…[截断]"

    def write_file(path: str, content: str) -> dict:
        target = _resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"written": str(target), "chars": len(content)}

    def list_dir(path: str = ".") -> list[str]:
        target = _resolve(path, allow_read_roots=True)
        return sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())

    def delete_file(path: str) -> dict:
        target = _resolve(path)
        target.unlink()
        return {"deleted": str(target)}

    return {
        "read_file": AgentTool(
            name="read_file",
            description="读工作目录内文件文本(截断 8000 字)",
            handler=read_file,
            dimension="fs",
            schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
        "write_file": AgentTool(
            name="write_file",
            description="在工作目录内写文件(自动建父目录)",
            handler=write_file,
            dimension="fs",
            write=True,
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        ),
        "list_dir": AgentTool(
            name="list_dir",
            description="列出工作目录内某目录的内容",
            handler=list_dir,
            dimension="fs",
            schema={"type": "object", "properties": {"path": {"type": "string"}}},
        ),
        "delete_file": AgentTool(
            name="delete_file",
            description="删除工作目录内文件(不可逆,需用户确认)",
            handler=delete_file,
            dimension="fs",
            write=True,
            irreversible=True,
            schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
    }
