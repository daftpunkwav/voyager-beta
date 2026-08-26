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

_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|#]+)")
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
                (nid, note["title"], note.get("content", ""),
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
        """摘要列表(state 过滤 + 关键词检索;正文只回 excerpt,§9.20)。"""
        col = sort if sort in _SORTABLE else "updated_ts"
        direction = "ASC" if col == "title" else "DESC"
        cond, cond_params = _STATE_CONDS.get(state, _STATE_CONDS["active"])
        sql = ("SELECT id, title, tags, source_id, node_id, archived, pinned,"
               " trashed_ts, created_ts, updated_ts, substr(content, 1, ?) AS excerpt"
               f" FROM notes WHERE {cond}")
        params: list[Any] = [_EXCERPT_LEN]
        if source_id is not None:
            sql += " AND source_id = ?"
            params.append(source_id)
        if tag:
            sql += " AND tags LIKE ? ESCAPE '\\'"
            params.append(f'%{_like_escape(json.dumps(tag, ensure_ascii=False))}%')
        if query:
            pattern = f"%{_like_escape(query)}%"
            sql += " AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')"
            params.extend([pattern, pattern])
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

    def sync_links(self, src_id: str, content: str) -> None:
        """"[[目标]] 解析入库:先删旧再插新;悬空目标不落表。"""
        targets = [t.strip() for m in _WIKI_LINK_RE.finditer(content)
                   if (t := m.group(1).strip())]
        resolved: set[str] = set()
        by_title_cache: dict[str, str | None] = {}
        for target in targets:
            if target in resolved:
                continue
            # 精确 id 形态(uuid 十六进制段)直接当 id 试探
            if not self._conn.execute(
                "SELECT 1 FROM notes WHERE id = ?", (target,)
            ).fetchone():
                if target not in by_title_cache:
                    by_title_cache[target] = self.exists_by_title(target)
                dst = by_title_cache[target]
            else:
                dst = target
            if dst:
                resolved.add(dst)
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

    def __enter__(self) -> "NoteStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
