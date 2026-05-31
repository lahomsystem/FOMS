<#
.SYNOPSIS
  Fast local smoke checks before pushing to deploy/main (mirrors CI test job subset).

.DESCRIPTION
  Target runtime: ~2-5 minutes. Sets in-memory SQLite test env and runs import,
  harness verify, design SSOT lint, and a curated pytest subset that catches
  common CI failures. Does NOT run on git push automatically — run manually.

.PARAMETER Full
  Slow pre-merge check: full pytest suite (ignores tests/visual, no playwright).
  Expect several minutes.

.PARAMETER Visual
  Local-only Playwright visual regression (tests/visual, win32 baselines).
  Requires `pip install playwright; playwright install chromium`. Skipped with a
  notice when playwright is missing. CI is unaffected (CI ignores tests/visual);
  baselines are platform-specific so do not regenerate linux baselines here.
  Combine with default subset or -Full.

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Full

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual

.NOTES
  Win11 / PowerShell 5.x. GitHub Actions still runs the full CI pipeline on push.
  See docs/guides/PRE_PUSH_SMOKE.md
#>

param(
    [switch]$Full,
    [switch]$Visual
)

$ErrorActionPreference = "Stop"

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

$script:FailedSteps = New-Object 'System.Collections.Generic.List[string]'

function Write-StepHeader {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Write-StepOk {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-StepSkip {
    param([string]$Message)
    Write-Host "[SKIP] $Message" -ForegroundColor Yellow
}

function Write-StepFail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Invoke-SmokeStep {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-StepHeader $Name
    try {
        & $Action
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
            throw "Command exited with code $LASTEXITCODE"
        }
        Write-StepOk $Name
    } catch {
        $detail = $_.Exception.Message
        Write-StepFail "$Name — $detail"
        $script:FailedSteps.Add($Name)
    }
}

function Invoke-PythonCommand {
    param([string]$CommandLine)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = $CommandLine
    $psi.WorkingDirectory = $root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if ($stdout) { Write-Host $stdout }
    if ($stderr) { Write-Host $stderr -ForegroundColor DarkGray }

    if ($proc.ExitCode -ne 0) {
        throw "python $CommandLine (exit $($proc.ExitCode))"
    }
}

Write-Host "FOMS pre-push smoke" -ForegroundColor Cyan
Write-Host "Root: $root"
Write-Host "Mode: $(if ($Full) { 'Full (slow)' } else { 'Fast subset' })$(if ($Visual) { ' + Visual regression' })"

# Test env (matches .github/workflows/ci.yml test job)
$env:DATABASE_URL = "sqlite:///:memory:"
$env:SECRET_KEY = "ci-secret-key"
$env:FLASK_ENV = "testing"

Invoke-SmokeStep -Name "APP import (APP_OK)" -Action {
    Invoke-PythonCommand '-c "import app; print(''APP_OK'')"'
}

$verifyPath = Join-Path $root "tools\harness\verify_result.py"
if (Test-Path $verifyPath) {
    Invoke-SmokeStep -Name "Harness verify_result.py" -Action {
        Invoke-PythonCommand "tools/harness/verify_result.py --json"
    }
} else {
    Write-StepSkip "tools/harness/verify_result.py not found"
}

$ssotPath = Join-Path $root "tools\design\ssot_lint.py"
if (Test-Path $ssotPath) {
    Invoke-SmokeStep -Name "Design SSOT lint" -Action {
        Invoke-PythonCommand "tools/design/ssot_lint.py docs/design"
    }
} else {
    Write-StepSkip "tools/design/ssot_lint.py not found"
}

if ($Full) {
    Invoke-SmokeStep -Name "Full pytest (no visual, no playwright) — SLOW" -Action {
        Invoke-PythonCommand "-m pytest -v --ignore=tests/visual -p no:playwright"
    }
} else {
    $pytestTargets = @(
        "tests/contracts/runtime/test_dockerfile_deploy_contract.py",
        "tests/domains/test_foms_namespace_imports.py",
        "tests/domains/test_foms_search_overlay.py::test_search_overlay_template_contract",
        "tests/domains/test_p2_htmx_fragment.py",
        "tests/visual/test_staging_mobile_v2_assets.py",
        "tests/visual/test_p1_mockup_structure.py",
        "tests/visual/test_p1_mockup_png_baseline.py"
    )

    $existingTargets = @()
    foreach ($target in $pytestTargets) {
        $filePart = ($target -split "::")[0]
        $fullPath = Join-Path $root ($filePart -replace "/", "\")
        if (Test-Path $fullPath) {
            $existingTargets += $target
        } else {
            Write-StepSkip "Missing test file: $filePart"
        }
    }

    if ($existingTargets.Count -gt 0) {
        $pytestArgs = "-m pytest -v " + ($existingTargets -join " ")
        Invoke-SmokeStep -Name "Pytest subset ($($existingTargets.Count) targets)" -Action {
            Invoke-PythonCommand $pytestArgs
        }
    } else {
        Write-StepFail "No pytest targets found"
        $script:FailedSteps.Add("Pytest subset")
    }
}

if ($Visual) {
    # Local-only Playwright visual regression. CI ignores tests/visual and uses
    # linux baselines, so this never gates CI; it catches local win32 drift.
    & python -c "import playwright" 2>$null
    $playwrightOk = ($LASTEXITCODE -eq 0)

    if (-not $playwrightOk) {
        Write-StepSkip "Visual regression — playwright not installed (pip install playwright; python -m playwright install chromium)"
    } else {
        if (-not (Test-Path "C:\tmp")) {
            New-Item -ItemType Directory -Path "C:\tmp" -Force | Out-Null
        }
        Invoke-SmokeStep -Name "Visual regression (tests/visual, win32 baselines, local only)" -Action {
            # File-backed SQLite so the Playwright live-server fixture shares state.
            $env:TEMP = "C:\tmp"
            $env:TMP = "C:\tmp"
            $env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
            Invoke-PythonCommand "-m pytest tests/visual -q"
        }
    }
}

Write-Host ""
if ($script:FailedSteps.Count -gt 0) {
    Write-Host "=== PRE-PUSH SMOKE FAILED ===" -ForegroundColor Red
    Write-Host "Failed steps:"
    foreach ($step in $script:FailedSteps) {
        Write-Host "  - $step" -ForegroundColor Red
    }
    exit 1
}

Write-Host "=== PRE-PUSH SMOKE PASSED ===" -ForegroundColor Green
exit 0
