[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Url,

    [Parameter(Mandatory = $true)]
    [string]$Scenario,

    [switch]$DryRun,
    [string]$VendorRoot = ".agents/skills/gstack",
    [string]$BundlePath,
    [string]$AdditionalPrompt,
    [switch]$NonInteractive,
    [switch]$AllowRiskyLevelOverride
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-HttpUrl {
    param([string]$Value)

    $uri = $null
    if (-not [System.Uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$uri)) {
        return $false
    }
    return $uri.Scheme -in @("http", "https")
}

function Get-ToolPath {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Get-CurrentPowerShellHostPath {
    $process = Get-Process -Id $PID -ErrorAction SilentlyContinue
    if ($null -eq $process -or [string]::IsNullOrWhiteSpace($process.Path)) {
        return $null
    }
    return $process.Path
}

function Resolve-GitBashPath {
    param([string]$GitPath)

    if (-not [string]::IsNullOrWhiteSpace($GitPath)) {
        $gitDir = Split-Path -Parent $GitPath
        $gitRoot = Split-Path -Parent $gitDir
        $candidates = @(
            (Join-Path $gitRoot "bin\bash.exe"),
            (Join-Path $gitRoot "usr\bin\bash.exe")
        )

        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) {
                return $candidate
            }
        }
    }

    return (Get-ToolPath -Name "bash")
}

function Test-WslReady {
    param([string]$WslPath)

    if ([string]::IsNullOrWhiteSpace($WslPath)) {
        return $false
    }

    $escapedWslPath = $WslPath.Replace('"', '""')
    $null = & cmd.exe /c """$escapedWslPath"" -l -q >nul 2>nul"
    return ($LASTEXITCODE -eq 0)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedVendorRoot = Join-Path $repoRoot $VendorRoot
$vendorManifest = Join-Path $resolvedVendorRoot "VENDOR.md"
$snapshotManifest = Join-Path $resolvedVendorRoot "upstream\SNAPSHOT.md"
$setupScript = Join-Path $PSScriptRoot "setup_gstack.ps1"
$codexWrapper = Join-Path $PSScriptRoot "run_codex.ps1"
$vendorQaSourcePath = Join-Path $resolvedVendorRoot "qa\SKILL.md"
$effectiveBundlePath = if ([string]::IsNullOrWhiteSpace($BundlePath)) {
    "docs/context/HARNESS_BUNDLE_CODEX.md"
} else {
    $BundlePath
}
$bundleCandidate = if ([System.IO.Path]::IsPathRooted($effectiveBundlePath)) {
    $effectiveBundlePath
} else {
    Join-Path $repoRoot $effectiveBundlePath
}
if (-not (Test-Path $bundleCandidate)) {
    Write-Error "Bundle file is missing at '$bundleCandidate'. Regenerate harness bundles before running QA."
}
$bundleResolved = (Resolve-Path $bundleCandidate).Path
$gitPath = Get-ToolPath -Name "git"
$qaSkillCandidates = @(
    ".agents/skills/gstack/qa/SKILL.md",
    ".agents/skills/gstack-qa/SKILL.md",
    ".agents/skills/qa/SKILL.md",
    ".agents/skills/gstack/.agents/skills/gstack-qa/SKILL.md",
    ".agents/skills/gstack/.agents/skills/qa/SKILL.md"
)
$qaSkillReady = $false
foreach ($candidate in $qaSkillCandidates) {
    if (Test-Path (Join-Path $repoRoot $candidate)) {
        $qaSkillReady = $true
        break
    }
}
$vendorQaSourceReady = Test-Path $vendorQaSourcePath

if (-not (Test-HttpUrl -Value $Url)) {
    Write-Error "Url must be an absolute http/https URL."
}

if ([string]::IsNullOrWhiteSpace($Scenario)) {
    Write-Error "Scenario must not be empty."
}

$nodePath = Get-ToolPath -Name "node"
$bunPath = Get-ToolPath -Name "bun"
$bashPath = Resolve-GitBashPath -GitPath $gitPath
$rawWslPath = Get-ToolPath -Name "wsl"
$wslReady = Test-WslReady -WslPath $rawWslPath
$wslPath = if ($wslReady) { $rawWslPath } else { $null }
$codexPath = Get-ToolPath -Name "codex"
$powerShellHostPath = Get-CurrentPowerShellHostPath
$shellBridgeReady = ($null -ne $bashPath) -or ($null -ne $wslPath)

$commandPreview = @(
    "powershell",
    "-NoProfile",
    "-File", $codexWrapper,
    "-Profile", "qa",
    "-Url", $Url,
    "-Scenario", $Scenario
)
if (-not [string]::IsNullOrWhiteSpace($BundlePath)) {
    $commandPreview += @("-BundlePath", $BundlePath)
}
if (-not [string]::IsNullOrWhiteSpace($AdditionalPrompt)) {
    $commandPreview += @("-AdditionalPrompt", $AdditionalPrompt)
}
if ($NonInteractive) {
    $commandPreview += "-NonInteractive"
}
if ($AllowRiskyLevelOverride) {
    $commandPreview += "-AllowRiskyLevelOverride"
}

Write-Host "== FOMS gstack QA preflight =="
Write-Host "Repo root : $repoRoot"
Write-Host "Vendor dir: $resolvedVendorRoot"
Write-Host "Scenario : $Scenario"
Write-Host "Url      : $Url"

if ($DryRun) {
    Write-Host ""
    Write-Host "DryRun summary:"
    Write-Host "- setup script : $setupScript"
    Write-Host "- codex wrapper: $codexWrapper"
    Write-Host "- vendor ready : $(Test-Path $vendorManifest)"
    Write-Host "- snapshot ready: $(Test-Path $snapshotManifest)"
    Write-Host "- bundle ready : $([bool](Test-Path $bundleResolved))"
    Write-Host "- node runtime : $([bool]($null -ne $nodePath))"
    Write-Host "- bun runtime  : $([bool]($null -ne $bunPath)) (setup/build time)"
    Write-Host "- shell bridge : $shellBridgeReady"
    Write-Host "- codex cli    : $([bool]($null -ne $codexPath))"
    Write-Host "- qa source    : $vendorQaSourceReady"
    Write-Host "- qa skill     : $qaSkillReady"
    Write-Host "- level policy : daily bundle by default; run_codex.ps1 may still promote risk/override-driven QA to harness context"
    Write-Host "- command      : $($commandPreview -join ' ')"
    Write-Host ""
    Write-Host "DryRun only. Real execution uses Codex CLI plus repo-local gstack QA skills."
    Write-Host "If bun, codex, or the generated QA skill are missing, execution will stop with a preflight error."
    exit 0
}

if (-not (Test-Path $vendorManifest)) {
    Write-Error "Vendor boundary missing. Run powershell -NoProfile -File ""tools/harness/setup_gstack.ps1"" -WhatIf and import the upstream snapshot before real QA execution."
}

if (-not (Test-Path $snapshotManifest)) {
    Write-Error "Pinned upstream snapshot missing. Import '$snapshotManifest' before real QA execution."
}

if (-not (Test-Path $codexWrapper)) {
    Write-Error "Codex wrapper is missing at '$codexWrapper'."
}

if ($null -eq $codexPath) {
    Write-Error "Codex CLI is not available on PATH. QA execution is driven through 'codex exec', not a standalone 'gstack qa' binary."
}

if ($null -eq $powerShellHostPath -or -not (Test-Path $powerShellHostPath)) {
    Write-Error "Current PowerShell host path is unavailable, so the QA wrapper cannot launch the nested Codex wrapper process safely."
}

if (-not $qaSkillReady) {
    $candidateList = ($qaSkillCandidates -join ", ")
    Write-Error "Repo-local gstack QA skill is missing. Expected one of: $candidateList"
}

$codexArgs = @(
    "-Profile", "qa",
    "-Url", $Url,
    "-Scenario", $Scenario
)
if (-not [string]::IsNullOrWhiteSpace($BundlePath)) {
    $codexArgs += @("-BundlePath", $BundlePath)
}
if (-not [string]::IsNullOrWhiteSpace($AdditionalPrompt)) {
    $codexArgs += @("-AdditionalPrompt", $AdditionalPrompt)
}
if ($NonInteractive) {
    $codexArgs += "-NonInteractive"
}
if ($AllowRiskyLevelOverride) {
    $codexArgs += "-AllowRiskyLevelOverride"
}

$nestedPowerShellArgs = @(
    "-NoProfile",
    "-File", $codexWrapper
) + $codexArgs

& $powerShellHostPath @nestedPowerShellArgs
$wrapperExitCode = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }
exit $wrapperExitCode
