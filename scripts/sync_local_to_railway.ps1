# 원격(Railway) DB 초기화 후 로컬 Postgres 완전 복사
# GDM 절차서: docs/RAILWAY_LOCAL_TO_REMOTE_SYNC.md
# 사용: 프로젝트 루트에서 .\scripts\sync_local_to_railway.ps1
#
# ⛔ 금지: 로컬 Postgres DB는 절대 삭제/초기화하지 않음.
#    로컬에는 pg_dump(읽기)만 수행하고, pg_restore(--clean)는 원격(DATABASE_URL)에만 적용.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $ProjectRoot "app.py"))) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

$LocalDbUrl = if ($env:LOCAL_DATABASE_URL) { $env:LOCAL_DATABASE_URL } else { "postgresql://postgres:lahom@localhost/furniture_orders" }
$DumpPath = Join-Path $ProjectRoot "foms.dump"

Write-Host "=== Sync local Postgres to Railway (remote reset + restore) ===" -ForegroundColor Cyan
Write-Host "Local DB: $LocalDbUrl"
Write-Host "Dump file: $DumpPath"
Write-Host "Target: Railway (linked project)"
Write-Host ""
$confirm = (Read-Host "Only REMOTE (Railway) data will be replaced. Local DB is READ-ONLY (pg_dump only). Type y or yes to continue").Trim().ToLower()
if ($confirm -ne "yes" -and $confirm -ne "y") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 1
}

# 1) pg_dump 경로
$pgDump = $null
foreach ($p in @(
    "pg_dump",
    "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    "C:\Program Files\PostgreSQL\15\bin\pg_dump.exe"
)) {
    if (Get-Command $p -ErrorAction SilentlyContinue) { $pgDump = $p; break }
    if ($p -like "*\*" -and (Test-Path $p)) { $pgDump = $p; break }
}
if (-not $pgDump) {
    Write-Host "ERROR: pg_dump not found. Install PostgreSQL client or add to PATH." -ForegroundColor Red
    exit 1
}

# 2) Local dump (read-only)
Write-Host "`n[1/3] Dumping local DB ..." -ForegroundColor Green
& $pgDump -Fc --no-owner --no-privileges -f $DumpPath $LocalDbUrl
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dump failed." -ForegroundColor Red
    exit 1
}
Write-Host "Dump done: $DumpPath" -ForegroundColor Green

# 3) Railway: from local PC, DATABASE_URL from Railway uses internal host (postgres.railway.internal) which does not resolve. Use PUBLIC URL.
$RemoteUrl = $env:RAILWAY_PUBLIC_DATABASE_URL
if (-not $RemoteUrl) {
    Write-Host "`n[2/3] Restoring to Railway ..." -ForegroundColor Green
    Write-Host "RAILWAY_PUBLIC_DATABASE_URL not set. Trying 'railway run' (may fail with 'Name or service not known' from local)." -ForegroundColor Gray
    railway status 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Railway not linked. Run 'railway link' then retry." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`n[2/3] Restoring to Railway (using RAILWAY_PUBLIC_DATABASE_URL) ..." -ForegroundColor Green
}
if ($RemoteUrl -and $RemoteUrl.StartsWith("postgres://")) {
    $RemoteUrl = "postgresql://" + $RemoteUrl.Substring(11)
}

$pgRestore = $null
foreach ($p in @("pg_restore", "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe", "C:\Program Files\PostgreSQL\15\bin\pg_restore.exe")) {
    if (Get-Command $p -ErrorAction SilentlyContinue) { $pgRestore = $p; break }
    if ($p -like "*\*" -and (Test-Path $p)) { $pgRestore = $p; break }
}
if (-not $pgRestore) {
    Write-Host "ERROR: pg_restore not found." -ForegroundColor Red
    exit 1
}

$restoreOk = $false
if ($RemoteUrl) {
    & $pgRestore --clean --if-exists --no-owner --no-privileges -d $RemoteUrl $DumpPath
    $restoreOk = ($LASTEXITCODE -eq 0)
} else {
    railway run powershell -NoProfile -Command "& '$pgRestore' --clean --if-exists --no-owner --no-privileges -d `$env:DATABASE_URL '$DumpPath'"
    $restoreOk = ($LASTEXITCODE -eq 0)
}

if (-not $restoreOk) {
    Write-Host "Restore failed. From local PC Railway injects an internal host that does not resolve." -ForegroundColor Yellow
    Write-Host "Set the PUBLIC Postgres URL and re-run:" -ForegroundColor Yellow
    Write-Host "  1. Railway Dashboard -> Your Project -> Postgres -> Connect -> copy 'Postgres Connection URL' (use Public, not internal)" -ForegroundColor Gray
    Write-Host "  2. $env:RAILWAY_PUBLIC_DATABASE_URL = 'postgresql://user:pass@host:port/railway'" -ForegroundColor Gray
    Write-Host "  3. .\scripts\sync_local_to_railway.ps1" -ForegroundColor Gray
} else {
    Write-Host "Restore done." -ForegroundColor Green
}

# 4) Bootstrap (optional from local; runs on deploy. Use public URL to avoid encoding errors.)
Write-Host "`n[3/3] Running railway_bootstrap.py ..." -ForegroundColor Green
if ($RemoteUrl) {
    $env:DATABASE_URL = $RemoteUrl
    python railway_bootstrap.py
} else {
    railway run python railway_bootstrap.py
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "Bootstrap had warnings or failed. Tables already exist from restore; bootstrap also runs on deploy." -ForegroundColor Yellow
} else {
    Write-Host "Bootstrap done." -ForegroundColor Green
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
Write-Host "Verify on Railway app: orders, chat, estimates match local. Dump file (sensitive): $DumpPath" -ForegroundColor Gray
