[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("review", "implement", "qa")]
    [string]$Profile,

    [string]$BundlePath = "docs/context/HARNESS_BUNDLE_CODEX.md",
    [string]$Target,
    [string]$Plan,
    [string]$Url,
    [string]$Scenario,
    [string]$AdditionalPrompt,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ToolPath {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Resolve-RepoPath {
    param(
        [string]$RepoRoot,
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $null
    }

    $candidate = if ([System.IO.Path]::IsPathRooted($PathValue)) {
        $PathValue
    } else {
        Join-Path $RepoRoot $PathValue
    }

    return (Resolve-Path $candidate).Path
}

function Get-RepoRelativePath {
    param(
        [string]$RepoRoot,
        [string]$ResolvedPath
    )

    if ([string]::IsNullOrWhiteSpace($ResolvedPath)) {
        return $null
    }

    if ($ResolvedPath.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $ResolvedPath.Substring($RepoRoot.Length).TrimStart('\').Replace('\', '/')
    }

    return $ResolvedPath
}

function Test-HttpUrl {
    param([string]$Value)

    $uri = $null
    if (-not [System.Uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$uri)) {
        return $false
    }
    return $uri.Scheme -in @("http", "https")
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$bundleResolved = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $BundlePath
$bundlePromptPath = Get-RepoRelativePath -RepoRoot $repoRoot -ResolvedPath $bundleResolved
$codexPath = Get-ToolPath -Name "codex"
$qaSkillCandidates = @(
    ".agents/skills/gstack-qa/SKILL.md",
    ".agents/skills/qa/SKILL.md",
    ".agents/skills/gstack/.agents/skills/gstack-qa/SKILL.md",
    ".agents/skills/gstack/.agents/skills/qa/SKILL.md"
)
$qaSkillResolved = @()
foreach ($candidate in $qaSkillCandidates) {
    $candidateAbs = Join-Path $repoRoot $candidate
    if (Test-Path $candidateAbs) {
        $qaSkillResolved += $candidate
    }
}

$promptLines = @(
    "You are running inside FOMS through the Codex CLI wrapper.",
    "Start by reading `"$bundlePromptPath`" and follow it as the portable harness baseline.",
    "Work from the repository root and keep Windows PowerShell 5.x compatibility for shared commands and documentation."
)

switch ($Profile) {
    "review" {
        if ([string]::IsNullOrWhiteSpace($Target)) {
            Write-Error "Target is required when Profile=review."
        }
        $targetResolved = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $Target
        $targetPromptPath = Get-RepoRelativePath -RepoRoot $repoRoot -ResolvedPath $targetResolved
        $promptLines += "Then review `"$targetPromptPath`" and any directly relevant surrounding code."
        $promptLines += "Return findings first, ordered by severity. Focus on bugs, regressions, security risks, and missing verification."
        $promptLines += "Do not modify files."
    }
    "implement" {
        if ([string]::IsNullOrWhiteSpace($Plan)) {
            Write-Error "Plan is required when Profile=implement."
        }
        $planResolved = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $Plan
        $planPromptPath = Get-RepoRelativePath -RepoRoot $repoRoot -ResolvedPath $planResolved
        $promptLines += "Then read plan `"$planPromptPath`"."
        $promptLines += "Continue only the next approved implementation step from that plan."
        $promptLines += "Keep unrelated dirty files untouched, follow Root Cause Fix, and verify before claiming success."
    }
    "qa" {
        if (-not (Test-HttpUrl -Value $Url)) {
            Write-Error "Url must be an absolute http/https URL when Profile=qa."
        }
        if ([string]::IsNullOrWhiteSpace($Scenario)) {
            Write-Error "Scenario is required when Profile=qa."
        }
        $promptLines += "Then run repeatable QA for URL `"$Url`" with scenario `"$Scenario`"."
        $promptLines += "Use the repo-local gstack QA skill if it is available."
        if ($qaSkillResolved.Count -gt 0) {
            $skillList = ($qaSkillResolved -join ", ")
            $promptLines += "Expected repo-local QA skill path(s): $skillList"
        } else {
            $candidateList = ($qaSkillCandidates -join ", ")
            $promptLines += "If none of these QA skill paths exist: $candidateList, stop and report the missing prerequisite instead of improvising with another browser tool."
        }
        $promptLines += "Report findings first. If you make no changes, say so explicitly."
    }
}

if (-not [string]::IsNullOrWhiteSpace($AdditionalPrompt)) {
    $promptLines += $AdditionalPrompt.Trim()
}

$promptText = $promptLines -join "`n`n"
$commandPreview = "codex exec"

Write-Host "== FOMS Codex wrapper =="
Write-Host "Repo root : $repoRoot"
Write-Host "Profile   : $Profile"
Write-Host "Bundle    : $bundlePromptPath"
Write-Host "Codex CLI : $([bool]($null -ne $codexPath))"

if ($Profile -eq "review") {
    Write-Host "Target    : $Target"
} elseif ($Profile -eq "implement") {
    Write-Host "Plan      : $Plan"
} elseif ($Profile -eq "qa") {
    Write-Host "Url       : $Url"
    Write-Host "Scenario  : $Scenario"
    Write-Host "QA skill  : $([bool]($qaSkillResolved.Count -gt 0))"
}

if ($DryRun) {
    Write-Host ""
    Write-Host "DryRun summary:"
    Write-Host "- command      : $commandPreview"
    Write-Host "- bundle ready : $([bool](Test-Path $bundleResolved))"
    Write-Host "- codex ready  : $([bool]($null -ne $codexPath))"
    if ($Profile -eq "qa") {
        Write-Host "- qa skill ready: $([bool]($qaSkillResolved.Count -gt 0))"
    }
    Write-Host "- prompt preview:"
    Write-Host ""
    Write-Host $promptText
    exit 0
}

if ($null -eq $codexPath) {
    Write-Error "Codex CLI is not available on PATH. Install Codex CLI or use -DryRun to preview the wrapper."
}

if ($Profile -eq "qa" -and $qaSkillResolved.Count -eq 0) {
    $candidateList = ($qaSkillCandidates -join ", ")
    Write-Error "Repo-local gstack QA skill is missing. Expected one of: $candidateList"
}

Push-Location $repoRoot
try {
    # Official Codex CLI docs support piping the prompt to stdin: `echo "..." | codex exec`.
    $promptText | & $codexPath exec
}
finally {
    Pop-Location
}
