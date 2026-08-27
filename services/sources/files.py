"""文档原文件的只读下载路由(用户看原版式;agent 不需要——读分章文本)。

按 doc_id 查库取得路径再校验落点,天然防路径穿越;媒体类型按扩展名
映射,浏览器据此内联预览(PDF 直接打开)。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from platform_contracts import ErrorSuffix, ServiceError

from .modules.doc.store import DocStore

_DOMAIN = "sources"

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


def build_files_router(store: DocStore) -> APIRouter:
    """/files/doc/{doc_id}(挂载方提供域前缀:/api/sources + /files)。"""
    router = APIRouter(prefix="/files")

    @router.get("/doc/{doc_id}")
    async def get_doc_file(doc_id: str) -> FileResponse:
        doc = store.get(doc_id)
        if doc is None or not doc["local_path"]:
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                               f"文档不存在或无本地文件: {doc_id}")
        path = Path(doc["local_path"])
        if not path.is_file():
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                               f"本地文件已不存在: {doc['filename']}")
        return FileResponse(
            str(path),
            media_type=_MEDIA_TYPES.get(doc["ext"], "application/octet-stream"),
            filename=doc["filename"] or path.name,
        )

    return router
