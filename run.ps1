# ════════════════════════════════════════════════════════════════════════════
#  Nexus ERP — Dev Runner
#  Starts Backend (FastAPI/uvicorn on :8000) AND Frontend (Next.js on :3001)
#  Usage: .\run.ps1
# ════════════════════════════════════════════════════════════════════════════

$Root     = $PSScriptRoot
$Backend  = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

# ── Colour helpers ──────────────────────────────────────────────────────────
function Info  ($msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Ok    ($msg) { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Warn  ($msg) { Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Err   ($msg) { Write-Host "  ✗ $msg" -ForegroundColor Red }

Clear-Host
Write-Host ""
Write-Host "  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗    ███████╗██████╗ ██████╗ " -ForegroundColor Blue
Write-Host "  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝    ██╔════╝██╔══██╗██╔══██╗" -ForegroundColor Blue
Write-Host "  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗    █████╗  ██████╔╝██████╔╝" -ForegroundColor Blue
Write-Host "  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║    ██╔══╝  ██╔══██╗██╔═══╝ " -ForegroundColor Blue
Write-Host "  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║    ███████╗██║  ██║██║     " -ForegroundColor Blue
Write-Host "  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚══════╝╚═╝  ╚═╝╚═╝     " -ForegroundColor Blue
Write-Host ""
Write-Host "  المرجع الرقمي للتاجر المصري — نظام الإدارة المتكامل" -ForegroundColor White
Write-Host ""

# ── Check prerequisites ─────────────────────────────────────────────────────
$uvicorn = Join-Path $Backend ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicorn)) {
    Err "لم يتم العثور على .venv في backend/"
    Warn "شغّل: cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$nextBin = Join-Path $Frontend "node_modules\.bin\next.cmd"
if (-not (Test-Path $nextBin)) {
    Err "لم يتم العثور على node_modules في frontend/"
    Warn "شغّل: cd frontend && npm install"
    exit 1
}

# ── Start Backend ───────────────────────────────────────────────────────────
Info "Starting Backend  →  http://localhost:8000"
$backendJob = Start-Process powershell -PassThru -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Backend'; Write-Host '🐍 Nexus ERP Backend → http://localhost:8000' -ForegroundColor Cyan; Write-Host '   Swagger UI → http://localhost:8000/docs' -ForegroundColor DarkCyan; & '.venv\Scripts\uvicorn.exe' app.main:app --reload --host 0.0.0.0 --port 8000"
)

Start-Sleep -Seconds 2

# ── Start Frontend ──────────────────────────────────────────────────────────
Info "Starting Frontend →  http://localhost:3001"
$frontendJob = Start-Process powershell -PassThru -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Frontend'; Write-Host '▲ Nexus ERP Frontend → http://localhost:3001' -ForegroundColor Blue; node_modules\.bin\next.cmd dev --port 3001"
)

Start-Sleep -Seconds 3

# ── Summary ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌─────────────────────────────────────────────────────┐" -ForegroundColor DarkGray
Write-Host "  │         Nexus ERP — Dev Servers Running             │" -ForegroundColor DarkGray
Write-Host "  ├─────────────────────────────────────────────────────┤" -ForegroundColor DarkGray
Write-Host "  │  Frontend   →  http://localhost:3001                │" -ForegroundColor White
Write-Host "  │  Backend    →  http://localhost:8000                │" -ForegroundColor White
Write-Host "  │  API Docs   →  http://localhost:8000/docs           │" -ForegroundColor White
Write-Host "  └─────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
Write-Host ""
Ok "Both servers are starting in separate windows."
Write-Host "  اضغط أي زرار لإغلاق هذه النافذة..." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
