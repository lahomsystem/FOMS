<#
.SYNOPSIS
  Fast local smoke checks before pushing to deploy/main (mirrors CI test job subset).

.DESCRIPTION
  Target runtime: ~2-3 minutes. Sets in-memory SQLite test env and runs import,
  harness verify, design SSOT lint, inventory regeneration, and the FULL pytest
  suite (tests/harness excluded) in parallel. There is no curated target list —
  curated lists go stale. Does NOT run on git push automatically — run manually.

.PARAMETER Full
  Adds tests/harness (~2 minutes locally) on top of the default run. The default
  already covers every other test, so -Full is only about tests/harness.

.PARAMETER Visual
  Local-only Playwright visual regression (tests/visual, win32 baselines).
  Requires `pip install playwright; playwright install chromium`. Skipped with a
  notice when playwright is missing. CI is unaffected (CI ignores tests/visual);
  baselines are platform-specific so do not regenerate linux baselines here.
  Combine with the default run or -Full.

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Full

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual

.PARAMETER PerfGate
  Staging 성능 게이트(tools/perf/staging_perf_gate.py)를 마지막 스텝으로 실행.
  배포 후 검증 도구라 기본(무플래그)에는 안 낀다. deploy 배포 완료 후 검증 /
  production 승격 직전 필수. env FOMS_STAGING_USERNAME/PASSWORD 없으면 SKIP(실패 아님).

.EXAMPLE
  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -PerfGate

.NOTES
  Win11 / PowerShell 5.x. GitHub Actions still runs the full CI pipeline on push.
  See docs/guides/PRE_PUSH_SMOKE.md
#>

param(
    [switch]$Full,
    [switch]$Visual,
    [switch]$PerfGate
)
# Win11 cp949 console: force UTF-8 output so Korean text is not mangled.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false


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
    # stderr 를 먼저 비동기 수집 — stdout ReadToEnd 중 stderr 버퍼 포화 데드락(고전 .NET 함정) 방지.
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $stderrTask.Result
    $proc.WaitForExit()

    if ($stdout) { Write-Host $stdout }
    if ($stderr) { Write-Host $stderr -ForegroundColor DarkGray }

    if ($proc.ExitCode -ne 0) {
        throw "python $CommandLine (exit $($proc.ExitCode))"
    }
}

Write-Host "FOMS pre-push smoke" -ForegroundColor Cyan
Write-Host "Root: $root"
Write-Host "Mode: $(if ($Full) { 'Full (+harness)' } else { 'Default (full suite, no harness)' })$(if ($Visual) { ' + Visual regression' })$(if ($PerfGate) { ' + Staging perf gate' })"

$visualStaleScript = Join-Path $root "scripts\ops\visual_baseline_stale.py"
$visualGateRequired = $false
$win32BaselineStale = $false

if (Test-Path $visualStaleScript) {
    Write-StepHeader "Visual-affecting change gate (CSS/templates/static)"
    $prevErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $sinceRef = ""
    $remoteDeploy = (& git rev-parse --verify origin/deploy 2>$null)
    if ($LASTEXITCODE -eq 0) {
        $sinceRef = "origin/deploy"
    }

    $listArgs = @("scripts/ops/visual_baseline_stale.py", "--list-visual-affecting-changes")
    if ($sinceRef) {
        $listArgs += @("--since-ref", $sinceRef)
    }
    & python @listArgs 2>&1 | ForEach-Object {
        Write-Host "  visual change: $_" -ForegroundColor Yellow
        $visualGateRequired = $true
    }
    if ($LASTEXITCODE -eq 1) {
        $visualGateRequired = $true
    } else {
        Write-StepOk "No pending visual-affecting path changes detected"
    }

    & python scripts/ops/visual_baseline_stale.py --check-win32-vs-sources 2>&1 | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Yellow
    }
    if ($LASTEXITCODE -eq 1) {
        $win32BaselineStale = $true
        if (-not $Visual) {
            Write-StepSkip "win32 baseline stale vs CSS/templates — PNG gate skipped (structural tests only; see PRE_PUSH_SMOKE.md)"
        } else {
            Write-Host "[WARN] win32 baselines older than visual sources — -Visual must pass after --update-snapshots" -ForegroundColor Yellow
        }
    } else {
        Write-StepOk "win32 baselines fresh vs visual sources"
    }

    if ($visualGateRequired -and -not $Visual) {
        Write-StepSkip "Visual-affecting files changed — default gate uses test_p1_mockup_* structural tests (not PNG -Visual)"
        Write-Host "  Optional full PNG regression: powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual" -ForegroundColor DarkGray
    } elseif ($visualGateRequired -and $Visual) {
        Write-StepOk "Visual-affecting changes present; -Visual enabled"
    }
    $ErrorActionPreference = $prevErrorAction
} else {
    Write-StepSkip "scripts/ops/visual_baseline_stale.py not found"
}

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

# 인벤토리 자동 재생성 — 사람이 재생성 명령 5개를 기억할 필요를 없앤다.
# 생성물이 낡으면 계약 테스트가 red 를 내는데(test_inventory_matches_fresh_scan 등),
# 2026-09 CI red 의 반복 원인이었다. 탐지는 아래 전체 스위트가 하고, 여기서는 먼저 고쳐 둔다.
# 줄번호만 밀린 무의미한 변화는 도구가 되돌리므로 커밋이 더러워지지 않는다(도구 docstring 참조).
$refreshPath = Join-Path $root "tools/harness/refresh_inventories.py"
if (Test-Path $refreshPath) {
    Write-StepHeader "인벤토리 자동 재생성 (docs/harness/*.json)"
    & python tools/harness/refresh_inventories.py 2>&1 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-StepSkip "tools/harness/refresh_inventories.py not found"
}

# 게이트 범위: 타깃 배열을 없애고 전체 스위트를 돌린다.
#
# 손으로 고른 목록은 반드시 낡는다 — 이 저장소가 이미 세 번 당했다(CI-VISUAL-01 등재 목록이
# 낡아 red 가 2주 반 살았고, as_timeline 호출부 명단이 4커밋 연속 red 를 냈고,
# CI-PROMOTE-01 base 필터 구멍으로 운영 사고 3건이 났다).
#
# 2026-09-22 계측(12코어): 33타깃 직렬 130초로 379개를 보던 게이트가, `-n auto --dist loadfile`
# 로는 104초에 10,204개를 본다. 같은 시간에 27배를 보는 셈이다. 그리고 그 시점의 CI red 20건은
# **전부** 타깃 배열 밖 파일이었다 — 목록이 좁아서 못 잡은 것이지, 게이트가 느려서가 아니었다.
#
# 분할이 loadfile 인 이유는 CI-XDIST-01 과 같다: 같은 파일의 테스트를 한 워커에 머물게 해
# 모듈 스코프 fixture 가 워커 경계에서 갈리지 않게 한다.
Invoke-SmokeStep -Name "Pytest 전체 스위트 (visual·harness 제외, -n auto)" -Action {
    Invoke-PythonCommand "-m pytest -q --ignore=tests/visual --ignore=tests/harness -p no:playwright -n auto --dist loadfile"
}

# tests/visual 은 목록 없이 통째로 돌린다. 브라우저 픽스처(page/browser/context)를 쓰는
# 테스트는 tests/visual/conftest.py 의 pytest_collection_modifyitems 가 skip 으로 떨어뜨린다
# — 예전처럼 "브라우저 없이 도는 파일" 목록을 손으로 유지하지 않는다.
Invoke-SmokeStep -Name "Pytest UI 구조 (tests/visual, 브라우저 테스트는 skip)" -Action {
    Invoke-PythonCommand "-m pytest -q tests/visual -p no:playwright -n auto --dist loadfile"
}

# tests/harness 는 Harness CI 잡이 전담하고 로컬에서 118초로 가장 무겁다(red 8/147 로 드물다).
# 기본 게이트에서 빼고 -Full 에만 넣는다.
if ($Full) {
    Invoke-SmokeStep -Name "Pytest 하네스 (tests/harness) — SLOW" -Action {
        Invoke-PythonCommand "-m pytest -q tests/harness -p no:playwright -n auto --dist loadfile"
    }
}

if ($Visual) {
    # Local-only Playwright visual regression. CI ignores tests/visual and uses
    # linux baselines, so this never gates CI; it catches local win32 drift.
    & python -c "import playwright" 2>$null
    $playwrightOk = ($LASTEXITCODE -eq 0)

    if (-not $playwrightOk) {
        Write-StepSkip "Visual regression — playwright not installed (optional; structural tests already ran)"
    } else {
        if (-not (Test-Path "C:\tmp")) {
            New-Item -ItemType Directory -Path "C:\tmp" -Force | Out-Null
        }
        Invoke-SmokeStep -Name "Visual regression (tests/visual, win32 baselines, local only)" -Action {
            # File-backed SQLite so the Playwright live-server fixture shares state.
            $env:TEMP = "C:\tmp"
            $env:TMP = "C:\tmp"
            $env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
            # Drop committed/stale DB before pytest (OneDrive locks; conftest also resets).
            $visualDb = Join-Path $root "tests\visual\visual_local.sqlite"
            Remove-Item -Force $visualDb -ErrorAction SilentlyContinue
            Get-ChildItem -Path (Join-Path $root "tests\visual") -Filter "visual_local.sqlite*" -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
            Invoke-PythonCommand "-m pytest tests/visual -q"
        }
    }
}

# Staging perf gate — 배포 후 검증 도구라 pre-push 기본에는 안 낀다(-PerfGate 로만 실행).
# 사용 시점: deploy 푸쉬·배포 완료 후 검증 / production 승격 직전 필수.
# env 크리덴셜(FOMS_STAGING_USERNAME/PASSWORD) 없으면 게이트가 exit 2 → SKIP 표기(실패 아님).
if ($PerfGate) {
    Write-StepHeader "Staging perf gate (deploy 후 검증 / 승격 전 필수)"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = "tools/perf/staging_perf_gate.py"
    $psi.WorkingDirectory = $root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    # stderr 를 먼저 비동기 수집 — stdout ReadToEnd 중 stderr 버퍼 포화 데드락(고전 .NET 함정) 방지.
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $stderrTask.Result
    $proc.WaitForExit()
    if ($stdout) { Write-Host $stdout }
    if ($stderr) { Write-Host $stderr -ForegroundColor DarkGray }
    if ($proc.ExitCode -eq 2) {
        Write-StepSkip "Staging perf gate — 크리덴셜 부재/로그인 실패로 스킵(실패 아님)"
    } elseif ($proc.ExitCode -ne 0) {
        Write-StepFail "Staging perf gate — 예산 초과(exit $($proc.ExitCode)) → 승격 차단"
        $script:FailedSteps.Add("Staging perf gate")
    } else {
        Write-StepOk "Staging perf gate"
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
