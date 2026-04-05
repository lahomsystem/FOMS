[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Url,

    [Parameter(Mandatory = $true)]
    [string]$Scenario,

    [switch]$DryRun,
    [string]$VendorRoot = ".agents/skills/gstack"
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
$setupScript = Join-Path $PSScriptRoot "setup_gstack.ps1"

if (-not (Test-HttpUrl -Value $Url)) {
    Write-Error "Url must be an absolute http/https URL."
}

if ([string]::IsNullOrWhiteSpace($Scenario)) {
    Write-Error "Scenario must not be empty."
}

$nodePath = Get-ToolPath -Name "node"
$bunPath = Get-ToolPath -Name "bun"
$gstackPath = Get-ToolPath -Name "gstack"

$commandPreview = @(
    "gstack",
    "qa",
    "--url", $Url,
    "--scenario", $Scenario
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
    Write-Host "- vendor ready : $(Test-Path $vendorManifest)"
    Write-Host "- node runtime : $([bool]($null -ne $nodePath))"
    Write-Host "- bun runtime  : $([bool]($null -ne $bunPath))"
    Write-Host "- gstack binary: $([bool]($null -ne $gstackPath))"
    Write-Host "- command      : $($commandPreview -join ' ')"
    Write-Host ""
    Write-Host "DryRun only. Real execution remains blocked until the vendor snapshot and exact runtime entrypoint are pinned."
    exit 0
}

if (-not (Test-Path $vendorManifest)) {
    Write-Error "Vendor boundary missing. Run setup in WhatIf mode and import the upstream snapshot before real QA execution."
}

if (($null -eq $nodePath) -and ($null -eq $bunPath)) {
    Write-Error "Neither node nor bun is available on PATH."
}

if ($null -eq $gstackPath) {
    Write-Error "No 'gstack' executable was found on PATH. Phase 2 kickoff only supports DryRun until the exact invocation path is pinned."
}

& $gstackPath "qa" "--url" $Url "--scenario" $Scenario
