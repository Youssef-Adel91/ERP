<#
.SYNOPSIS
    Omni ERP — Full E2E Dev Boot Script
    Starts Docker infrastructure, runs Alembic migrations, then launches
    FastAPI and Next.js in separate terminal windows.

.USAGE
    From the monorepo root (ERP/):
        .\start.ps1

.DESCRIPTION
    Step 1 — Docker  : starts PostgreSQL (port 5432) and Redis (port 6379)
    Step 2 — Alembic : waits for Postgres health, then runs `alembic upgrade head`
    Step 3 — Backend : opens a new window → Uvicorn on http://localhost:8000
    Step 4 — Frontend: opens a new window → Next.js  on http://localhost:3000
#>

# ── Config ────────────────────────────────────────────────────────────────────
$Root        = $PSScriptRoot
$BackendPath = Join-Path $Root "backend"
$FrontendPath= Join-Path $Root "frontend"
$VenvActivate= Join-Path $BackendPath ".venv\Scripts\Activate.ps1"
$AlembicExe  = Join-Path $BackendPath ".venv\Scripts\alembic.exe"

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       Omni ERP — E2E Development Boot Script        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Guard checks ─────────────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Docker is not installed or not on PATH." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $VenvActivate)) {
    Write-Host "[ERROR] Python .venv not found at: $VenvActivate" -ForegroundColor Red
    Write-Host "        Run: cd backend && python -m venv .venv && .venv\Scripts\Activate.ps1 && pip install -e ." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $AlembicExe)) {
    Write-Host "[ERROR] alembic.exe not found. Is the venv installed correctly?" -ForegroundColor Red
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Docker: Start PostgreSQL + Redis
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[1/4] Starting Docker infrastructure (PostgreSQL + Redis)..." -ForegroundColor Green
docker compose -f "$Root\docker-compose.yml" up -d db redis

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] docker compose failed. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

Write-Host "      Waiting for PostgreSQL to become healthy..." -ForegroundColor DarkGray
$MaxWait = 30   # seconds
$Elapsed = 0
$Interval= 2

do {
    Start-Sleep -Seconds $Interval
    $Elapsed += $Interval
    $Health = docker inspect --format="{{.State.Health.Status}}" omni_erp_db 2>$null
    if ($Health -eq "healthy") { break }
    Write-Host "      ...[$Elapsed s] DB status: $Health" -ForegroundColor DarkGray
} while ($Elapsed -lt $MaxWait)

if ($Health -ne "healthy") {
    Write-Host "[ERROR] PostgreSQL did not become healthy within ${MaxWait}s. Check: docker logs omni_erp_db" -ForegroundColor Red
    exit 1
}
Write-Host "      ✅ PostgreSQL is healthy on localhost:5432" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Alembic: Apply migrations
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[2/4] Running Alembic migrations (alembic upgrade head)..." -ForegroundColor Green

Push-Location $BackendPath
try {
    & $AlembicExe -n public upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Alembic migration failed. Check the output above." -ForegroundColor Red
        exit 1
    }
    Write-Host "      ✅ Database schema is up to date." -ForegroundColor Green
} finally {
    Pop-Location
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Backend: FastAPI / Uvicorn (new window)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/4] Launching FastAPI backend  → http://localhost:8000/docs" -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$BackendPath'; " +
    "& '.venv\Scripts\Activate.ps1'; " +
    "Write-Host '🚀 FastAPI starting on http://127.0.0.1:8000' -ForegroundColor Cyan; " +
    "uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
)

# Give Uvicorn a couple of seconds to start binding the port
Start-Sleep -Seconds 2

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Frontend: Next.js (new window)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[4/4] Launching Next.js frontend → http://localhost:3000" -ForegroundColor Green

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FrontendPath'; " +
    "Write-Host '🚀 Next.js starting on http://localhost:3000' -ForegroundColor Cyan; " +
    "npm run dev"
)

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  All services are starting. Open these URLs:         ║" -ForegroundColor Cyan
Write-Host "║                                                      ║" -ForegroundColor Cyan
Write-Host "║  Frontend  →  http://localhost:3000                  ║" -ForegroundColor Cyan
Write-Host "║  API Docs  →  http://localhost:8000/docs             ║" -ForegroundColor Cyan
Write-Host "║  API Alt   →  http://localhost:8000/redoc            ║" -ForegroundColor Cyan
Write-Host "║                                                      ║" -ForegroundColor Cyan
Write-Host "║  To stop:  docker compose down                       ║" -ForegroundColor DarkGray
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

