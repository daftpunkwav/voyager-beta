"""浏览器文件上传端点(§10.3 导入通道)。

上传是 HTTP 运输动作,不是领域能力:capability 通道保持纯 JSON
(gen_rest 不承载 multipart);本端点只负责把文件落到 workspace/imports/
并返回服务器路径,业务校验(类型/大小上限/路径越界)由后续领域能力
(如 sources.add_document、notes.add_asset)在其守卫链内强制。
"""

from __future__ import annotations

import re
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

#: 硬顶 1GB(运输层上限;领域层有更小的业务上限)
_MAX_BYTES = 1024 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024  # 1MB 分片读,控制并发内存占用

_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def build_upload_router(workspace: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/api/uploads")
    async def upload(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            return JSONResponse(status_code=400, content={
                "error": {"code": "GATEWAY.INVALID_INPUT",
                          "message": "须为 multipart/form-data 上传"}})
        form = await request.form()
        file = form.get("file")
        if file is None or not hasattr(file, "read"):
            return JSONResponse(status_code=400, content={
                "error": {"code": "GATEWAY.INVALID_INPUT",
                          "message": "缺少 file 字段"}})

        import uuid
        from datetime import datetime
        safe_name = _UNSAFE_FILENAME_RE.sub("_", file.filename or "upload")
        safe_name = safe_name.replace("..", "_").strip(" .")[:120] or "upload"
        month_dir = datetime.now(UTC).strftime("%Y%m")
        dest_dir = Path(workspace) / "imports" / month_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex[:12]}__{safe_name}"

        class _TooLarge(Exception):
            pass

        # 分块读/写,避免并发上传把整个文件都读进内存
        total = 0
        try:
            with dest.open("wb") as f:
                while True:
                    chunk = await file.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_BYTES:
                        raise _TooLarge
                    f.write(chunk)
        except _TooLarge:
            dest.unlink(missing_ok=True)
            return JSONResponse(status_code=413, content={
                "error": {"code": "GATEWAY.PAYLOAD_TOO_LARGE",
                          "message": "文件超过 1GB 运输上限"}})
        except Exception as exc:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            return JSONResponse(status_code=400, content={
                "error": {"code": "GATEWAY.INVALID_INPUT",
                          "message": f"读取上传流失败: {exc}"}})
        if total == 0:
            dest.unlink(missing_ok=True)
            return JSONResponse(status_code=400, content={
                "error": {"code": "GATEWAY.INVALID_INPUT", "message": "空文件"}})
        return JSONResponse(status_code=201, content={
            "file_path": str(dest), "filename": file.filename or safe_name,
            "size": total})

    return router
