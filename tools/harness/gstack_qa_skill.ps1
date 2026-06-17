Set-StrictMode -Version Latest

function Get-GstackQaSkillCandidates {
    return @(
        ".agents/skills/gstack/qa/SKILL.md",
        ".agents/skills/gstack/qa/SKILL.md.tmpl",
        ".agents/skills/gstack-qa/SKILL.md",
        ".agents/skills/gstack-qa/SKILL.md.tmpl",
        ".agents/skills/qa/SKILL.md",
        ".agents/skills/qa/SKILL.md.tmpl",
        ".agents/skills/gstack/.agents/skills/gstack-qa/SKILL.md",
        ".agents/skills/gstack/.agents/skills/gstack-qa/SKILL.md.tmpl",
        ".agents/skills/gstack/.agents/skills/qa/SKILL.md",
        ".agents/skills/gstack/.agents/skills/qa/SKILL.md.tmpl"
    )
}

function Join-RepoChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $normalized = $RelativePath -replace '\\', '/'
    $parts = @($normalized -split '/' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($parts.Count -eq 0) {
        return $Root
    }

    $combined = $Root
    foreach ($part in $parts) {
        $combined = [System.IO.Path]::Combine($combined, $part)
    }
    return $combined
}

function Test-RepoRelativePathExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        return $false
    }

    $candidatePath = Join-RepoChildPath -Root $Root -RelativePath $RelativePath
    return Test-Path -LiteralPath $candidatePath
}

function Test-GstackQaSkillReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    foreach ($candidate in (Get-GstackQaSkillCandidates)) {
        if (Test-RepoRelativePathExists -Root $RepoRoot -RelativePath $candidate) {
            return $true
        }
    }
    return $false
}

function Get-GstackQaSkillResolvedCandidates {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $resolved = @()
    foreach ($candidate in (Get-GstackQaSkillCandidates)) {
        if (Test-RepoRelativePathExists -Root $RepoRoot -RelativePath $candidate) {
            $resolved += $candidate
        }
    }
    return @($resolved)
}

function Test-GstackVendorQaSourceReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VendorRoot
    )

    return (Test-RepoRelativePathExists -Root $VendorRoot -RelativePath "qa/SKILL.md") -or
        (Test-RepoRelativePathExists -Root $VendorRoot -RelativePath "qa/SKILL.md.tmpl")
}
