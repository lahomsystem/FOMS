# Mobile v2 rollout preflight (P0-00C cron + P0-01 cohort + P1-P3 gates)
# Usage: powershell -NoProfile -File scripts/ops/verify_mobile_v2_rollout.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== FOMS Mobile v2 Rollout Preflight ===" -ForegroundColor Cyan
Write-Host "Root: $Root"

function Assert-Exit($label, $exitCode) {
    if ($exitCode -ne 0) {
        Write-Host "[FAIL] $label (exit $exitCode)" -ForegroundColor Red
        exit $exitCode
    }
    Write-Host "[OK] $label" -ForegroundColor Green
}

Write-Host "`n--- P0-00C OrderDraft cleanup cron (dry-run) ---"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$cronOut = python tools/cron/cleanup_order_drafts.py --dry-run 2>&1 | Out-String
$ErrorActionPreference = $prevEap
if ($cronOut -notmatch "mode=dry-run") {
    Write-Host $cronOut
    Write-Host "[FAIL] cleanup_order_drafts dry-run missing expected log" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] cleanup_order_drafts dry-run" -ForegroundColor Green

Write-Host "`n--- APP import ---"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$appOut = python -c "import app; print('APP_OK')" 2>&1 | Out-String
$ErrorActionPreference = $prevEap
if ($appOut -notmatch "APP_OK") {
    Write-Host $appOut
    exit 1
}
Write-Host "[OK] APP_OK" -ForegroundColor Green

Write-Host "`n--- Domain gates P1/P2/P3 ---"
pytest tests/domains/test_p1_gate.py tests/domains/test_p2_gate.py tests/domains/test_p3_gate.py tests/domains/test_mobile_device_qa_contract.py -q
Assert-Exit "P1/P2/P3 + device QA gates" $LASTEXITCODE

Write-Host "`n--- SSOT lint ---"
python tools/design/ssot_lint.py docs/design
Assert-Exit "ssot_lint" $LASTEXITCODE

Write-Host "`n--- Railway ops checklist (manual) ---"
Write-Host "  1. Cron: New Service -> Config Path railway-cron.toml -> DATABASE_URL + SECRET_KEY"
Write-Host "  2. Day1: ERP_MOBILE_V2_ENABLED=true, FOMS_V3_SHELL_COHORT=<user_id>"
Write-Host "  7. Full: FOMS_V3_SHELL_COHORT=all (any authenticated user)"
Write-Host "  3. Day4+: FOMS_OFFLINE_SW_ENABLED=true (after device QA)"
Write-Host "  4. Day5+: FOMS_BOTTOM_NAV_HTMX_ENABLED=true (after device QA)"
Write-Host "  See docs/runbooks/mobile-v2-railway-ops.md"

Write-Host "`n=== Preflight PASS (local). Railway env + device QA remain ops. ===" -ForegroundColor Cyan
