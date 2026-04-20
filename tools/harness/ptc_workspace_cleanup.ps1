#requires -Version 5.1
<#
.SYNOPSIS
  Removes forbidden workspace residue before PTC final audit (plan §4.4 / §5.6).

.DESCRIPTION
  Best-effort deletion of paths that must be absent for workspace hygiene green:
  - .gstack/
  - .pytest_cache/
  - .tmp_strict_tree_verify/
  - repo root __pycache__/
  - root-level *.db, *.dump

  Optional: -RecursePyCache removes every __pycache__ directory under the repo (excluding .git).

  Does not touch unrelated dirty changes; only listed patterns.

.EXAMPLE
  powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1
  powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$RecursePyCache,
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $top = git rev-parse --show-toplevel 2>$null
    if (-not $top) { throw "Not inside a git repository." }
    $RepoRoot = (Resolve-Path $top).Path
}
else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}

function Remove-IfExists {
    param([string]$LiteralPath)
    if (-not (Test-Path -LiteralPath $LiteralPath)) { return }
    if ($WhatIf) {
        Write-Host "[whatif] would remove: $LiteralPath"
        return
    }
    Remove-Item -LiteralPath $LiteralPath -Recurse -Force -ErrorAction Stop
    Write-Host "[removed] $LiteralPath"
}

Write-Host "[ptc_workspace_cleanup] repoRoot=$RepoRoot"

foreach ($rel in @(".gstack", ".pytest_cache", ".tmp_strict_tree_verify", "__pycache__")) {
    Remove-IfExists (Join-Path $RepoRoot $rel)
}

Get-ChildItem -LiteralPath $RepoRoot -File -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Extension -eq ".db" -or $_.Extension -eq ".dump") {
        if ($WhatIf) {
            Write-Host "[whatif] would remove file: $($_.Name)"
        }
        else {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
            Write-Host "[removed] $($_.Name)"
        }
    }
}

if ($RecursePyCache) {
    Get-ChildItem -LiteralPath $RepoRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notmatch '\\\.git\\' -and $_.Name -eq '__pycache__' -and
            $_.FullName -notmatch '\\node_modules\\' -and
            $_.FullName -notmatch '\\venv\\' -and
            $_.FullName -notmatch '\\.venv\\' -and
            $_.FullName -notmatch '\\\.claude\\'
        } |
        ForEach-Object {
            if ($WhatIf) {
                Write-Host "[whatif] would remove: $($_.FullName)"
            }
            else {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
                Write-Host "[removed] $($_.FullName.Substring($RepoRoot.Length).TrimStart('\'))"
            }
        }
}

Write-Host "[ptc_workspace_cleanup] done"
exit 0
