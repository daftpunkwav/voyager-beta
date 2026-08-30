"""skill 加载(§9.13 / §9.20):索引常驻(name+desc),全文按需。"""

from __future__ import annotations

from pathlib import Path


class SkillLoader:
    """扫描 roots 下的 <name>/SKILL.md;索引只读标题与首行描述,全文按需。"""

    def __init__(self, roots: list[str | Path]) -> None:
        self._roots = [Path(r) for r in roots]

    def index(self) -> list[dict[str, str]]:
        """索引条目只回 name + description;本机绝对路径不出 loader(§9.20)。"""
        return [
            {"name": item["name"], "description": item["description"]}
            for item in self._scan()
        ]

    def full_text(self, name: str) -> str:
        for item in self._scan():
            if item["name"] == name:
                return Path(item["path"]).read_text(encoding="utf-8")
        raise KeyError(f"未知 skill: {name}(index() 查看全部)")

    def _scan(self) -> list[dict[str, str]]:
        """内部扫描:含 path,供 full_text 按需读盘。"""
        out: list[dict[str, str]] = []
        for root in self._roots:
            if not root.exists():
                continue
            for skill_md in sorted(root.rglob("SKILL.md")):
                out.append(
                    {
                        "name": skill_md.parent.name,
                        "description": self._read_desc(skill_md),
                        "path": str(skill_md),
                    }
                )
        return out

    @staticmethod
    def _read_desc(path: Path) -> str:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                return line[:120]
        return ""
