"""notes 服务数据访问(§8.3):Markdown 笔记的完整存储层。

状态机:pinned/archived/trashed_ts 三列互不排斥组合出四个视图——
- active(默认):未归档未删除;
- archived:归档(不进默认列表,仍可搜索/打开);
- trash:trashed_ts 非空 = 在回收站(可恢复);
- all:全部。

随附能力:
- 版本快照(content 变更前自动入 note_versions,按设置保留 N 版);
- 双向链接:[[目标]] 在写入时解析为 note_links 表(dst=id),支持反链查询;
  目标优先按精确 id 匹配,其次按标题精确匹配(大小写不敏感);解析失败的
  链接(悬空)不入表——反链视图里看不到它们是已知取舍;
- 全文检索:LIKE 转义匹配 title/content(个人笔记量级足够;十万级再演进 FTS5);
- 迁移:旧库缺列时 PRAGMA 探测后 ALTER,不破坏既有数据。
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tags       TEXT NOT NULL DEFAULT '[]',
    source_id  TEXT NOT NULL DEFAULT '',
    node_id    TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_source ON notes(source_id);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_ts);

CREATE TABLE IF NOT EXISTS note_versions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id  TEXT NOT NULL,
    version  INTEGER NOT NULL,
    content  TEXT NOT NULL,
    ts       REAL NOT NULL,
    UNIQUE (note_id, version)
);
CREATE INDEX IF NOT EXISTS idx_versions_note ON note_versions(note_id, version DESC);

CREATE TABLE IF NOT EXISTS note_links (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_links_dst ON note_links(dst);
"""

# 内链目标不允许跨行(排除换行)与 | 别名、# 锚点段
_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|#\n]+)")
_SUMMARY_COLS = ("id", "title", "tags", "source_id", "node_id",
                 "archived", "pinned", "trashed_ts",
                 "created_ts", "updated_ts", "excerpt")
_ALL_COLS = ("id", "title", "content", "tags", "source_id", "node_id",
             "archived", "pinned", "trashed_ts", "created_ts", "updated_ts")
_STATE_CONDS = {
    "active": ("archived = 0 AND trashed_ts IS NULL", []),
    "archived": ("archived = 1 AND trashed_ts IS NULL", []),
    "trash": ("trashed_ts IS NOT NULL", []),
    "all": ("1=1", []),
}
_EXCERPT_LEN = 120


def _normalize(text: str) -> str:
    """统一换行为 LF:Windows 剪贴板/编辑器带入的 CRLF 会让正文偏移量、
    行号语义与搜索窗口产生漂移,入库一律规范化。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


class NoteStore:
    def __init__(self, db_path: str | Path, *, history_keep: int = 20) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._lock = threading.Lock()
        self.history_keep = max(0, history_keep)

    # ---------- 迁移 ----------

    def _migrate(self) -> None:
        """旧库平滑升级:缺列 ALTER 添加(SQLite 无 ADD COLUMN IF NOT EXISTS)。"""
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(notes)")}
        for ddl in (
            "ALTER TABLE notes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE notes ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE notes ADD COLUMN trashed_ts REAL",
        ):
            name = ddl.split("ADD COLUMN ")[1].split()[0]
            if name not in cols:
                self._conn.execute(ddl)
        self._conn.commit()

    # ---------- 基础 CRUD ----------

    def create(self, note: dict[str, Any]) -> str:
        nid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO notes (id, title, content, tags, source_id, node_id,"
                " archived, pinned, trashed_ts, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?)",
                (nid, note["title"], _normalize(note.get("content", "")),
                 json.dumps(note.get("tags", []), ensure_ascii=False),
                 note.get("source_id", ""), note.get("node_id", ""), now, now),
            )
            self._conn.commit()
        return nid

    def get(self, nid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT {','.join(_ALL_COLS)} FROM notes WHERE id = ?", (nid,)
        ).fetchone()
        return _full_row(row) if row else None

    def exists_by_title(self, title: str) -> str | None:
        """标题精确匹配(大小写不敏感)取最新一条存活笔记 id;链接解析用。"""
        row = self._conn.execute(
            "SELECT id FROM notes"
            " WHERE lower(title)=lower(?) AND trashed_ts IS NULL"
            " ORDER BY updated_ts DESC LIMIT 1", (title,),
        ).fetchone()
        return row[0] if row else None

    def update(self, nid: str, **fields: Any) -> bool:
        """字段级更新。content 变更先快照旧文;返回是否命中记录。

        快照策略保留最近 history_keep 版(0 = 关闭历史)。
        """
        allowed = {"title", "content", "tags", "source_id", "node_id",
                   "pinned", "archived"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False
        if "content" in updates:
            updates["content"] = _normalize(updates["content"])
        sets, params = [], []
        new_content = None
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
            if k == "content":
                new_content = v
        with self._lock:
            old_content = None
            if new_content is not None and self.history_keep > 0:
                row = self._conn.execute(
                    "SELECT content FROM notes WHERE id = ?", (nid,)
                ).fetchone()
                old_content = row[0] if row else None
            cur = self._conn.execute(
                f"UPDATE notes SET {', '.join(sets)}, updated_ts = ? WHERE id = ?",
                (*params, time.time(), nid),
            )
            self._conn.commit()
            if old_content is not None and old_content != new_content:
                self._snapshot_locked(nid, old_content)
        return cur.rowcount > 0

    def delete(self, nid: str) -> None:
        """彻底删除(含版本与链接)。软删除走 trash()。"""
        with self._lock:
            self._conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
            self._conn.execute("DELETE FROM note_versions WHERE note_id = ?", (nid,))
            self._conn.execute(
                "DELETE FROM note_links WHERE src = ? OR dst = ?", (nid, nid))
            self._conn.commit()

    # ---------- 状态机 ----------

    def trash(self, nid: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notes SET trashed_ts = ?, updated_ts = ?"
                " WHERE id = ? AND trashed_ts IS NULL",
                (time.time(), time.time(), nid),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def restore(self, nid: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notes SET trashed_ts = NULL, updated_ts = ? WHERE id = ?",
                (time.time(), nid),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def purge_expired(self, older_than_days: int) -> int:
        """清掉回收站中超期条目(days<=0 表示永久保留 → no-op)。"""
        if older_than_days <= 0:
            return 0
        cutoff = time.time() - older_than_days * 86400
        rows = self._conn.execute(
            "SELECT id FROM notes WHERE trashed_ts IS NOT NULL AND trashed_ts < ?",
            (cutoff,),
        ).fetchall()
        count = 0
        for (nid,) in rows:
            self.delete(nid)
            count += 1
        return count

    # ---------- 列表与检索 ----------

    def list(self, *, source_id: str | None = None, tag: str = "",
             query: str = "", state: str = "active", sort: str = "updated_ts",
             limit: int = 100) -> list[dict[str, Any]]:
        """摘要列表(state 过滤 + 关键词检索,§9.20)。

        query 命中正文时 excerpt 不再取固定开头,而是返回命中处前后的
        上下文窗口(对齐 GitHub/Obsidian 搜索结果);仅标题命中的笔记回退
        到前 120 字。
        """
        col = sort if sort in _SORTABLE else "updated_ts"
        direction = "ASC" if col == "title" else "DESC"
        state_sql, state_params = _STATE_CONDS.get(state, _STATE_CONDS["active"])
        conds = [state_sql]
        params: list[Any] = list(state_params)
        if source_id is not None:
            conds.append("source_id = ?")
            params.append(source_id)
        if tag:
            conds.append("tags LIKE ? ESCAPE '\\'")
            params.append(f'%{_like_escape(json.dumps(tag, ensure_ascii=False))}%')
        excerpt_sql = f"substr(content, 1, {_EXCERPT_LEN})"
        if query:
            # 注意绑定顺序:SELECT 头的 CASE 占位先于 WHERE 的 LIKE 占位
            needle = query.lower()
            excerpt_sql = (
                "CASE WHEN instr(lower(content), lower(?)) > 0 THEN"
                " substr(content, MAX(1, instr(lower(content), lower(?)) - 60), 180)"
                f" ELSE substr(content, 1, {_EXCERPT_LEN}) END"
            )
            params.extend([needle, needle])
            pattern = f"%{_like_escape(query)}%"
            conds.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params.extend([pattern, pattern])
        sql = ("SELECT id, title, tags, source_id, node_id, archived, pinned,"
               " trashed_ts, created_ts, updated_ts,"
               f" {excerpt_sql} AS excerpt"
               f" FROM notes WHERE {' AND '.join(conds)}")
        sql += f" ORDER BY pinned DESC, {col} {direction} LIMIT ?"
        params.append(limit)
        return [_summary_row(r) for r in self._conn.execute(sql, params)]

    def stats(self) -> dict[str, Any]:
        states = {"active": 0, "archived": 0, "trash": 0}
        for (flag, has_trash, n) in self._conn.execute(
            "SELECT archived, trashed_ts IS NOT NULL, COUNT(*)"
            " FROM notes GROUP BY archived, trashed_ts IS NOT NULL"
        ):
            key = "trash" if has_trash else ("archived" if flag else "active")
            states[key] = states.get(key, 0) + n
        tag_counts: dict[str, int] = {}
        for (tags_json,) in self._conn.execute(
            "SELECT tags FROM notes WHERE trashed_ts IS NULL"
        ):
            try:
                for t in json.loads(tags_json):
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            except ValueError:
                continue
        top_tags = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        return {**states, "total": sum(states.values()),
                "tags": [{"tag": t, "count": c} for t, c in top_tags]}

    def all_tags(self) -> list[tuple[str, int]]:
        counter: dict[str, int] = {}
        for (tags_json,) in self._conn.execute(
            "SELECT tags FROM notes WHERE trashed_ts IS NULL"
        ):
            try:
                for t in json.loads(tags_json):
                    counter[t] = counter.get(t, 0) + 1
            except ValueError:
                continue
        return sorted(counter.items())

    def rename_tag(self, old: str, new: str) -> int:
        """全局改标签名:直接对 JSON 文本做带引号的整词替换;返回影响行数。"""
        needle_old = json.dumps(old, ensure_ascii=False)
        needle_new = json.dumps(new, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notes SET tags = replace(tags, ?, ?), updated_ts = ?"
                " WHERE instr(tags, ?) > 0",
                (needle_old, needle_new, time.time(), needle_old),
            )
            self._conn.commit()
        return cur.rowcount

    # ---------- 版本历史 ----------

    def _snapshot_locked(self, nid: str, content: str) -> None:
        next_version = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM note_versions WHERE note_id = ?",
            (nid,),
        ).fetchone()[0]
        self._conn.execute(
            "INSERT INTO note_versions (note_id, version, content, ts)"
            " VALUES (?, ?, ?, ?)", (nid, next_version, content, time.time()))
        keep_from = next_version - self.history_keep
        if keep_from > 0:
            self._conn.execute(
                "DELETE FROM note_versions WHERE note_id = ? AND version <= ?",
                (nid, keep_from))

    def list_versions(self, nid: str) -> list[dict[str, Any]]:
        return [
            {"version": r[0], "ts": r[1], "chars": len(r[2])}
            for r in self._conn.execute(
                "SELECT version, ts, content FROM note_versions"
                " WHERE note_id = ? ORDER BY version DESC", (nid,))
        ]

    def get_version(self, nid: str, version: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT content, ts FROM note_versions"
            " WHERE note_id = ? AND version = ?", (nid, version),
        ).fetchone()
        return {"content": row[0], "ts": row[1]} if row else None

    # ---------- 双向链接 ----------

    def resolve_link_targets(self, content: str) -> list[dict[str, Any]]:
        """解析 [[目标]] → 候选明细(raw/target_id/title),供渲染与建表共用。

        target_id 为 None 表示悬空链接(目标不存在);title 回填候选的
        现有笔记标题(id 形态命中时也回读),前端可直接展示与跳转。
        """
        raws: list[str] = []
        seen_raw: set[str] = set()
        for m in _WIKI_LINK_RE.finditer(content):
            raw = m.group(1).strip()
            if raw and raw not in seen_raw:
                seen_raw.add(raw)
                raws.append(raw)
        out: list[dict[str, Any]] = []
        by_title_cache: dict[str, str | None] = {}
        for raw in raws:
            dst_id: str | None = None
            row = self._conn.execute(
                "SELECT id, title FROM notes WHERE id = ?", (raw,)
            ).fetchone()
            if row is not None:
                dst_id, title = str(row[0]), str(row[1])
            else:
                if raw not in by_title_cache:
                    by_title_cache[raw] = self.exists_by_title(raw)
                hit = by_title_cache[raw]
                if hit:
                    dst_id = hit
                    row = self._conn.execute(
                        "SELECT id, title FROM notes WHERE id = ?", (hit,)
                    ).fetchone()
                    title = str(row[1]) if row else raw
                else:
                    title = raw
            out.append({"raw": raw, "target_id": dst_id,
                        "title": title if dst_id else None})
        return out

    def sync_links(self, src_id: str, content: str) -> None:
        """"[[目标]] 解析入库:先删旧再插新;悬空目标不落表。"""
        resolved = {
            item["target_id"]
            for item in self.resolve_link_targets(content)
            if item["target_id"]
        }
        with self._lock:
            self._conn.execute("DELETE FROM note_links WHERE src = ?", (src_id,))
            self._conn.executemany(
                "INSERT OR IGNORE INTO note_links (src, dst) VALUES (?, ?)",
                [(src_id, dst) for dst in sorted(resolved)])
            self._conn.commit()

    def backlinks(self, nid: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT s.id, s.title, substr(s.content, 1, ?), s.updated_ts"
            " FROM note_links l JOIN notes s ON s.id = l.src"
            " WHERE l.dst = ? AND s.trashed_ts IS NULL"
            " ORDER BY s.updated_ts DESC LIMIT ?", (_EXCERPT_LEN, nid, limit),
        )
        return [
            {"id": r[0], "title": r[1], "excerpt": r[2], "updated_ts": r[3]}
            for r in rows
        ]

    # ---------- 生命周期 ----------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> NoteStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def extract_toc(content: str) -> list[dict[str, Any]]:
    """提取 Markdown 标题大纲(1-6 级 ATX):level/text/line(1 基,LF 文本)。

    供前端大纲面板与滚动定位;代码块内的 `#` 注释不是标题——跳过围栏段。
    """
    toc: list[dict[str, Any]] = []
    in_fence = False
    fence_marker = ""
    for line_no, line in enumerate(content.split("\n"), start=1):
        stripped = line.lstrip()
        if stripped[:3] in ("```", "~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence or not stripped.startswith("#"):
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if m:
            toc.append({"level": len(m.group(1)), "text": m.group(2).strip(),
                        "line": line_no})
    return toc


def _summary_row(r: tuple) -> dict[str, Any]:
    d = dict(zip(_SUMMARY_COLS, r))
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["archived"] = bool(d["archived"])
    d["pinned"] = bool(d["pinned"])
    return d


def _full_row(row: tuple) -> dict[str, Any]:
    d = dict(zip(_ALL_COLS, row))
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["archived"] = bool(d["archived"])
    d["pinned"] = bool(d["pinned"])
    return d


_SORTABLE = {"updated_ts", "created_ts", "title"}
