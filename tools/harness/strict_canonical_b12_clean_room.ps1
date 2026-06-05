#requires -Version 5.1
<#
.SYNOPSIS
  Replays SFC-B12 / plan §6.19 clean-room verification on a given git ref (default HEAD).

.DESCRIPTION
  - git worktree add to an isolated path
  - Compare-Object root allowlist vs Get-ChildItem (must be zero diff)
  - SLG subtree closed-sets + forbidden paths (incl. templates/partials/http_errors absent)
  - templates/partials/shared/*.html exact allowlist (PAC post-audit §3.3)
  - python -c "import app; print('APP_OK')"
  - python tools/harness/verify_result.py --json
  - Optional: pytest (full suite). Final PAC-B5 closeout: use -RunFullPytest so clean-room replays ``pytest tests -q``.

  Run from repo root after committing B12 changes so SG6 is proven on a snapshot, not only a dirty tree.

.PARAMETER Ref
  Commit-ish to verify (branch name, tag, or SHA). Default: HEAD

.PARAMETER WorktreePath
  Absolute or repo-relative path for the temporary worktree. Default: .tmp_strict_tree_verify under repo root.

.PARAMETER RunFullPytest
  If set, runs: python -m pytest tests -q

.PARAMETER KeepWorktree
  If set, does not remove the worktree on exit (for debugging).

.EXAMPLE
  cd C:\path\to\FOMS
  powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD
#>
[CmdletBinding()]
param(
    [string]$Ref = "HEAD",
    [string]$WorktreePath = "",
    [switch]$RunFullPytest,
    [switch]$KeepWorktree
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $top = git rev-parse --show-toplevel 2>$null
    if (-not $top) {
        throw "Not inside a git repository (git rev-parse --show-toplevel failed)."
    }
    return (Resolve-Path $top).Path
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($WorktreePath)) {
    $WorktreePath = Join-Path $repoRoot ".tmp_strict_tree_verify"
}
elseif (-not [System.IO.Path]::IsPathRooted($WorktreePath)) {
    $WorktreePath = Join-Path $repoRoot $WorktreePath
}
$WorktreePath = [System.IO.Path]::GetFullPath($WorktreePath)

Write-Host "[strict_canonical_b12] repoRoot=$repoRoot"
Write-Host "[strict_canonical_b12] Ref=$Ref worktree=$WorktreePath"

# Best-effort remove stale worktree (ignore stderr: path may not be a worktree)
cmd /c "git worktree remove --force `"$WorktreePath`" 2>nul"
cmd /c "git worktree prune 2>nul"
if (Test-Path -LiteralPath $WorktreePath) {
    Remove-Item -LiteralPath $WorktreePath -Recurse -Force -ErrorAction Stop
}

$pushed = $false
try {
    git worktree add $WorktreePath $Ref
    if ($LASTEXITCODE -ne 0) {
        throw "git worktree add failed (exit $LASTEXITCODE)."
    }

    Push-Location $WorktreePath
    $pushed = $true

    # Literal replay of docs/plans/...-100-percent-execution-plan.md §6.19 (PowerShell clean-room recipe).
    # Root allowlist must stay in lockstep with docs/specs/2026-04-07-repo-structure-governance_SPEC.md §2.6.1
    # and docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md §4.1.
    $actualRoot = Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' } | Sort-Object
    $allowedRoot = @(
        '.agents', '.claude', '.cursor', '.github', '.vscode',
        '.dockerignore', '.gcloudignore', '.gitattributes', '.gitignore', '.python-version',
        'Add In Program', 'AGENTS.md', 'alembic.ini', 'app.py', 'CLAUDE.md', 'data', 'db.py',
        'Dockerfile', 'docs', 'foms', 'migrations', 'models.py', 'Procfile', 'README.md',
        'railway.toml', 'railway-worker.toml', 'railway-cron.toml', 'requirements.txt', 'run.py', 'SCheduler',
        'scripts', 'start.sh', 'static', 'templates', 'tests', 'tools', 'wdcalculator_db.py', 'wdcalculator_models.py'
    ) | Sort-Object

    $rootDiff = Compare-Object $allowedRoot $actualRoot
    if ($rootDiff) {
        $rootDiff | Format-Table -AutoSize
        throw 'STRICT_ROOT_DIFF_DETECTED'
    }
    Write-Host "[strict_canonical_b12] Compare-Object: OK (zero diff)"

    # SLG literal-gap: subtree closed-set compare (docs/plans/...-literal-gap-remediation-plan.md §4, §6.2)
    function Get-SortedChildDirNames {
        param([string]$Path)
        if (-not (Test-Path -LiteralPath $Path)) {
            throw "Subtree path missing: $Path"
        }
        return (
            Get-ChildItem -LiteralPath $Path -Directory -ErrorAction Stop |
            Where-Object { $_.Name -ne '__pycache__' -and -not $_.Name.StartsWith('.') } |
            ForEach-Object { $_.Name } |
            Sort-Object
        )
    }
    function Assert-SubtreeClosedSet {
        param(
            [string]$Label,
            [string]$AbsolutePath,
            [string[]]$AllowedDirs
        )
        $actual = @(Get-SortedChildDirNames -Path $AbsolutePath)
        $allowed = @($AllowedDirs | Sort-Object)
        $d = Compare-Object $allowed $actual
        if ($d) {
            Write-Host "[strict_canonical_b12] SUBTREE_DIFF label=$Label path=$AbsolutePath"
            $d | Format-Table -AutoSize
            throw "STRICT_SUBTREE_DIFF_DETECTED:$Label"
        }
        Write-Host "[strict_canonical_b12] subtree OK: $Label"
    }

    $tpl = Join-Path $WorktreePath "templates"
    $web = Join-Path $WorktreePath "foms\web"
    $api = Join-Path $WorktreePath "foms\api"
    $svc = Join-Path $WorktreePath "foms\services"

    Assert-SubtreeClosedSet -Label "templates" -AbsolutePath $tpl -AllowedDirs @(
        'admin', 'auth', 'channel', 'construction', 'cs', 'drawing',
        'measurement', 'orders', 'partials', 'production', 'shipment', 'wdcalculator'
    )
    Assert-SubtreeClosedSet -Label "foms/web" -AbsolutePath $web -AllowedDirs @(
        'admin', 'auth', 'channel', 'construction', 'cs', 'drawing',
        'measurement', 'orders', 'production', 'shipment', 'wdcalculator'
    )
    Assert-SubtreeClosedSet -Label "foms/api" -AbsolutePath $api -AllowedDirs @(
        'admin', 'auth', 'channel', 'construction', 'cs', 'drawing', 'files',
        'measurement', 'notifications', 'orders', 'production', 'shipment', 'wdcalculator'
    )
    Assert-SubtreeClosedSet -Label "foms/services" -AbsolutePath $svc -AllowedDirs @(
        'admin', 'auth', 'channel', 'common', 'construction', 'cs', 'drawing', 'files',
        'jobs', 'measurement', 'notifications', 'orders', 'production', 'shipment', 'wdcalculator'
    )

    $forbiddenPaths = @(
        (Join-Path $tpl "shared\layout.html"),
        (Join-Path $tpl "errors"),
        (Join-Path $tpl "partials\http_errors"),
        (Join-Path $svc "erp_policy_internal"),
        (Join-Path $WorktreePath "foms\services\orders\erp_policy_internal")
    )
    foreach ($fp in $forbiddenPaths) {
        if (Test-Path -LiteralPath $fp) {
            throw "STRICT_SLG_FORBIDDEN_PATH_PRESENT: $fp"
        }
    }
    Write-Host "[strict_canonical_b12] SLG forbidden-path probe: OK"

    # PAC §3.3: templates/partials/shared/*.html must equal exact allowlist (no extra erp_*.html).
    $sharedPartials = Join-Path $tpl "partials\shared"
    if (-not (Test-Path -LiteralPath $sharedPartials)) {
        throw "STRICT_PAC_SHARED_PARTIALS_MISSING: $sharedPartials"
    }
    $allowedSharedHtml = @(
        'layout_head.html', 'layout_nav.html', 'layout_flash.html', 'layout_scripts.html',
        'erp_mobile_shell.html', 'erp_mobile_shell_header.html', 'erp_mobile_bottom_nav.html',
        'erp_mobile_menu_drawer.html', 'erp_mobile_queue_card.html', 'erp_sub_nav.html'
    ) | Sort-Object
    $actualSharedHtml = @(
        Get-ChildItem -LiteralPath $sharedPartials -File -Filter *.html -ErrorAction Stop |
        ForEach-Object { $_.Name } | Sort-Object
    )
    $sharedDiff = Compare-Object $allowedSharedHtml $actualSharedHtml
    if ($sharedDiff) {
        Write-Host "[strict_canonical_b12] PAC shared partials HTML allowlist mismatch path=$sharedPartials"
        $sharedDiff | Format-Table -AutoSize
        throw 'STRICT_PAC_PARTIALS_SHARED_HTML_ALLOWLIST_DIFF'
    }
    Write-Host "[strict_canonical_b12] PAC partials/shared *.html allowlist: OK"

    $py = "python"
    if (Test-Path (Join-Path $WorktreePath ".venv\Scripts\python.exe")) {
        $py = Join-Path $WorktreePath ".venv\Scripts\python.exe"
    }

    & $py -c "import app; print('APP_OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "APP import check failed (exit $LASTEXITCODE)."
    }

    & $py (Join-Path $WorktreePath "tools\harness\verify_result.py") --json
    if ($LASTEXITCODE -ne 0) {
        throw "verify_result.py failed (exit $LASTEXITCODE)."
    }

    if ($RunFullPytest) {
        & $py -m pytest (Join-Path $WorktreePath "tests") -q
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed (exit $LASTEXITCODE)."
        }
    }

    Write-Host "[strict_canonical_b12] CLEAN_ROOM_OK ref=$Ref"
}
finally {
    if ($pushed) {
        Pop-Location -ErrorAction SilentlyContinue
    }
    Set-Location $repoRoot
    if (-not $KeepWorktree) {
        cmd /c "git worktree remove --force `"$WorktreePath`" 2>nul"
        cmd /c "git worktree prune 2>nul"
        if (Test-Path -LiteralPath $WorktreePath) {
            Write-Warning "Worktree path still exists: $WorktreePath (remove manually if needed)."
        }
    }
    else {
        Write-Host "[strict_canonical_b12] Kept worktree at: $WorktreePath"
    }
}
