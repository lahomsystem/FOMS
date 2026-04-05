[CmdletBinding()]
param(
    [switch]$WhatIf,
    [switch]$AllowInstall,
    [string]$VendorRoot = ".agents/skills/gstack"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Status {
    param(
        [string]$Label,
        [bool]$Ok,
        [string]$Detail
    )

    $prefix = if ($Ok) { "[OK]" } else { "[WARN]" }
    Write-Host "$prefix $Label - $Detail"
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

Write-Host "== FOMS gstack setup preflight =="
Write-Host "Repo root : $repoRoot"
Write-Host "Vendor dir: $resolvedVendorRoot"

$gitPath = Get-ToolPath -Name "git"
$nodePath = Get-ToolPath -Name "node"
$bunPath = Get-ToolPath -Name "bun"
$bashPath = Get-ToolPath -Name "bash"
$pwshPath = Get-ToolPath -Name "pwsh"

$gitDetail = if ($null -ne $gitPath) { $gitPath } else { "not found" }
$nodeDetail = if ($null -ne $nodePath) { $nodePath } else { "not found" }
$bunDetail = if ($null -ne $bunPath) { $bunPath } else { "not found" }
$bashDetail = if ($null -ne $bashPath) { $bashPath } else { "not found (optional)" }
$pwshDetail = if ($null -ne $pwshPath) { $pwshPath } else { "not found (optional)" }
$vendorReady = Test-Path $vendorManifest
$vendorDetail = if ($vendorReady) { $vendorManifest } else { "VENDOR.md not found yet" }

Write-Status -Label "PowerShell" -Ok $true -Detail "Version $($PSVersionTable.PSVersion)"
Write-Status -Label "git" -Ok ($null -ne $gitPath) -Detail $gitDetail
Write-Status -Label "node" -Ok ($null -ne $nodePath) -Detail $nodeDetail
Write-Status -Label "bun" -Ok ($null -ne $bunPath) -Detail $bunDetail
Write-Status -Label "bash" -Ok ($null -ne $bashPath) -Detail $bashDetail
Write-Status -Label "pwsh" -Ok ($null -ne $pwshPath) -Detail $pwshDetail
Write-Status -Label "vendor boundary" -Ok $vendorReady -Detail $vendorDetail

if ($AllowInstall) {
    Write-Warning "Automatic install is intentionally not implemented in Phase 2 kickoff. Use this script for detection/reporting only."
}

if ($WhatIf) {
    Write-Host ""
    Write-Host "WhatIf summary:"
    Write-Host "- This script currently validates local prerequisites and vendor boundary readiness."
    Write-Host "- It does not install gstack, Node, Bun, bash, or Playwright."
    Write-Host "- After upstream snapshot import, this script can be extended with pinned setup steps."
    exit 0
}

if (-not (Test-Path $vendorManifest)) {
    Write-Error "gstack vendor boundary is missing. Import the upstream snapshot into '$resolvedVendorRoot' and keep VENDOR.md in place."
}

if (($null -eq $nodePath) -and ($null -eq $bunPath)) {
    Write-Error "Neither node nor bun was found on PATH. At least one runtime is required before real gstack setup can continue."
}

Write-Host ""
Write-Host "Preflight complete. Vendor boundary exists and at least one JS runtime is available."
