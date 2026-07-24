<#
.SYNOPSIS
    Omni ERP — Universal Dev Boot Script
    Starts the FastAPI backend and Next.js frontend in separate terminal windows.

.USAGE
    From the monorepo root (ERP/):
        .\start.ps1

.DESCRIPTION
    Window 1 — Backend  : activates Python venv → runs Uvicorn on port 8000
    Window 2 — Frontend : runs Next.js dev server on port 3000
#>

$Root = $PSScriptRoot

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        Omni ERP — Starting Dev Environment       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Backend ───────────────────────────────────────────────────────────────────
$backendPath = Join-Path $Root "backend"
$venvActivate = Join-Path $backendPath ".venv\Scripts\Activate.ps1"

if (-not (Test-Path $backendPath)) {
    Write-Host "[ERROR] Backend directory not found: $backendPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $venvActivate)) {
    Write-Host "[WARN ] No .venv found at $venvActivate" -ForegroundColor Yellow
    Write-Host "        Create it first with: python -m venv .venv && .venv\Scripts\Activate.ps1 && pip install -e ." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "[1/2] Launching Backend  → http://localhost:8000/docs" -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$backendPath'; " +
    "if (Test-Path '.venv\Scripts\Activate.ps1') { & '.venv\Scripts\Activate.ps1' } else { Write-Host 'No venv found, using system Python.' -ForegroundColor Yellow }; " +
    "Write-Host '🚀 Starting FastAPI on http://127.0.0.1:8000' -ForegroundColor Cyan; " +
    "uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
)

# Brief pause so both windows don't open simultaneously
Start-Sleep -Seconds 1

# ── Frontend ──────────────────────────────────────────────────────────────────
$frontendPath = Join-Path $Root "frontend"

if (-not (Test-Path $frontendPath)) {
    Write-Host "[ERROR] Frontend directory not found: $frontendPath" -ForegroundColor Red
    exit 1
}

Write-Host "[2/2] Launching Frontend → http://localhost:3000" -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$frontendPath'; " +
    "Write-Host '🚀 Starting Next.js on http://localhost:3000' -ForegroundColor Cyan; " +
    "npm run dev"
)

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Both servers are starting in separate windows.  ║" -ForegroundColor Cyan
Write-Host "║                                                  ║" -ForegroundColor Cyan
Write-Host "║  Backend  → http://localhost:8000/docs           ║" -ForegroundColor Cyan
Write-Host "║  Frontend → http://localhost:3000                ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
