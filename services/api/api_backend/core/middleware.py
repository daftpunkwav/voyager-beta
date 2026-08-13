"""
中间件装配 —— CORS 等（与 main 入口保持配置一致）

主应用在 main.py 中直接挂载中间件；本模块提供可复用的 setup，
避免出现第二份硬编码 allow_origins。
"""
from api_backend.config import get_settings
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def setup_middleware(app: FastAPI) -> None:
    """按当前 Settings 挂载 CORS（allow_credentials=True 时不可用 *）。"""
    settings = get_settings()
    origins = settings.cors_origins_list()
    # fail-fast：allow_credentials=True 时 Starlette 不会真正允许 *，
    # 浏览器会静默拒绝携带凭据的请求；启动期显式报错更可诊断
    if "*" in origins:
        raise ValueError(
            "CORS_ALLOW_ORIGINS 含通配符 * 但与 allow_credentials=True 冲突，"
            "请配置精确的源列表（例如 http://localhost:5173）"
        )
    if not origins:
        raise ValueError("CORS_ALLOW_ORIGINS 为空，跨源请求将全部被拒；请显式配置允许源")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        # 显式枚举实际使用的 HTTP 方法，避免通配 * 放开 DELETE/PATCH 等写操作
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # 保留 *：跨源请求可能携带任意自定义头（X-Agent-Internal-Token 等），
        # 收紧为白名单会遗漏后续新增头导致跨源失败
        allow_headers=["*"],
    )


def cors_allow_origins() -> list[str]:
    """供测试与诊断：当前 CORS 允许源列表。"""
    return get_settings().cors_origins_list()
