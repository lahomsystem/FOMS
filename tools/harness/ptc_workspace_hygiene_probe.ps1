#requires -Version 5.1
<#
.SYNOPSIS
  Probes repo working tree for forbidden workspace residue (PTC plan §4.4 / §3.5).

.DESCRIPTION
  To clear violations before audit, run tools/harness/ptc_workspace_cleanup.ps1 (see docs/harness/PTC_WORKSPACE_HYGIENE.md).

  Fails if any of the following exist under repo root (or optionally under -ScanCanonicalOnly):
  - .gstack/
  - .pytest_cache/
  - .tmp_strict_tree_verify/
  - repo root __pycache__/
  - root-level *.db, *.dump

  Recursive: optional scan for **/ __pycache__ when -RecursePyCache is set (expensive).

.PARAMETER RepoRoot
  Defaults to git toplevel.

.PARAMETER RecursePyCache
  If set, fails on any directory named __pycache__ under RepoRoot (excluding .git).

.EXAMPLE
  powershell -NoProfile -File tools\harness\ptc_workspace_hygiene_probe.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$RecursePyCache
)

# Win11 cp949 console: force UTF-8 output so Korean text is not mangled.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

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

$failures = New-Object System.Collections.Generic.List[string]

function Test-PathExists {
    param([string]$Rel)
    $p = Join-Path $RepoRoot $Rel
    if (Test-Path -LiteralPath $p) {
        [void]$script:failures.Add($Rel)
    }
}

Test-PathExists ".gstack"
Test-PathExists ".pytest_cache"
Test-PathExists ".tmp_strict_tree_verify"
Test-PathExists "__pycache__"

Get-ChildItem -LiteralPath $RepoRoot -File -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Extension -eq ".db" -or $_.Extension -eq ".dump") {
        [void]$failures.Add($_.Name)
    }
}

if ($RecursePyCache) {
    Get-ChildItem -LiteralPath $RepoRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notmatch '\\\.git\\' -and
            $_.Name -eq '__pycache__' -and
            $_.FullName -notmatch '\\node_modules\\' -and
            $_.FullName -notmatch '\\venv\\' -and
            $_.FullName -notmatch '\\.venv\\' -and
            $_.FullName -notmatch '\\\.claude\\'
        } |
        ForEach-Object {
            $rel = $_.FullName.Substring($RepoRoot.Length).TrimStart('\')
            [void]$failures.Add($rel)
        }
}

if ($failures.Count -gt 0) {
    Write-Host "[ptc_workspace_hygiene] FAIL — forbidden residue:"
    $failures | ForEach-Object { Write-Host "  $_" }
    exit 2
}

Write-Host "[ptc_workspace_hygiene] OK repoRoot=$RepoRoot"
exit 0
