# 启动图谱引擎 HTTP sidecar（默认 127.0.0.1:9750）
# 档位：C 引擎 graph-engine.exe 优先（性能权威实现）；未构建时回退 Python graph_fallback（装即用）。
# API 默认可进程内使用 graph_fallback；仅在需要 sidecar 时运行本脚本，并设置 GRAPH_ENGINE_URL。
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$dataRoot = Join-Path $Root "data"
if (-not (Test-Path $dataRoot)) {
    New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
}

$env:GRAPH_ALLOWED_ROOT = if ($env:GRAPH_ALLOWED_ROOT) { $env:GRAPH_ALLOWED_ROOT } else { $dataRoot }
$env:GRAPH_ENGINE_PORT = if ($env:GRAPH_ENGINE_PORT) { $env:GRAPH_ENGINE_PORT } else { "9750" }

$cacheDir = if ($env:GRAPH_CACHE_DIR) { $env:GRAPH_CACHE_DIR } else { Join-Path $dataRoot "graph-engine-cache" }
if (-not (Test-Path $cacheDir)) { New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null }

# 档位一：C 引擎（Windows 原生二进制 graph-engine.exe）
# C 引擎内部只读 ENGINE_CACHE_DIR / ENGINE_ALLOWED_ROOT（源码 getenv，唯一权威名）；
# GRAPH_* 是应用层配置契约，此处不再双写（与 sidecar.py 同策略，避免两套名字漂移）。
$cExe = Join-Path $Root "services\graph_engine\graph_engine_core\build\c\graph-engine.exe"
if (Test-Path $cExe) {
    $env:ENGINE_CACHE_DIR = $cacheDir
    # ENGINE_ALLOWED_ROOT 取 GRAPH_ALLOWED_ROOT 覆盖值(第 12 行已归一化)，
    # 保证操作员收窄索引边界时 C 引擎遵守，不被默认 dataRoot 静默扩大
    $env:ENGINE_ALLOWED_ROOT = $env:GRAPH_ALLOWED_ROOT
    Write-Host "graph-engine (C) sidecar → 127.0.0.1:$($env:GRAPH_ENGINE_PORT)" -ForegroundColor Cyan
    Write-Host "ENGINE_CACHE_DIR=$($env:ENGINE_CACHE_DIR)"
    Write-Host "ENGINE_ALLOWED_ROOT=$($env:ENGINE_ALLOWED_ROOT)"
    Set-Location $Root
    & $cExe "--port=$($env:GRAPH_ENGINE_PORT)"
    exit $LASTEXITCODE
}

# 档位二：Python 回退 graph_fallback（跨平台，装即用；包位于 services/graph_engine/ 下）
# 引擎层统一读 ENGINE_*（与 C 引擎命名面一致），此处由应用层 GRAPH_* 翻译
$env:ENGINE_ALLOWED_ROOT = $env:GRAPH_ALLOWED_ROOT
$env:ENGINE_PORT = $env:GRAPH_ENGINE_PORT
Write-Host "graph-engine (Python) sidecar → 127.0.0.1:$($env:ENGINE_PORT)" -ForegroundColor Cyan
Write-Host "ENGINE_ALLOWED_ROOT=$($env:ENGINE_ALLOWED_ROOT)"

Set-Location (Join-Path $Root "services\graph_engine")
python -m graph_fallback.server
