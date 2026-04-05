[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Url,

    [Parameter(Mandatory = $true)]
    [string]$Scenario,

    [switch]$DryRun,
    [string]$VendorRoot = ".agents/skills/gstack",
    [string]$BundlePath = "docs/context/HARNESS_BUNDLE_CODEX.md"
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

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedVendorRoot = Join-Path $repoRoot $VendorRoot
$vendorManifest = Join-Path $resolvedVendorRoot "VENDOR.md"
$snapshotManifest = Join-Path $resolvedVendorRoot "upstream\SNAPSHOT.md"
$setupScript = Join-Path $PSScriptRoot "setup_gstack.ps1"
$codexWrapper = Join-Path $PSScriptRoot "run_codex.ps1"
$bundleResolved = if ([System.IO.Path]::IsPathRooted($BundlePath)) {
    (Resolve-Path $BundlePath).Path
} else {
    (Resolve-Path (Join-Path $repoRoot $BundlePath)).Path
}
$qaSkillCandidates = @(
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

if (-not (Test-HttpUrl -Value $Url)) {
    Write-Error "Url must be an absolute http/https URL."
}

if ([string]::IsNullOrWhiteSpace($Scenario)) {
    Write-Error "Scenario must not be empty."
}

$nodePath = Get-ToolPath -Name "node"
$bunPath = Get-ToolPath -Name "bun"
$bashPath = Get-ToolPath -Name "bash"
$wslPath = Get-ToolPath -Name "wsl"
$codexPath = Get-ToolPath -Name "codex"
$shellBridgeReady = ($null -ne $bashPath) -or ($null -ne $wslPath)

$commandPreview = @(
    "powershell",
    "-NoProfile",
    "-File", $codexWrapper,
    "-Profile", "qa",
    "-Url", $Url,
    "-Scenario", $Scenario
)

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
    Write-Host "- qa skill     : $qaSkillReady"
    Write-Host "- command      : $($commandPreview -join ' ')"
    Write-Host ""
    Write-Host "DryRun only. Real execution uses Codex CLI plus repo-local gstack QA skills; it remains blocked until those prerequisites are present."
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

if (-not $qaSkillReady) {
    $candidateList = ($qaSkillCandidates -join ", ")
    Write-Error "Repo-local gstack QA skill is missing. Expected one of: $candidateList"
}

& $codexWrapper -Profile "qa" -Url $Url -Scenario $Scenario -BundlePath $BundlePath
