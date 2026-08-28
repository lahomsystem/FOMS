# Deploy vs Production ERP stress — L1 (HTTP TTFB) + L2 (browser tab stress).
# Win11 PowerShell 5.x, repo root에서 실행.
#
# Usage:
#   $env:FOMS_STAGING_USERNAME = "..."
#   $env:FOMS_STAGING_PASSWORD = "..."
#   powershell -NoProfile -File "scripts/ops/compare_deploy_production_stress.ps1"
#
# Optional:
#   -DeployUrl  "https://lahom-dev.up.railway.app"
#   -ProductionUrl "https://lahom-production.up.railway.app"
#   -SkipBrowser  # HTTP TTFB only (Playwright 미설치 시)

param(
    [string]$DeployUrl = "https://lahom-dev.up.railway.app",
    [string]$ProductionUrl = "https://lahom-production.up.railway.app",
    [switch]$SkipBrowser
)
# Win11 cp949 console: force UTF-8 output so Korean text is not mangled.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false


$ErrorActionPreference = "Stop"

if (-not $env:FOMS_STAGING_USERNAME -or -not $env:FOMS_STAGING_PASSWORD) {
    Write-Error "Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD before running."
    exit 2
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$ts = Get-Date -Format "yyyy-MM-ddTHHmmss"
$evidenceDir = Join-Path $repoRoot "docs\harness\evidence"
if (-not (Test-Path $evidenceDir)) {
    New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
}
$outPath = Join-Path $evidenceDir "stress-compare-$ts.json"

Write-Host "=== FOMS deploy vs production stress (L1 + L2) ===" -ForegroundColor Cyan
Write-Host "Deploy:     $DeployUrl"
Write-Host "Production: $ProductionUrl"
Write-Host ""

# --- L1: fragment TTFB ---
Write-Host "[L1] measure_erp_tab_switch.py ..." -ForegroundColor Yellow
$ttfbRaw = & python "tools\perf\measure_erp_tab_switch.py" $DeployUrl $ProductionUrl 2>&1
if ($LASTEXITCODE -ne 0) {
    $ttfbRaw | ForEach-Object { Write-Host $_ }
    exit $LASTEXITCODE
}
$ttfbJson = $ttfbRaw | Out-String
$ttfbParsed = $ttfbJson | ConvertFrom-Json

# --- L2: browser tab stress (optional) ---
$tabParsed = $null
$tabError = $null
if (-not $SkipBrowser) {
    Write-Host "[L2] browser_tab_stress_compare.py ..." -ForegroundColor Yellow
    try {
        $tabRaw = & python "tools\perf\browser_tab_stress_compare.py" $DeployUrl $ProductionUrl 2>&1
        if ($LASTEXITCODE -ne 0) {
            $tabError = ($tabRaw | Out-String).Trim()
            Write-Warning "L2 skipped or failed: $tabError"
        } else {
            $tabParsed = ($tabRaw | Out-String) | ConvertFrom-Json
        }
    } catch {
        $tabError = $_.Exception.Message
        Write-Warning "L2 exception: $tabError"
    }
} else {
    Write-Host "[L2] skipped (-SkipBrowser)" -ForegroundColor DarkGray
}

function Get-EnvLayer {
    param(
        [string]$BaseUrl,
        [object]$TtfbAll,
        [object]$TabAll
    )
    $ttfb = $TtfbAll | Where-Object { $_.base -eq $BaseUrl } | Select-Object -First 1
    $tab = $null
    if ($TabAll) {
        $tab = $TabAll | Where-Object { $_.base -eq $BaseUrl } | Select-Object -First 1
    }
    return @{
        fragment_ttfb = $ttfb
        tab_stress      = $tab
    }
}

$report = @{
    meta = @{
        run_id    = (Get-Date -Format "o")
        script    = "scripts/ops/compare_deploy_production_stress.ps1"
        deploy    = $DeployUrl
        production = $ProductionUrl
        layers    = @("L1_fragment_ttfb", "L2_tab_stress")
        skip_browser = [bool]$SkipBrowser
        l2_error  = $tabError
    }
    environments = @{
        deploy = @{
            base_url = $DeployUrl
            layers   = (Get-EnvLayer -BaseUrl $DeployUrl -TtfbAll $ttfbParsed -TabAll $tabParsed)
        }
        production = @{
            base_url = $ProductionUrl
            layers   = (Get-EnvLayer -BaseUrl $ProductionUrl -TtfbAll $ttfbParsed -TabAll $tabParsed)
        }
    }
    comparison = @{
        note = "Run cursor-ide-browser (L3) + user-postgres (L4) per docs/guides/prompts/deploy-production-stress-test.cursor.md"
    }
    verdict = @{
        overall_faster = "inconclusive"
        primary_bottleneck_dimension = $null
        safe_to_promote = $false
        notes = "Automated L1/L2 only. Complete L3-L5 before promotion decision."
    }
}

$jsonText = $report | ConvertTo-Json -Depth 20 -Compress:$false
[System.IO.File]::WriteAllText($outPath, $jsonText, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Wrote: $outPath" -ForegroundColor Green
Write-Host $jsonText

exit 0
