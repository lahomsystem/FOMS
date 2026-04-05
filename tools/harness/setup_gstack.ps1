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

function Convert-WindowsPathToWsl {
    param([string]$WindowsPath)

    if ([string]::IsNullOrWhiteSpace($WindowsPath)) {
        return $null
    }

    $normalized = $WindowsPath.Replace('\', '/')
    if ($normalized -match '^([A-Za-z]):/(.+)$') {
        $drive = $matches[1].ToLowerInvariant()
        $pathPart = $matches[2]
        return "/mnt/$drive/$pathPart"
    }

    return $normalized
}

function Convert-WindowsPathToGitBash {
    param([string]$WindowsPath)

    if ([string]::IsNullOrWhiteSpace($WindowsPath)) {
        return $null
    }

    $normalized = $WindowsPath.Replace('\', '/')
    if ($normalized -match '^([A-Za-z]):/(.+)$') {
        $drive = $matches[1].ToLowerInvariant()
        $pathPart = $matches[2]
        return "/$drive/$pathPart"
    }

    return $normalized
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedVendorRoot = Join-Path $repoRoot $VendorRoot
$vendorManifest = Join-Path $resolvedVendorRoot "VENDOR.md"
$snapshotManifest = Join-Path $resolvedVendorRoot "upstream\SNAPSHOT.md"
$setupEntrypoint = Join-Path $resolvedVendorRoot "setup"

Write-Host "== FOMS gstack setup preflight (validation only) =="
Write-Host "Repo root : $repoRoot"
Write-Host "Vendor dir: $resolvedVendorRoot"

$gitPath = Get-ToolPath -Name "git"
$nodePath = Get-ToolPath -Name "node"
$bunPath = Get-ToolPath -Name "bun"
$bashPath = Get-ToolPath -Name "bash"
$wslPath = Get-ToolPath -Name "wsl"
$pwshPath = Get-ToolPath -Name "pwsh"

$gitDetail = if ($null -ne $gitPath) { $gitPath } else { "not found" }
$nodeDetail = if ($null -ne $nodePath) { $nodePath } else { "not found" }
$bunDetail = if ($null -ne $bunPath) { $bunPath } else { "not found" }
$bashDetail = if ($null -ne $bashPath) { $bashPath } else { "not found" }
$wslDetail = if ($null -ne $wslPath) { $wslPath } else { "not found" }
$pwshDetail = if ($null -ne $pwshPath) { $pwshPath } else { "not found (optional)" }
$vendorReady = Test-Path $vendorManifest
$snapshotReady = Test-Path $snapshotManifest
$setupReady = Test-Path $setupEntrypoint
$shellBridgeReady = ($null -ne $bashPath) -or ($null -ne $wslPath)
$wslVendorRoot = Convert-WindowsPathToWsl -WindowsPath $resolvedVendorRoot
$gitBashVendorRoot = Convert-WindowsPathToGitBash -WindowsPath $resolvedVendorRoot
$vendorDetail = if ($vendorReady) { $vendorManifest } else { "VENDOR.md not found yet" }
$snapshotDetail = if ($snapshotReady) { $snapshotManifest } else { "Pinned upstream snapshot not found yet" }
$setupDetail = if ($setupReady) { $setupEntrypoint } else { "Repo-local upstream setup entrypoint not imported yet" }
$shellBridgeDetail = if ($null -ne $bashPath) {
    "Git Bash: $bashPath"
} elseif ($null -ne $wslPath) {
    "WSL: $wslPath"
} else {
    "not found (Git Bash or WSL required for real runtime on Windows)"
}
$setupCommandDetail = if ($setupReady -and ($null -ne $wslPath)) {
    "wsl bash -lc `"cd '$wslVendorRoot' && bash ./setup --host codex`""
} elseif ($setupReady -and ($null -ne $bashPath)) {
    "bash -lc `"cd '$gitBashVendorRoot' && bash ./setup --host codex`""
} else {
    "Unavailable until repo-local setup entrypoint and shell bridge are present"
}

Write-Status -Label "PowerShell" -Ok $true -Detail "Version $($PSVersionTable.PSVersion)"
Write-Status -Label "git" -Ok ($null -ne $gitPath) -Detail $gitDetail
Write-Status -Label "node" -Ok ($null -ne $nodePath) -Detail $nodeDetail
Write-Status -Label "bun" -Ok ($null -ne $bunPath) -Detail $bunDetail
Write-Status -Label "bash" -Ok ($null -ne $bashPath) -Detail $bashDetail
Write-Status -Label "wsl" -Ok ($null -ne $wslPath) -Detail $wslDetail
Write-Status -Label "shell bridge" -Ok $shellBridgeReady -Detail $shellBridgeDetail
Write-Status -Label "pwsh" -Ok ($null -ne $pwshPath) -Detail $pwshDetail
Write-Status -Label "vendor boundary" -Ok $vendorReady -Detail $vendorDetail
Write-Status -Label "vendor snapshot" -Ok $snapshotReady -Detail $snapshotDetail
Write-Status -Label "setup entrypoint" -Ok $setupReady -Detail $setupDetail
Write-Status -Label "codex setup command" -Ok ($setupReady -and $shellBridgeReady) -Detail $setupCommandDetail

if ($AllowInstall) {
    Write-Warning "Automatic install is intentionally not implemented in Phase 2 kickoff. Use this script for detection/reporting only."
}

if ($WhatIf) {
    Write-Host ""
    Write-Host "WhatIf summary:"
    Write-Host "- This script currently validates local prerequisites and vendor boundary readiness."
    Write-Host "- The pinned upstream snapshot is treated as the minimum import gate for later runtime work."
    Write-Host "- The pinned repo-local setup entrypoint is '.agents/skills/gstack/setup --host codex'."
    Write-Host "- Upstream Windows runtime currently implies: git + node + bun + (Git Bash or WSL)."
    Write-Host "- This script never runs upstream ./setup in Phase 2; it only validates readiness."
    Write-Host "- It does not install gstack, Node, Bun, bash, or Playwright."
    Write-Host "- After upstream source import, this script can be extended with pinned setup steps."
    exit 0
}

if (-not (Test-Path $vendorManifest)) {
    Write-Error "gstack vendor boundary is missing. Import the upstream snapshot into '$resolvedVendorRoot' and keep VENDOR.md in place."
}

if (-not (Test-Path $snapshotManifest)) {
    Write-Error "Pinned upstream snapshot is missing. Import '$snapshotManifest' before real setup can continue."
}

if (-not (Test-Path $setupEntrypoint)) {
    Write-Error "Repo-local setup entrypoint is missing at '$setupEntrypoint'. The current vendor zone is still docs-first. Import the upstream source tree before real setup can continue."
}

if ($null -eq $nodePath) {
    Write-Error "Node.js is missing. Upstream gstack requires Node.js on Windows for real runtime execution."
}

if ($null -eq $bunPath) {
    Write-Error "Bun is missing. Upstream gstack requires Bun for setup/build even when Windows browse execution falls back to Node.js."
}

if (-not $shellBridgeReady) {
    Write-Error "Neither Git Bash nor WSL was found. One shell bridge is required before real gstack setup can continue on Windows."
}

Write-Host ""
Write-Host "Validation complete. Vendor boundary, pinned snapshot, setup entrypoint, Node.js, Bun, and a Windows shell bridge are present."
Write-Host "No upstream ./setup command was executed by this script."
