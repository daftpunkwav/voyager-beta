"""扩展名集合、跳过目录与索引模式限额(对照原生引擎 discover)。"""
from __future__ import annotations

# 仓库提交的 .engineignore 否定规则永远无法解除这些目录的跳过
SAFETY_CORE_DIRS = frozenset({".git", "node_modules", ".worktrees", ".claude-worktrees"})

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    "vendor",
    "target",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    "Pods",
    ".idea",
    ".vscode",
    "__snapshots__",
}

CODE_EXT = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".scala",
    ".vue",
    ".svelte",
}
DOC_EXT = {".md", ".mdx", ".markdown", ".rst"}
CONFIG_EXT = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".sql",
    ".graphql",
    ".gql",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".xml",
    ".tf",
    ".proto",
}
ALL_EXT = CODE_EXT | DOC_EXT | CONFIG_EXT

MODE_LIMITS = {
    # fast：少文件，仍含 md Section（否则节点数会严重偏低）
    "fast": {"max_files": 800, "max_bytes": 400_000, "layout_iters": 0},
    "moderate": {"max_files": 8_000, "max_bytes": 1_500_000, "layout_iters": 0},
    # full：对齐原生引擎 量级；服务端不做力导向
    "full": {"max_files": 100_000, "max_bytes": 5_000_000, "layout_iters": 0},
    "cross-repo-intelligence": {"max_files": 0, "max_bytes": 0, "layout_iters": 0},
}
