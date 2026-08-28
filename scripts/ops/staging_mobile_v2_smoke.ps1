# Staging mobile v2 visual smoke — static assets + login page cohort markers
# Usage:
#   powershell -NoProfile -File scripts/ops/staging_mobile_v2_smoke.ps1
#   powershell -NoProfile -File scripts/ops/staging_mobile_v2_smoke.ps1 -BaseUrl "https://lahom-dev.up.railway.app"

param(
    [string]$BaseUrl = "https://lahom-dev.up.railway.app"
)
# Win11 cp949 console: force UTF-8 output so Korean text is not mangled.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false


$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Write-Host "=== FOMS Staging Mobile v2 Smoke ===" -ForegroundColor Cyan
Write-Host "BaseUrl: $BaseUrl"
Write-Host "Root: $root"

$assets = @(
    "/static/css/foundation/foms-mobile-surfaces.css",
    "/static/css/foundation/foms-shell.css",
    "/static/js/foms/mobile-queue-scroll.js",
    "/static/js/foms/wizard-attachments.js"
)

$fail = 0
foreach ($path in $assets) {
    $url = ($BaseUrl.TrimEnd("/") + $path)
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 30
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
            Write-Host "[OK] $path ($($resp.StatusCode))" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] $path status $($resp.StatusCode)" -ForegroundColor Red
            $fail++
        }
    } catch {
        Write-Host "[FAIL] $path — $($_.Exception.Message)" -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
Write-Host "--- Env checklist (Railway Web service) ---" -ForegroundColor Yellow
Write-Host "  ERP_MOBILE_V2_ENABLED=true"
Write-Host "  FOMS_V3_SHELL_COHORT=all  (or pilot user id)"
Write-Host "  See docs/runbooks/mobile-v2-railway-ops.md"
Write-Host ""
Write-Host "--- Manual 390px browser checks ---" -ForegroundColor Yellow
Write-Host "  1. Login cohort user -> $BaseUrl/erp/dashboard"
Write-Host "  2. Expect: foms-mobile-v2-dashboard, chip-strip, foms-shell-fab"
Write-Host "  3. Expect hidden: .erp-pro-header (mobile v2 layout)"
Write-Host "  4. Order detail: $BaseUrl/erp/orders/<id>/mobile -> foms-detail-hero"
Write-Host ""
Write-Host "Evidence template: docs/runbooks/staging-mobile-v2-evidence-20260531.md"

if ($fail -gt 0) {
    Write-Host "=== FAIL ($fail asset errors) ===" -ForegroundColor Red
    exit 1
}
Write-Host "=== PASS (static assets reachable) ===" -ForegroundColor Green
exit 0
