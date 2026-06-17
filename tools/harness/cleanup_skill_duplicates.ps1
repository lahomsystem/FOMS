[CmdletBinding()]
param(
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Remove-TreeIfExists {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Host "[SKIP] $Path"
        return
    }

    if ($WhatIf) {
        Write-Host "[DRY] Remove $Path"
        return
    }

    Remove-Item -LiteralPath $Path -Recurse -Force
    Write-Host "[OK] Removed $Path"
}

function Remove-FileIfExists {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Host "[SKIP] $Path"
        return
    }

    if ($WhatIf) {
        Write-Host "[DRY] Remove $Path"
        return
    }

    Remove-Item -LiteralPath $Path -Force
    Write-Host "[OK] Removed $Path"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$vendorRoot = Join-Path $repoRoot ".agents\skills\gstack"

Write-Host "== FOMS skill duplicate cleanup =="
Write-Host "WhatIf: $WhatIf"

# 1) Global gstack setup artifacts scanned recursively by Claude
Remove-TreeIfExists -Path (Join-Path $env:USERPROFILE ".claude\skills\gstack\.agents")
Remove-TreeIfExists -Path (Join-Path $env:USERPROFILE ".claude\skills\gstack\.cursor")

# 2) Redundant home-level caveman copy (skills CLI target)
Remove-TreeIfExists -Path (Join-Path $env:USERPROFILE ".agents\skills\caveman")

# 3) Repo-local caveman copies duplicate global Codex/Cursor skills in FOMS workspace
$cavemanRoots = @(
    (Join-Path $repoRoot ".agents\skills\caveman"),
    (Join-Path $repoRoot ".agents\skills\cavecrew")
) + @(Get-ChildItem -Path (Join-Path $repoRoot ".agents\skills") -Directory -Filter "caveman-*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })

foreach ($path in $cavemanRoots) {
    Remove-TreeIfExists -Path $path
}

# 4) Cursor: flat gstack-* copies duplicate Claude/Codex paths in unified Cursor UI
$cursorSkillsRoot = Join-Path $env:USERPROFILE ".cursor\skills"
Get-ChildItem -Path $cursorSkillsRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "gstack*" -or $_.Name -eq "caveman" } |
    ForEach-Object { Remove-TreeIfExists -Path $_.FullName }

# 5) Claude: source tree SKILL.md under gstack/ duplicates top-level gstack-* copies
$globalGstackRoot = Join-Path $env:USERPROFILE ".claude\skills\gstack"
$globalSourceSkillMd = Get-ChildItem -Path $globalGstackRoot -Recurse -Filter "SKILL.md" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -ne $globalGstackRoot }

foreach ($file in $globalSourceSkillMd) {
    Remove-FileIfExists -Path $file.FullName
}

# 6) Claude duplicate root alias (_gstack-command also registers as name: gstack)
Remove-TreeIfExists -Path (Join-Path $env:USERPROFILE ".claude\skills\_gstack-command")

# 7) Codex gstack-* + caveman duplicate Claude tree in Cursor unified skill UI
$codexSkillsRoot = Join-Path $env:USERPROFILE ".codex\skills"
Get-ChildItem -Path $codexSkillsRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "gstack*" } |
    ForEach-Object { Remove-TreeIfExists -Path $_.FullName }
Remove-TreeIfExists -Path (Join-Path $codexSkillsRoot "caveman")

# 8) FOMS vendor workflow SKILL.md files duplicate global gstack-* in Codex/Cursor
$vendorSkillMd = Get-ChildItem -Path $vendorRoot -Recurse -Filter "SKILL.md" -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch "\\upstream\\" -and
        $_.DirectoryName -ne $vendorRoot
    }

foreach ($file in $vendorSkillMd) {
    Remove-FileIfExists -Path $file.FullName
}

Write-Host ""
Write-Host "Re-run audit:"
Write-Host "  python tools/harness/audit_skills.py"
