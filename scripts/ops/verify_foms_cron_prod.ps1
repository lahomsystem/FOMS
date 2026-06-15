# Verify production FOMS-cron Railway configuration (no mutations).
# Usage: powershell -NoProfile -File scripts/ops/verify_foms_cron_prod.ps1

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

function Invoke-RailwayQuiet {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$RailwayArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & railway @RailwayArgs 2>&1 | Out-String
    } finally {
        $ErrorActionPreference = $prev
    }
}

Write-Host "[1/3] GraphQL dry-run (production FOMS-cron)" -ForegroundColor Cyan
$dryRun = python tools/ops/railway_configure_cron_service.py --target production --dry-run 2>&1 | Out-String
Write-Host $dryRun

$required = @(
    '"startCommand": "python tools/cron/cleanup_order_drafts.py --execute"',
    '"cronSchedule": "0 17 * * *"',
    '"railwayConfigFile": "railway-cron.toml"'
)
foreach ($needle in $required) {
    if ($dryRun -notmatch [regex]::Escape($needle)) {
        Write-Host "[FAIL] Missing expected config: $needle" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[OK] production cron config fields present" -ForegroundColor Green

Write-Host "[2/3] Recent logs: gunicorn should be absent" -ForegroundColor Cyan
railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -s FOMS-cron 2>&1 | Out-Null
$gunicornLogs = Invoke-RailwayQuiet logs --lines 30 --since 24h --filter "gunicorn"
if ($gunicornLogs -match "gunicorn" -and $gunicornLogs -notmatch "Usage: railway") {
    Write-Host "[WARN] gunicorn lines found in last 24h (cron may still be misconfigured):" -ForegroundColor Yellow
    Write-Host $gunicornLogs
} else {
    Write-Host "[OK] no gunicorn logs in last 24h" -ForegroundColor Green
}

Write-Host "[3/3] Service should be idle between cron runs" -ForegroundColor Cyan
$sshTry = Invoke-RailwayQuiet ssh -s FOMS-cron "echo awake"
if ($sshTry -match "scaled to zero|not running|Sleep when idle|unexpected state") {
    Write-Host "[OK] cron service idle (expected between scheduled runs)" -ForegroundColor Green
} elseif ($sshTry -match "awake") {
    Write-Host "[OK] service reachable via SSH" -ForegroundColor Green
} else {
    Write-Host "[INFO] SSH status:" -ForegroundColor Yellow
    Write-Host $sshTry
}

Write-Host "Done. Next scheduled run: UTC 17:00 (KST 02:00). Expect log: [cleanup_order_drafts] mode=execute ..." -ForegroundColor Cyan
