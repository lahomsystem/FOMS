# EPT-B8: login (env) -> set FOMS_STAGING_COOKIE -> run HTTP evidence harness (JSON).
# Requires: FOMS_STAGING_USERNAME, FOMS_STAGING_PASSWORD in environment.
# Optional: FOMS_STAGING_BASE_URL (default https://lahom-dev.up.railway.app), FOMS_STAGING_ORDER_ID (default 2732)
#
# Usage (PowerShell 5.x, repo root):
#   . .\tools\harness\ept_b8_staging_full_evidence.ps1
# Or:
#   powershell -NoProfile -File ".\tools\harness\ept_b8_staging_full_evidence.ps1"

$ErrorActionPreference = "Stop"

if (-not $env:FOMS_STAGING_USERNAME -or -not $env:FOMS_STAGING_PASSWORD) {
    Write-Error "Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD (use .env or session scope; never commit)."
    exit 2
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$base = if ($env:FOMS_STAGING_BASE_URL) { $env:FOMS_STAGING_BASE_URL } else { "https://lahom-dev.up.railway.app" }
$orderId = if ($env:FOMS_STAGING_ORDER_ID) { $env:FOMS_STAGING_ORDER_ID } else { "2732" }

$loginOut = & python "tools\harness\ept_b8_staging_session_from_login.py" --base $base 2>&1
if ($LASTEXITCODE -ne 0) {
    $loginOut | ForEach-Object { Write-Host $_ }
    exit $LASTEXITCODE
}

# Single-line stdout: session_staging=... (merge stderr into stream only on failure path above)
if ($loginOut -is [System.Array]) {
    $cookieLine = ($loginOut | Where-Object { $_ -match '^session_staging=' } | Select-Object -First 1)
    if (-not $cookieLine) { $cookieLine = $loginOut[-1] }
} else {
    $cookieLine = $loginOut
}
$env:FOMS_STAGING_COOKIE = $cookieLine.ToString().Trim()

& python "tools\harness\ept_b8_staging_http_evidence.py" --base $base --order-id ([int]$orderId) --include-g1 --json
exit $LASTEXITCODE
