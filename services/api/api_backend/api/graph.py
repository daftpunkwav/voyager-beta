"""
旧单体 graph 路由已拆分为 graph_l0 / graph_l1。
保留本文件以免文档外链瞬间 404；请勿再挂载。
"""
from api_backend.api.graph_l0 import router as l0_router
from api_backend.api.graph_l1 import router as l1_router

# 兼容测试：合并路由（生产 main 分域挂载）
from fastapi import APIRouter

router = APIRouter()
router.include_router(l0_router)
router.include_router(l1_router)

__all__ = ["router", "l0_router", "l1_router"]
