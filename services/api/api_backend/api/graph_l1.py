"""
L1 代码图谱 API —— 独立模块；加载失败不影响 L0。
"""
from __future__ import annotations

from uuid import UUID

from api_backend.api.deps import get_db
from api_backend.config import get_settings
from api_backend.core import error_codes as EC
from api_backend.core.exceptions import AppException, NotFoundError
from api_backend.core.responses import wrap_data
from api_backend.models.project import Project
from api_backend.schemas.common import DataResponse
from api_backend.schemas.graph import IndexTriggerBody, SearchBody, TraceBody
from api_backend.services.index_data_adapter import adapt_layout
from fastapi import APIRouter, Depends, Query
from graph_engine_runtime import index_pipeline as pipeline
from graph_engine_runtime.client import GraphEngineClient, GraphEngineError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

# GRAPH_DISABLED=1 时模块加载失败 → safe_load_router 捕获 → /api/v1/graph/* 返回 503
# （模块容错挂载设计：单域失败不阻塞 app 启动；graph_l0 纯 DB 投影不受影响）
if get_settings().graph_disabled:
    raise RuntimeError(
        "图谱引擎已禁用（GRAPH_DISABLED=1）；graph_l1 索引/查询不可用"
    )

router = APIRouter(prefix="/graph", tags=["graph-l1"])


class BatchIndexBody(BaseModel):
    project_ids: list[UUID] = Field(..., min_length=1, max_length=50)
    mode: str = "fast"


@router.get("/projects/{project_id}/status", response_model=DataResponse[dict])
async def get_project_index_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await pipeline.get_status_out(db, project_id))


@router.post("/projects/{project_id}/index", response_model=DataResponse[dict])
async def trigger_project_index(
    project_id: UUID,
    body: IndexTriggerBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    mode = (body.mode if body else "fast") or "fast"
    return wrap_data(await pipeline.trigger_index(db, project_id, mode=mode))


@router.post("/projects/index-batch", response_model=DataResponse[dict])
async def trigger_batch_index(
    body: BatchIndexBody,
    db: AsyncSession = Depends(get_db),
):
    """批量入队索引（worker 池并行）；返回各项目状态快照。"""
    results = []
    for pid in body.project_ids:
        try:
            st = await pipeline.trigger_index(db, pid, mode=body.mode or "fast")
            results.append(st)
        except AppException as exc:
            results.append(
                {
                    "project_id": str(pid),
                    "status": "INDEX_FAILED",
                    "error": exc.detail.get("message")
                    if isinstance(exc.detail, dict)
                    else str(exc.detail),
                    "code": exc.detail.get("code")
                    if isinstance(exc.detail, dict)
                    else EC.GRAPH_INDEX_FAILED,
                }
            )
    return wrap_data({"items": results, "queued": len(results)})


@router.post("/projects/{project_id}/refresh", response_model=DataResponse[dict])
async def refresh_project_index(
    project_id: UUID,
    body: IndexTriggerBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    mode = (body.mode if body else "fast") or "fast"
    return wrap_data(
        await pipeline.trigger_index(db, project_id, mode=mode, refresh=True)
    )


@router.post("/projects/{project_id}/index/cancel", response_model=DataResponse[dict])
async def cancel_project_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """取消排队或进行中的索引。"""
    return wrap_data(await pipeline.cancel_index(db, project_id))


@router.get("/index-statuses", response_model=DataResponse[dict])
async def list_project_index_statuses(
    db: AsyncSession = Depends(get_db),
):
    """图谱页索引进度条：全部项目索引状态快照。"""
    items = await pipeline.list_index_statuses(db)
    active = [
        s
        for s in items
        if s["status"] in ("QUEUED", "CLONING", "INDEXING")
        or s["status"] in ("CLONE_FAILED", "INDEX_FAILED")
    ]
    return wrap_data(
        {
            "items": items,
            "active": active,
            "stats": {
                "total": len(items),
                "running": sum(
                    1 for s in items if s["status"] in ("QUEUED", "CLONING", "INDEXING")
                ),
                "ready": sum(1 for s in items if s["status"] == "READY"),
                "failed": sum(
                    1
                    for s in items
                    if s["status"] in ("CLONE_FAILED", "INDEX_FAILED")
                ),
            },
        }
    )


@router.delete("/projects/{project_id}/index", response_model=DataResponse[dict])
async def delete_project_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return wrap_data(await pipeline.delete_index(db, project_id))


@router.get("/projects/{project_id}", response_model=DataResponse[dict])
async def get_code_graph(
    project_id: UUID,
    max_nodes: int = Query(5000, ge=100, le=100_000),
    db: AsyncSession = Depends(get_db),
):
    status = await pipeline.get_status_out(db, project_id)
    if status["status"] != "READY":
        raise AppException(
            409,
            EC.GRAPH_NOT_INDEXED,
            f"项目尚未索引就绪（当前状态：{status['status']}）。请先在项目详情页构建代码图谱。",
        )
    client = GraphEngineClient()
    try:
        raw = await client.fetch_layout(
            status["engine_project"], max_nodes=max_nodes
        )
    except GraphEngineError as exc:
        raise AppException(502, exc.code, exc.message) from exc
    return wrap_data(adapt_layout(raw).model_dump())


@router.get("/projects/{project_id}/architecture", response_model=DataResponse[dict])
async def get_project_architecture(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    engine = await _require_ready_engine(db, project_id)
    client = GraphEngineClient()
    try:
        data = await client.get_architecture(engine)
    except GraphEngineError as exc:
        raise AppException(502, exc.code, exc.message) from exc
    return wrap_data(data if isinstance(data, dict) else {"result": data})


@router.post("/projects/{project_id}/trace", response_model=DataResponse[dict])
async def trace_project_symbol(
    project_id: UUID,
    body: TraceBody,
    db: AsyncSession = Depends(get_db),
):
    engine = await _require_ready_engine(db, project_id)
    client = GraphEngineClient()
    try:
        data = await client.trace_path(
            engine,
            symbol=body.symbol,
            direction=body.direction,
            depth=body.depth,
        )
    except GraphEngineError as exc:
        raise AppException(502, exc.code, exc.message) from exc
    return wrap_data(data if isinstance(data, dict) else {"result": data})


@router.post("/projects/{project_id}/search", response_model=DataResponse[dict])
async def search_project_graph(
    project_id: UUID,
    body: SearchBody,
    db: AsyncSession = Depends(get_db),
):
    engine = await _require_ready_engine(db, project_id)
    client = GraphEngineClient()
    try:
        data = await client.search_graph(
            engine,
            query=body.query,
            label=body.label,
            limit=body.limit,
        )
    except GraphEngineError as exc:
        raise AppException(502, exc.code, exc.message) from exc
    return wrap_data(data if isinstance(data, dict) else {"result": data})


@router.get("/projects/{project_id}/schema", response_model=DataResponse[dict])
async def get_project_graph_schema(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    engine = await _require_ready_engine(db, project_id)
    client = GraphEngineClient()
    try:
        data = await client.get_graph_schema(engine)
    except GraphEngineError as exc:
        raise AppException(502, exc.code, exc.message) from exc
    return wrap_data(data if isinstance(data, dict) else {"result": data})


async def _require_ready_engine(db: AsyncSession, project_id: UUID) -> str:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目不存在", EC.PROJECT_NOT_FOUND)
    status = await pipeline.get_status_out(db, project_id)
    if status["status"] != "READY" or not status.get("engine_project"):
        raise AppException(
            409,
            EC.GRAPH_NOT_INDEXED,
            f"项目尚未索引就绪（当前状态：{status['status']}）。请先构建代码图谱。",
        )
    return status["engine_project"]
