"""
L0 项目宇宙图 API —— 与 L1 代码索引域故障隔离。
本模块禁止 import graph_l1 / graph_fallback 索引引擎。
"""
from __future__ import annotations

from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.schemas.common import DataResponse
from api_backend.services.graph_service import build_cross_edges, build_graph
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/graph", tags=["graph-l0"])


@router.get("/", response_model=DataResponse[dict])
async def get_graph(
    min_similarity: float = Query(0.3, ge=0, le=1),
    max_edges: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """L0 项目相似度图（不依赖代码索引引擎）。"""
    graph = await build_graph(
        db,
        min_similarity=min_similarity,
        max_edges=max_edges,
    )
    return wrap_data(graph)


@router.get("/cross-edges", response_model=DataResponse[dict])
async def get_cross_edges(db: AsyncSession = Depends(get_db)):
    """L0 跨仓边只读投影；引擎不可用时返回空列表，不影响相似度图。"""
    try:
        edges = await build_cross_edges(db)
    except Exception:
        edges = []
    return wrap_data({"edges": edges, "stats": {"edge_count": len(edges)}})


@router.get("/recommend-edges", response_model=DataResponse[dict])
async def get_recommend_edges(db: AsyncSession = Depends(get_db)):
    """
    Agent 推荐学习边（预留）。

    约定：项目导入且索引稳定后，由 Agent 写入推荐关系；当前返回空列表，
    前端已按 edge_type=recommend_learn 分色渲染。
    """
    _ = db
    return wrap_data(
        {
            "edges": [],
            "stats": {"edge_count": 0},
            "meta": {
                "source": "agent_recommend",
                "status": "reserved",
                "note": "导入稳定后由 Agent 更新 recommend_learn 边",
            },
        }
    )
