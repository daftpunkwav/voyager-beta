"""笔记图片附件(§8.3 扩展):add_asset 能力 + 受控资产存储。

- 引用形态:正文中写 `attachment://<asset_id>`,渲染端解析为受控路由
  /api/notes/assets/<id>——内容与存储位置解耦,访问收束到单一入口;
- 内容寻址:asset_id 生成后文件永不覆盖(immutable 缓存的前提),
  替换图片 = 新增 asset 插新引用;
- 唯一写入口是 add_asset 能力(file_path 须位于 workspace/ 内——
  浏览器上传经 gateway /api/uploads,agent 用自身文件工具落 workspace/),
  路由只读。
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "notes"

#: 允许作为笔记图片的扩展名白名单(其他格式一律拒绝,不做格式嗅探)。
# 不含 SVG:SVG 可内嵌脚本,同源内联时存在存储型 XSS 面。
ALLOWED_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

class AssetStore:
    """note_assets 表:asset_id → 落盘路径;独立命名空间(assets.db)。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS note_assets (
        asset_id  TEXT PRIMARY KEY,
        note_id   TEXT NOT NULL DEFAULT '',
        filename  TEXT NOT NULL DEFAULT '',
        ext       TEXT NOT NULL DEFAULT '',
        path      TEXT NOT NULL,
        size      INTEGER NOT NULL DEFAULT 0,
        created_ts REAL NOT NULL
    );
    """

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(self._SCHEMA)
        self._lock = threading.Lock()

    def add(self, asset: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO note_assets"
                " (asset_id, note_id, filename, ext, path, size, created_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    asset["asset_id"], asset.get("note_id", ""),
                    asset.get("filename", ""), asset.get("ext", ""),
                    asset["path"], int(asset.get("size", 0)), asset["created_ts"],
                ),
            )
            self._conn.commit()

    def get(self, asset_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT asset_id, note_id, filename, ext, path, size, created_ts"
            " FROM note_assets WHERE asset_id = ?", (asset_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(("asset_id", "note_id", "filename", "ext", "path",
                         "size", "created_ts"), row))

    def remove_of_note(self, note_id: str) -> list[str]:
        """删除某笔记名下全部资产记录,返回文件路径(调用方删文件)。"""
        paths = [r[0] for r in self._conn.execute(
            "SELECT path FROM note_assets WHERE note_id = ?", (note_id,),
        ).fetchall()]
        with self._lock:
            self._conn.execute(
                "DELETE FROM note_assets WHERE note_id = ?", (note_id,))
            self._conn.commit()
        return paths

    def close(self) -> None:
        self._conn.close()


_store: AssetStore | None = None
_workspace: Path | None = None
_max_file_mb: Callable[[], int] | None = None


def init_store(store: AssetStore, workspace: Path,
               max_file_mb: Callable[[], int] | None = None) -> None:
    global _store, _workspace, _max_file_mb
    _store = store
    _workspace = workspace
    _max_file_mb = max_file_mb


def require_store() -> AssetStore:
    if _store is None:
        raise RuntimeError("assets 未注入:服务入口需先调用 init_store()")
    return _store


def purge_of_note(note_id: str) -> list[str]:
    """删除笔记名下资产(记录+文件);返回被删路径供审计。"""
    store = require_store()
    paths = store.remove_of_note(note_id)
    for p in paths:
        Path(p).unlink(missing_ok=True)
    return paths


def register(registry: Registry) -> None:
    """把 add_asset 注册进 notes 注册表(wiring 调用;避免与 capabilities 循环导入)。

    registry 是模块级单例,重复 wire(测试多次装配)时跳过注册,只重绑 deps。
    """
    if "add_asset" in registry:
        return

    @capability(registry, name="add_asset",
                description="为笔记添加图片附件:复制文件到附件区并返回 attachment:// 引用。"
                            "file_path 须位于 workspace/ 内(浏览器上传经 /api/uploads,"
                            "agent 用文件工具落 workspace/)。", cost=1)
    async def add_asset(file_path: str, filename: str = "",
                        note_id: str = "") -> dict:
        store = require_store()
        src = Path(file_path)
        if not src.is_file():
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               f"文件不存在: {file_path}")
        ext = src.suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               f"不支持的图片格式: {ext}",
                               hint=f"仅支持 {'/'.join(ALLOWED_EXTS)}")
        limit_mb = _max_file_mb() if _max_file_mb else 20
        if limit_mb > 0 and src.stat().st_size > limit_mb * 1024 * 1024:
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               f"图片超过大小上限 {limit_mb}MB",
                               hint="可用设置 notes.assets.max_mb 调整")
        root = _workspace if _workspace else Path("workspace")
        root_resolved = Path(root).resolve()
        src_resolved = src.resolve(strict=True)
        if not src_resolved.is_relative_to(root_resolved):
            raise ServiceError(_DOMAIN, ErrorSuffix.FORBIDDEN,
                               "文件须位于 workspace/ 内(经 /api/uploads 上传)")
        asset_id = uuid.uuid4().hex[:12]
        assets_dir = Path(root) / "notes-assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / f"{asset_id}{ext}"
        dest_resolved = dest.resolve()
        if not dest_resolved.is_relative_to(root_resolved):
            raise ServiceError(_DOMAIN, ErrorSuffix.FORBIDDEN,
                               "目标路径异常,请检查 workspace 配置")
        # 如 src 是 symlink,复制后得到普通文件,阻断通过链接指向外部路径
        shutil.copy2(src, dest)
        safe_name = _UNSAFE_FILENAME_RE.sub("_", filename or src.name)[:120]
        store.add({"asset_id": asset_id, "note_id": note_id,
                   "filename": safe_name, "ext": ext,
                   "path": str(dest), "size": src.stat().st_size,
                   "created_ts": time.time()})
        return {
            "asset_id": asset_id,
            "url": f"/api/notes/assets/{asset_id}",
            "markdown": f"![{safe_name}](attachment://{asset_id})",
        }


def build_assets_router() -> object:
    """附件只读路由:/assets/{asset_id}(挂载方提供 /api/notes 前缀)。

    内容寻址 ⇒ immutable 缓存成立;路径按 id 查库取得,天然防穿越。
    """
    from fastapi import APIRouter
    from fastapi.responses import FileResponse

    router = APIRouter(prefix="/assets")

    @router.get("/{asset_id}")
    async def get_asset(asset_id: str) -> FileResponse:
        store = require_store()
        asset = store.get(asset_id)
        if asset is None:
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                               f"附件不存在: {asset_id}")
        path = Path(asset["path"])
        if not path.is_file():
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                               f"附件文件已丢失: {asset['filename']}")
        return FileResponse(
            str(path),
            media_type=_MEDIA_TYPES.get(asset["ext"], "application/octet-stream"),
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    return router
