# Voyager：构建迁入的 C 图谱引擎（graph-engine）
# 优先 WSL；否则尝试本机 MinGW make。

param(
    [switch]$WithUi,
    [int]$Jobs = 0,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Help) {
    Write-Host @"
用法: .\scripts\build.ps1 [-Jobs N]

在 services/graph_engine/graph_engine_core 下编译迁入的 C 引擎。
产物: build/c/graph-engine（或 .exe）
注: UI asset 服务已移除，-WithUi 参数保留仅为兼容旧调用，无实际效果。
"@
    exit 0
}

if ($WithUi) {
    Write-Host "警告: -WithUi 已弃用（前端资源服务已移除），按标准目标构建。" -ForegroundColor Yellow
}

function Test-Wsl {
    try {
        $null = & wsl.exe -e true 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$j = if ($Jobs -gt 0) { $Jobs } else { [Math]::Max(2, [Environment]::ProcessorCount - 1) }
$target = "graph-engine"

Write-Host "==> 构建目标: $target  -j$j" -ForegroundColor Cyan

# 构建前规范化 shell 脚本换行，避免 /mnt/d CRLF 导致 sh 失败
python -c @"
from pathlib import Path
root = Path(r'$($Root -replace '\\','/')')
for p in root.rglob('*.sh'):
    b = p.read_bytes()
    if b'\r' in b:
        p.write_bytes(b.replace(b'\r\n', b'\n').replace(b'\r', b'\n'))
"@

if (Test-Wsl) {
    $wslPath = (& wsl.exe wslpath -a $Root).Trim()
    Write-Host "==> 使用 WSL: $wslPath" -ForegroundColor Cyan
    & wsl.exe -e bash -lc "set -euo pipefail; cd '$wslPath'; make -f Makefile -j$j $target"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    $make = Get-Command make -ErrorAction SilentlyContinue
    $gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if (-not $make -or -not $gcc) {
        Write-Error "未找到 WSL，且本机缺少 make/gcc。请安装 WSL 或 MinGW。"
    }
    Write-Host "==> 使用本机 MinGW make/gcc" -ForegroundColor Cyan
    & make -f Makefile -j$j $target
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$candidates = @(
    (Join-Path $Root "build\c\graph-engine.exe"),
    (Join-Path $Root "build\c\graph-engine"),
    (Join-Path $Root "build\c\graph-engine.exe"),
    (Join-Path $Root "build\c\graph-engine")
)
$found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($found) {
    Write-Host "==> 成功: $found" -ForegroundColor Green
} else {
    Write-Warning "构建命令已返回，但未找到预期产物路径，请检查 build/c/"
}
