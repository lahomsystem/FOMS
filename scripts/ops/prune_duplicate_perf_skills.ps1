# prune_duplicate_perf_skills.ps1 — global ~/.codex perf skill 복제본 제거 (SSOT는 repo .cursor/skills)
param(
    [switch]$WhatIf
)

$globalSkills = @(
    Join-Path $env:USERPROFILE ".codex\skills\perf-guard"
    Join-Path $env:USERPROFILE ".codex\skills\perf-audit"
)

foreach ($path in $globalSkills) {
    if (-not (Test-Path $path)) {
        Write-Host "[skip] not found: $path"
        continue
    }
    if ($WhatIf) {
        Write-Host "[whatif] would remove: $path"
        continue
    }
    Remove-Item -Recurse -Force $path
    Write-Host "[removed] $path"
}

Write-Host "SSOT: .cursor/skills/perf-guard · perf-audit (see docs/guides/PERF_SKILLS_ROUTING.md)"
