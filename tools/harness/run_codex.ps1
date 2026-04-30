[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("review", "implement", "qa")]
    [string]$Profile,

    [string]$BundlePath,
    [ValidateSet("auto", "daily", "harness")]
    [string]$ContextMode = "auto",
    [string]$Target,
    [string]$Plan,
    [string]$Url,
    [string]$Scenario,
    [string]$AdditionalPrompt,
    [switch]$NonInteractive,
    [switch]$AllowRiskyLevelOverride,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$script:LevelRanks = @{
    low = 1
    medium = 2
    high = 3
    top = 4
}

function New-UnicodeString {
    param([int[]]$CodePoints)

    return (-join ($CodePoints | ForEach-Object { [char]$_ }))
}

$script:KoreanTokens = @{
    low = New-UnicodeString @(0xD558)
    medium = New-UnicodeString @(0xC911)
    high = New-UnicodeString @(0xC0C1)
    top = New-UnicodeString @(0xCD5C, 0xC0C1)
    level = New-UnicodeString @(0xB808, 0xBCA8)
    progress = New-UnicodeString @(0xC9C4, 0xD589)
}

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

    if (-not (Test-Path $candidate)) {
        Write-Error "Path not found: '$PathValue' (resolved: '$candidate')."
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
        return $ResolvedPath.Substring($RepoRoot.Length).TrimStart('/', '\').Replace('\', '/')
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

function Invoke-TaskClassifier {
    param(
        [string]$RepoRoot,
        [string]$ProfileName,
        [string]$PromptText,
        [string]$PathValue,
        [string]$ContextSignalPath,
        [string]$PlanPath,
        [string]$UrlValue,
        [string]$ScenarioText,
        [string]$AdditionalPromptText,
        [string]$RequestedContextMode,
        [string]$RequestedBundlePath
    )

    $pythonPath = Get-ToolPath -Name "python"
    if ($null -eq $pythonPath) {
        Write-Error "Python is not available on PATH; cannot run shared harness task classifier."
    }

    $classifierPath = Join-Path $PSScriptRoot "task_classifier.py"
    if (-not (Test-Path $classifierPath)) {
        Write-Error "Shared harness task classifier is missing: $classifierPath"
    }

    $classifierArgs = @(
        $classifierPath,
        "--repo-root", $RepoRoot,
        "--profile", $ProfileName,
        "--context-mode", $RequestedContextMode,
        "--json"
    )

    if (-not [string]::IsNullOrWhiteSpace($PromptText)) {
        $classifierArgs += @("--prompt", $PromptText)
    }
    if (-not [string]::IsNullOrWhiteSpace($PathValue)) {
        $classifierArgs += @("--path", $PathValue)
    }
    if (-not [string]::IsNullOrWhiteSpace($ContextSignalPath)) {
        $classifierArgs += @("--context-signal-path", $ContextSignalPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($PlanPath)) {
        $classifierArgs += @("--plan", $PlanPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($UrlValue)) {
        $classifierArgs += @("--url", $UrlValue)
    }
    if (-not [string]::IsNullOrWhiteSpace($ScenarioText)) {
        $classifierArgs += @("--scenario", $ScenarioText)
    }
    if (-not [string]::IsNullOrWhiteSpace($AdditionalPromptText)) {
        $classifierArgs += @("--additional-prompt", $AdditionalPromptText)
    }
    if (-not [string]::IsNullOrWhiteSpace($RequestedBundlePath)) {
        $classifierArgs += @("--bundle-path", $RequestedBundlePath)
    }

    $jsonText = & $pythonPath @classifierArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Shared harness task classifier failed with exit code $LASTEXITCODE."
    }
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        Write-Error "Shared harness task classifier returned empty output."
    }

    return ($jsonText | ConvertFrom-Json)
}

function Test-HarnessContextPath {
    param([string]$RepoRelativePath)

    if ([string]::IsNullOrWhiteSpace($RepoRelativePath)) {
        return $false
    }

    $normalized = $RepoRelativePath.Replace('\', '/')
    $exactMatches = @(
        "AGENTS.md",
        "CLAUDE.md",
        "docs/context/analysis/task_plan.md",
        "docs/context/analysis/findings.md",
        "docs/context/analysis/progress.md",
        "docs/ARCHIVE_INDEX.md",
        ".agents/workflows/verify-result.md",
        "docs/harness/policy/DECISIONS.md",
        "docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md",
        "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md"
    )
    if ($exactMatches -contains $normalized) {
        return $true
    }

    $prefixes = @(
        "tools/harness/",
        ".cursor/hooks/",
        ".cursor/rules/",
        ".cursor/agents/",
        "docs/specs/",
        "docs/harness/bundles/HARNESS_BUNDLE_"
    )
    foreach ($prefix in $prefixes) {
        if ($normalized.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-LevelRank {
    param([string]$Level)

    return $script:LevelRanks[$Level]
}

function Resolve-LevelName {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    $trimmed = $Value.Trim()
    $normalized = $trimmed.ToLowerInvariant()

    if ($normalized -eq "low") { return "low" }
    if ($normalized -eq "medium") { return "medium" }
    if ($normalized -eq "high") { return "high" }
    if ($normalized -eq "top") { return "top" }

    if ($trimmed -eq $script:KoreanTokens.low) { return "low" }
    if ($trimmed -eq $script:KoreanTokens.medium) { return "medium" }
    if ($trimmed -eq $script:KoreanTokens.high) { return "high" }
    if ($trimmed -eq $script:KoreanTokens.top) { return "top" }

    return $null
}

function Get-HigherLevel {
    param(
        [string]$CurrentLevel,
        [string]$CandidateLevel
    )

    if ((Get-LevelRank -Level $CandidateLevel) -gt (Get-LevelRank -Level $CurrentLevel)) {
        return $CandidateLevel
    }

    return $CurrentLevel
}

function New-ReasonList {
    return New-Object "System.Collections.Generic.List[string]"
}

function Add-Reason {
    param(
        [System.Collections.Generic.List[string]]$Reasons,
        [string]$Reason
    )

    if ([string]::IsNullOrWhiteSpace($Reason)) {
        return
    }

    if (-not $Reasons.Contains($Reason)) {
        $Reasons.Add($Reason)
    }
}

function Join-Reasons {
    param([System.Collections.Generic.List[string]]$Reasons)

    if ($Reasons.Count -eq 0) {
        return "narrow non-core scope"
    }

    return (($Reasons | Select-Object -First 2) -join " + ")
}

function Test-ContainsAnyKeyword {
    param(
        [string]$Text,
        [string[]]$Keywords
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $false
    }

    foreach ($keyword in $Keywords) {
        if ($Text.IndexOf($keyword, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }

    return $false
}

function Read-TextFileSafe {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }

    try {
        return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    }
    catch {
        return Get-Content -LiteralPath $Path -Raw
    }
}

function Get-PlanMetadata {
    param([string]$ResolvedPlanPath)

    $result = [pscustomobject]@{
        ModifiedFileCount = 0
        StepCount = 0
    }

    if ([string]::IsNullOrWhiteSpace($ResolvedPlanPath)) {
        return $result
    }

    $contents = Read-TextFileSafe -Path $ResolvedPlanPath
    if ([string]::IsNullOrWhiteSpace($contents)) {
        return $result
    }

    $lines = $contents -split "`r?`n"
    $inFileTable = $false
    $inSteps = $false

    foreach ($line in $lines) {
        if ($line -match "^###\s+2\.1") {
            $inFileTable = $true
            $inSteps = $false
            continue
        }

        if ($line -match "^##\s+3\.") {
            $inFileTable = $false
            $inSteps = $true
            continue
        }

        if ($line -match "^##\s+" -and -not ($line -match "^##\s+3\.")) {
            $inSteps = $false
        }

        if ($line -match "^###\s+" -and -not ($line -match "^###\s+2\.1")) {
            $inFileTable = $false
        }

        if ($inFileTable -and $line -match "^\|\s*`.+?`\s*\|") {
            $result.ModifiedFileCount += 1
        }

        if ($inSteps -and $line -match "^- \[[ xX]\]\s+Step") {
            $result.StepCount += 1
        }
    }

    return $result
}

function Get-RequestedLevelOverride {
    param([string]$Text)

    $empty = [pscustomobject]@{
        Level = $null
        Source = $null
        MatchedText = $null
    }

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $empty
    }

    $levelOptions = @(
        $script:KoreanTokens.top,
        $script:KoreanTokens.high,
        $script:KoreanTokens.medium,
        $script:KoreanTokens.low,
        "top",
        "high",
        "medium",
        "low"
    )
    $joinedLevelPattern = ($levelOptions | ForEach-Object { [System.Text.RegularExpressions.Regex]::Escape($_) }) -join "|"
    $levelKeyPattern = ("level", [System.Text.RegularExpressions.Regex]::Escape($script:KoreanTokens.level)) -join "|"

    $patterns = @(
        @{
            Regex = "(?:\[(?:$levelKeyPattern)\s*[:=]\s*($joinedLevelPattern)\])"
            Source = "fixed tag"
        },
        @{
            Regex = "(?:^|[\s,;])(?:$levelKeyPattern)\s*[:=]\s*($joinedLevelPattern)(?:$|[\s,;\]])"
            Source = "fixed tag"
        },
        @{
            Regex = "(?:this\s*task|this\s*run)?\s*(top|high|medium|low)\s*(?:level)?\s*(?:please\s+run|please\s+proceed|run|proceed)"
            Source = "natural language"
        }
    )

    foreach ($candidate in $patterns) {
        $match = [System.Text.RegularExpressions.Regex]::Match(
            $Text,
            $candidate.Regex,
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        if (-not $match.Success) {
            continue
        }

        $level = Resolve-LevelName -Value $match.Groups[1].Value
        if ($null -eq $level) {
            continue
        }

        return [pscustomobject]@{
            Level = $level
            Source = $candidate.Source
            MatchedText = $match.Value.Trim()
        }
    }

    foreach ($candidate in @(
            @{ Token = $script:KoreanTokens.top; Level = "top" },
            @{ Token = $script:KoreanTokens.high; Level = "high" },
            @{ Token = $script:KoreanTokens.medium; Level = "medium" },
            @{ Token = $script:KoreanTokens.low; Level = "low" }
        )) {
        if ($Text.Contains($candidate.Token) -and $Text.Contains($script:KoreanTokens.progress)) {
            return [pscustomobject]@{
                Level = $candidate.Level
                Source = "natural language"
                MatchedText = $candidate.Token
            }
        }
    }

    return $empty
}

function Get-PathRiskReasons {
    param([string]$RepoRelativePath)

    $reasons = New-ReasonList
    if ([string]::IsNullOrWhiteSpace($RepoRelativePath)) {
        return $reasons
    }

    $normalized = $RepoRelativePath.Replace('\', '/').ToLowerInvariant()

    if (Test-HarnessContextPath -RepoRelativePath $normalized) {
        Add-Reason -Reasons $reasons -Reason "harness core path"
    }

    $coreExactMatches = @(
        "app.py",
        "db.py",
        "models.py"
    )
    $corePrefixes = @(
        "apps/api/",
        "migrations/",
        "services/auth/",
        "auth/"
    )
    if ($coreExactMatches -contains $normalized) {
        Add-Reason -Reasons $reasons -Reason "db/api/auth core path"
    }
    foreach ($prefix in $corePrefixes) {
        if ($normalized.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Add-Reason -Reasons $reasons -Reason "db/api/auth core path"
            break
        }
    }

    $deployExactMatches = @(
        "dockerfile",
        "procfile",
        "railway.toml",
        "railway.json"
    )
    $deployPrefixes = @(
        ".github/workflows/",
        "docker/",
        "deploy/"
    )
    if ($deployExactMatches -contains $normalized) {
        Add-Reason -Reasons $reasons -Reason "deployment path"
    }
    foreach ($prefix in $deployPrefixes) {
        if ($normalized.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Add-Reason -Reasons $reasons -Reason "deployment path"
            break
        }
    }

    return $reasons
}

function Get-LevelGuidance {
    param([string]$Level)

    switch ($Level) {
        "low" {
            return [pscustomobject]@{
                Verification = "light review"
                PromptLines = @(
                    "Task level: low. Keep scope tight and avoid unnecessary broad context.",
                    "Use lightweight verification appropriate for a small, non-core task."
                )
            }
        }
        "medium" {
            return [pscustomobject]@{
                Verification = "related checks"
                PromptLines = @(
                    "Task level: medium. Stay on the daily bundle unless an explicit context override was requested.",
                    "Do the relevant targeted checks, tests, or browser verification before claiming success."
                )
            }
        }
        "high" {
            return [pscustomobject]@{
                Verification = "strong verification"
                PromptLines = @(
                    "Task level: high. Use harness-level rigor with stronger surrounding-code review.",
                    "Include stronger verification and consult relevant project docs or decisions when needed."
                )
            }
        }
        default {
            return [pscustomobject]@{
                Verification = "full verification"
                PromptLines = @(
                    "Task level: top. Apply full harness rigor with broad verification and explicit residual-risk reporting.",
                    "Consider research, browser QA, and parallel review or agent orchestration when the environment supports it."
                )
            }
        }
    }
}

function Get-AutoTaskLevel {
    param(
        [string]$ProfileName,
        [string]$ContextSignalPath,
        [string]$PlanResolvedPath,
        [string]$ScenarioText,
        [string]$AdditionalPromptText
    )

    $level = "low"
    $reasons = New-ReasonList
    $combinedText = @($ContextSignalPath, $ScenarioText, $AdditionalPromptText) -join " "
    $planMetadata = Get-PlanMetadata -ResolvedPlanPath $PlanResolvedPath

    $pathReasons = Get-PathRiskReasons -RepoRelativePath $ContextSignalPath
    foreach ($reason in $pathReasons) {
        Add-Reason -Reasons $reasons -Reason $reason
        if ($reason -in @("harness core path", "db/api/auth core path", "deployment path")) {
            $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "high"
        }
    }

    if (Test-ContainsAnyKeyword -Text $combinedText -Keywords @("auth", "session", "token")) {
        Add-Reason -Reasons $reasons -Reason "auth keywords"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "high"
    }

    if ($ProfileName -eq "qa") {
        Add-Reason -Reasons $reasons -Reason "qa verification flow"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "medium"
    }

    if (Test-ContainsAnyKeyword -Text $combinedText -Keywords @("qa", "browser", "e2e", "screenshot", "smoke", "audit", "test")) {
        Add-Reason -Reasons $reasons -Reason "verification-heavy flow"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "medium"
    }

    $wideScope = $false
    if ($planMetadata.ModifiedFileCount -ge 4 -or $planMetadata.StepCount -ge 4) {
        Add-Reason -Reasons $reasons -Reason "multi-file plan"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "medium"
        $wideScope = $true
    }

    if (
        $planMetadata.ModifiedFileCount -ge 7 -or
        $planMetadata.StepCount -ge 6 -or
        (Test-ContainsAnyKeyword -Text $combinedText -Keywords @("refactor", "architecture", "migration", "multi-file", "broad"))) {
        Add-Reason -Reasons $reasons -Reason "wide structural scope"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "high"
        $wideScope = $true
    }

    if (Test-ContainsAnyKeyword -Text $combinedText -Keywords @("parallel", "research", "full verification", "benchmark", "canary", "release", "deep audit")) {
        Add-Reason -Reasons $reasons -Reason "full-rigor resource signals"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "top"
    }

    if ($wideScope -and (Get-LevelRank -Level $level) -ge (Get-LevelRank -Level "high") -and $ProfileName -eq "implement") {
        Add-Reason -Reasons $reasons -Reason "broad implementation plan"
        $level = Get-HigherLevel -CurrentLevel $level -CandidateLevel "top"
    }

    if ($reasons.Count -eq 0) {
        Add-Reason -Reasons $reasons -Reason "narrow non-core scope"
    }

    return [pscustomobject]@{
        Level = $level
        Reason = Join-Reasons -Reasons $reasons
        PlanMetadata = $planMetadata
    }
}

function Resolve-CodexBundlePath {
    param(
        [string]$RequestedBundlePath,
        [string]$RequestedContextMode,
        [string]$ResolvedLevel
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedBundlePath)) {
        return $RequestedBundlePath
    }

    if ($RequestedContextMode -eq "harness") {
        return "docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md"
    }

    if ($RequestedContextMode -eq "daily") {
        return "docs/harness/bundles/HARNESS_BUNDLE_CODEX.md"
    }

    if ((Get-LevelRank -Level $ResolvedLevel) -ge (Get-LevelRank -Level "high")) {
        return "docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md"
    }

    return "docs/harness/bundles/HARNESS_BUNDLE_CODEX.md"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$codexPath = Get-ToolPath -Name "codex"
$qaSkillCandidates = @(
    ".agents/skills/gstack/qa/SKILL.md",
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

$basePromptLines = @(
    "You are running inside FOMS through the Codex CLI wrapper.",
    "Work from the repository root and keep Windows PowerShell 5.x compatibility for shared commands and documentation.",
    "If you need PowerShell commands, prefer `powershell.exe -NoProfile -Command ...` over profile-loading shells."
)
$taskPromptLines = @()

$contextSignalPath = $null
$planResolved = $null
$planPromptPath = $null
$classifierPathValue = $null

switch ($Profile) {
    "review" {
        if ([string]::IsNullOrWhiteSpace($Target)) {
            Write-Error "Target is required when Profile=review."
        }
        $targetResolved = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $Target
        $targetPromptPath = Get-RepoRelativePath -RepoRoot $repoRoot -ResolvedPath $targetResolved
        $contextSignalPath = $targetPromptPath
        $classifierPathValue = $targetPromptPath
        $taskPromptLines += "Then review `"$targetPromptPath`" and any directly relevant surrounding code."
        $taskPromptLines += "Return findings first, ordered by severity. Focus on bugs, regressions, security risks, and missing verification."
        $taskPromptLines += "Do not modify files."
    }
    "implement" {
        if ([string]::IsNullOrWhiteSpace($Plan)) {
            Write-Error "Plan is required when Profile=implement."
        }
        $planResolved = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $Plan
        $planPromptPath = Get-RepoRelativePath -RepoRoot $repoRoot -ResolvedPath $planResolved
        $contextSignalPath = $planPromptPath
        $classifierPathValue = $planPromptPath
        $taskPromptLines += "Then read plan `"$planPromptPath`"."
        $taskPromptLines += "Continue only the next approved implementation step from that plan."
        $taskPromptLines += "Keep unrelated dirty files untouched, follow Root Cause Fix, and verify before claiming success."
    }
    "qa" {
        if (-not (Test-HttpUrl -Value $Url)) {
            Write-Error "Url must be an absolute http/https URL when Profile=qa."
        }
        if ([string]::IsNullOrWhiteSpace($Scenario)) {
            Write-Error "Scenario is required when Profile=qa."
        }
        $taskPromptLines += "Then run repeatable QA for URL `"$Url`" with scenario `"$Scenario`"."
        $taskPromptLines += "Use the repo-local gstack QA skill if it is available."
        if ($qaSkillResolved.Count -gt 0) {
            $skillList = ($qaSkillResolved -join ", ")
            $taskPromptLines += "Expected repo-local QA skill path(s): $skillList"
        } else {
            $candidateList = ($qaSkillCandidates -join ", ")
            $taskPromptLines += "If none of these QA skill paths exist: $candidateList, stop and report the missing prerequisite instead of improvising with another browser tool."
        }
        $taskPromptLines += "Report findings first. If you make no changes, say so explicitly."
    }
}

$classification = Invoke-TaskClassifier `
    -RepoRoot $repoRoot `
    -ProfileName $Profile `
    -PromptText "" `
    -PathValue $classifierPathValue `
    -ContextSignalPath $contextSignalPath `
    -PlanPath $planPromptPath `
    -UrlValue $Url `
    -ScenarioText $Scenario `
    -AdditionalPromptText $AdditionalPrompt `
    -RequestedContextMode $ContextMode `
    -RequestedBundlePath $BundlePath

$overrideInfo = [pscustomobject]@{
    Level = $classification.override_level
    Source = $classification.override_source
    MatchedText = $classification.override_matched_text
}
$autoLevelInfo = [pscustomobject]@{
    Level = $classification.auto_level
    Reason = $classification.auto_reason
    PlanMetadata = $classification.plan_metadata
}
$resolvedLevel = $classification.level
$resolvedReason = $classification.reason
$guidance = [pscustomobject]@{
    Verification = $classification.verification
    PromptLines = @($classification.prompt_lines)
}

$requiresRiskyOverrideAck = [bool]$classification.risky_override_ack_required

if ($requiresRiskyOverrideAck -and -not $DryRun) {
    $warningMessage = "High-risk task auto-classified as $($autoLevelInfo.Level) ($($autoLevelInfo.Reason)). Use -AllowRiskyLevelOverride or rerun interactively to confirm the downgrade to $($overrideInfo.Level)."
    if ($AllowRiskyLevelOverride) {
        Write-Warning $warningMessage
    } elseif ($NonInteractive -or -not [string]::IsNullOrWhiteSpace($env:CI)) {
        Write-Error $warningMessage
    } else {
        $response = Read-Host "$warningMessage Continue anyway? [y/N]"
        if ($response -notmatch "^(?i:y|yes)$") {
            Write-Error "Aborted risky level downgrade."
        }
    }
}

$resolvedBundlePath = $classification.codex_bundle_path
$bundleResolved = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $resolvedBundlePath
$bundlePromptPath = Get-RepoRelativePath -RepoRoot $repoRoot -ResolvedPath $bundleResolved
$resolvedContextMode = if ($bundlePromptPath -like "*_HARNESS.md") { "harness" } else { "daily" }
$promptLines = @(
    $basePromptLines[0],
    "Start by reading `"$bundlePromptPath`" and follow it as the portable harness baseline.",
    $basePromptLines[1],
    $basePromptLines[2],
    "Resolved task level: $resolvedLevel. Reason: $resolvedReason."
) + $guidance.PromptLines + $taskPromptLines

if (-not [string]::IsNullOrWhiteSpace($AdditionalPrompt)) {
    $promptLines += $AdditionalPrompt.Trim()
}

$promptText = $promptLines -join "`n`n"
$commandPreview = "codex exec -s workspace-write"

Write-Host "== FOMS Codex wrapper =="
Write-Host "Repo root : $repoRoot"
Write-Host "Profile   : $Profile"
Write-Host "Context   : $resolvedContextMode"
Write-Host "Bundle    : $bundlePromptPath"
Write-Host "Level     : $resolvedLevel ($resolvedReason)"
Write-Host "AutoLevel : $($autoLevelInfo.Level) ($($autoLevelInfo.Reason))"
if ($null -ne $overrideInfo.Level) {
    Write-Host "Override  : $($overrideInfo.Level) via $($overrideInfo.Source)"
}
Write-Host "Verify    : $($guidance.Verification)"
Write-Host "RiskAck   : $requiresRiskyOverrideAck"
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
    Write-Host "- level        : $resolvedLevel"
    Write-Host "- auto level   : $($autoLevelInfo.Level)"
    Write-Host "- reason       : $resolvedReason"
    Write-Host "- context      : $resolvedContextMode"
    Write-Host "- bundle ready : $([bool](Test-Path $bundleResolved))"
    Write-Host "- codex ready  : $([bool]($null -ne $codexPath))"
    Write-Host "- risky override ack required : $requiresRiskyOverrideAck"
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

$codexExitCode = 0
Push-Location $repoRoot
try {
    # Official Codex CLI docs support piping the prompt to stdin: `echo "..." | codex exec`.
    $promptText | & $codexPath exec -s workspace-write
    $codexExitCode = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }
}
finally {
    Pop-Location
}

exit $codexExitCode
