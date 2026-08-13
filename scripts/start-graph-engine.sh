#!/usr/bin/env bash
# 启动图谱引擎 HTTP sidecar（默认 127.0.0.1:9750）
# 档位：C 引擎 graph-engine 优先（性能权威实现）；未构建时回退 Python graph_fallback（装即用）。
# API 默认可进程内使用 graph_fallback；仅在需要 sidecar 时运行本脚本，并设置 GRAPH_ENGINE_URL。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${GRAPH_ALLOWED_ROOT:-$ROOT/data}"
mkdir -p "$DATA_ROOT"

export GRAPH_ALLOWED_ROOT="$DATA_ROOT"
export GRAPH_ENGINE_PORT="${GRAPH_ENGINE_PORT:-9750}"

CACHE_DIR="${GRAPH_CACHE_DIR:-$ROOT/data/graph-engine-cache}"
mkdir -p "$CACHE_DIR"

# 档位一：C 引擎（Unix 原生二进制 graph-engine）
# C 引擎内部只读 ENGINE_CACHE_DIR / ENGINE_ALLOWED_ROOT（源码 getenv，唯一权威名）；
# ENGINE_ALLOWED_ROOT 取 GRAPH_ALLOWED_ROOT 覆盖值，保证操作员收窄索引边界被遵守。
C_BIN="$ROOT/services/graph_engine/graph_engine_core/build/c/graph-engine"
if [ -x "$C_BIN" ]; then
    export ENGINE_CACHE_DIR="$CACHE_DIR"
    export ENGINE_ALLOWED_ROOT="$GRAPH_ALLOWED_ROOT"
    echo "graph-engine (C) sidecar → 127.0.0.1:${GRAPH_ENGINE_PORT}"
    echo "ENGINE_CACHE_DIR=${ENGINE_CACHE_DIR}"
    echo "ENGINE_ALLOWED_ROOT=${ENGINE_ALLOWED_ROOT}"
    cd "$ROOT"
    exec "$C_BIN" "--port=${GRAPH_ENGINE_PORT}"
fi

# 档位二：Python 回退 graph_fallback（跨平台，装即用；包位于 services/graph_engine/ 下）
# 引擎层统一读 ENGINE_*（与 C 引擎命名面一致），此处由应用层 GRAPH_* 翻译
export ENGINE_ALLOWED_ROOT="$GRAPH_ALLOWED_ROOT"
export ENGINE_PORT="${GRAPH_ENGINE_PORT}"
echo "graph-engine (Python) sidecar → 127.0.0.1:${ENGINE_PORT}"
echo "ENGINE_ALLOWED_ROOT=${ENGINE_ALLOWED_ROOT}"

cd "$ROOT/services/graph_engine"
exec python -m graph_fallback.server
