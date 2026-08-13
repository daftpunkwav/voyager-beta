# 并行启动开发服务
# 默认两进程：API（:19878）+ Web（:5173）
# -All：四进程 —— 额外启动独立 Agent（:19877）+ 图谱 sidecar（:9750）
# 图谱档位见 start-graph-engine.ps1（C 引擎优先，缺失回退 Python graph_fallback）
param(
    [switch]$GraphEngine,   # 单独启用图谱 sidecar（不起 Agent）
    [switch]$All            # 四进程：API + Web + Agent + 图谱 sidecar
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Voyager dev — API :19878, Web :5173" -ForegroundColor Cyan
if ($All) {
    Write-Host "四进程模式（-All）：+ Agent :19877 + 图谱 sidecar :9750" -ForegroundColor Cyan
} elseif ($GraphEngine) {
    Write-Host "图谱 sidecar 单独启用（C 引擎优先）" -ForegroundColor DarkGray
}

# API 需要 SECRET_KEY（长度 >= 32 字节）；若未设置则自动生成一个开发用密钥
$generatedSecret = $false
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(32))")
    $generatedSecret = $true
    Write-Host "SECRET_KEY not set, generated a development key" -ForegroundColor Yellow
}

# 图谱 sidecar（-GraphEngine / -All / GRAPH_START_SIDECAR=1 触发）
$startGraph = $GraphEngine -or $All -or ($env:GRAPH_START_SIDECAR -eq "1")
$graph = $null
$graphPort = $null
if ($startGraph) {
    $startScript = Join-Path $Root "scripts\start-graph-engine.ps1"
    $graph = Start-Process -PassThru -NoNewWindow -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startScript
    ) -WorkingDirectory $Root
    $graphPort = if ($env:GRAPH_ENGINE_PORT) { $env:GRAPH_ENGINE_PORT } else { "9750" }
    Write-Host "Graph sidecar PID $($graph.Id) → 127.0.0.1:$graphPort" -ForegroundColor Cyan
    # 等待 sidecar 就绪，避免 API 启动期 ensure 重复拉起争抢端口
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$graphPort/api/ui-config" -TimeoutSec 1 -UseBasicParsing
            if ($r.StatusCode -eq 200) {
                Write-Host "Graph sidecar ready" -ForegroundColor Green
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
}

# 端口与 vite.config.ts / npm run dev:api 对齐（19876 在部分 Windows 环境会幽灵占用）
# 可用 $env:API_PORT / $env:AGENT_PORT 覆盖后端端口
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { "19878" }

$agent = $null
$waitIds = @()

if ($All) {
    # API↔Agent 内部鉴权 token；API 与 Agent 两个进程必须读到同一值
    if (-not $env:AGENT_INTERNAL_TOKEN) {
        if ($generatedSecret) {
            $env:AGENT_INTERNAL_TOKEN = $env:SECRET_KEY
        } else {
            $env:AGENT_INTERNAL_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(32))")
        }
    }
    # 图谱 sidecar URL（与上面启动的 sidecar 端口一致）
    if (-not $env:GRAPH_ENGINE_URL) { $env:GRAPH_ENGINE_URL = "http://127.0.0.1:$graphPort" }

    $agentPort = if ($env:AGENT_PORT) { $env:AGENT_PORT } else { "19877" }
    $agent = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList @(
        "-m", "uvicorn", "agent_runtime.main:app", "--reload", "--host", "127.0.0.1", "--port", $agentPort
    ) -WorkingDirectory "$Root\services\agent"
    Write-Host "Agent PID $($agent.Id)  |  :$agentPort" -ForegroundColor Green
    $waitIds += $agent.Id

    # API 将对话转发到独立 Agent 进程（agent_runtime 用同一 AGENT_INTERNAL_TOKEN 校验）
    $env:AGENT_BASE_URL = "http://127.0.0.1:$agentPort"
}

$api = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList @(
    "-m", "uvicorn", "api_backend.main:app", "--reload", "--host", "127.0.0.1", "--port", $apiPort
) -WorkingDirectory "$Root\services\api"

$web = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList @(
    "/c", "npm", "run", "dev", "-w", "web"
) -WorkingDirectory $Root

Write-Host "API  PID $($api.Id)  |  Web PID $($web.Id)" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop (subprocesses need manual cleanup)" -ForegroundColor Green

$waitIds += $api.Id
$waitIds += $web.Id
if ($graph) { $waitIds += $graph.Id }

try {
    Wait-Process -Id $waitIds
} finally {
    Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue
    if ($agent) { Stop-Process -Id $agent.Id -Force -ErrorAction SilentlyContinue }
    if ($graph) {
        Stop-Process -Id $graph.Id -Force -ErrorAction SilentlyContinue
    }
}
