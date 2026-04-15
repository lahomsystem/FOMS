#requires -Version 5.1
<#
.SYNOPSIS
  Replays SFC-B12 / plan §6.19 clean-room verification on a given git ref (default HEAD).

.DESCRIPTION
  - git worktree add to an isolated path
  - Compare-Object root allowlist vs Get-ChildItem (must be zero diff)
  - python -c "import app; print('APP_OK')"
  - python tools/harness/verify_result.py --json
  - Optional: pytest (full suite)

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

    # Literal replay of docs/plans/...-100-percent-execution-plan.md §6.19 (PowerShell clean-room recipe)
    $actualRoot = Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' } | Sort-Object
    $allowedRoot = @(
        '.agents', '.claude', '.cursor', '.github', '.vscode',
        '.dockerignore', '.gcloudignore', '.gitattributes', '.gitignore', '.python-version',
        'Add In Program', 'AGENTS.md', 'alembic.ini', 'app.py', 'backups', 'CLAUDE.md', 'data', 'db.py',
        'Dockerfile', 'docs', 'foms', 'migrations', 'models.py', 'Procfile', 'README.md',
        'railway.toml', 'railway-worker.toml', 'requirements.txt', 'run.py', 'SCheduler',
        'scripts', 'start.sh', 'static', 'templates', 'tests', 'tools', 'wdcalculator_db.py', 'wdcalculator_models.py'
    ) | Sort-Object

    $rootDiff = Compare-Object $allowedRoot $actualRoot
    if ($rootDiff) {
        $rootDiff | Format-Table -AutoSize
        throw 'STRICT_ROOT_DIFF_DETECTED'
    }
    Write-Host "[strict_canonical_b12] Compare-Object: OK (zero diff)"

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
