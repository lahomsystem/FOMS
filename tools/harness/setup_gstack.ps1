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
$ethosPath = Join-Path $resolvedVendorRoot "ETHOS.md"
$reviewChecklistPath = Join-Path $resolvedVendorRoot "review\checklist.md"
$qaSourceSkillPath = Join-Path $resolvedVendorRoot "qa\SKILL.md.tmpl"
$upgradeMigrationPath = Join-Path $resolvedVendorRoot "gstack-upgrade\migrations\v0.15.2.0.sh"
$buildSourceMarkerPath = Join-Path $resolvedVendorRoot "scripts\gen-skill-docs.ts"
$browseSourceMarkerPath = Join-Path $resolvedVendorRoot "browse\src\cli.ts"
$designSourceMarkerPath = Join-Path $resolvedVendorRoot "design\src\cli.ts"
$templateMarkerPath = Join-Path $resolvedVendorRoot "SKILL.md.tmpl"
$generatedCodexSkillPath = Join-Path $resolvedVendorRoot ".agents\skills\gstack\SKILL.md"
$browseBinaryPath = Join-Path $resolvedVendorRoot "browse\dist\browse"
$browseBinaryExePath = Join-Path $resolvedVendorRoot "browse\dist\browse.exe"

Write-Host "== FOMS gstack setup preflight (validation only) =="
Write-Host "Repo root : $repoRoot"
Write-Host "Vendor dir: $resolvedVendorRoot"

$gitPath = Get-ToolPath -Name "git"
$nodePath = Get-ToolPath -Name "node"
$bunPath = Get-ToolPath -Name "bun"
$bashPath = Resolve-GitBashPath -GitPath $gitPath
$rawWslPath = Get-ToolPath -Name "wsl"
$wslReady = Test-WslReady -WslPath $rawWslPath
$wslPath = if ($wslReady) { $rawWslPath } else { $null }
$pwshPath = Get-ToolPath -Name "pwsh"

$gitDetail = if ($null -ne $gitPath) { $gitPath } else { "not found" }
$nodeDetail = if ($null -ne $nodePath) { $nodePath } else { "not found" }
$bunDetail = if ($null -ne $bunPath) { $bunPath } else { "not found" }
$bashDetail = if ($null -ne $bashPath) { $bashPath } else { "not found" }
$wslDetail = if ($null -ne $rawWslPath) {
    if ($wslReady) {
        $rawWslPath
    } else {
        "$rawWslPath (not configured with an installed distro)"
    }
} else {
    "not found"
}
$pwshDetail = if ($null -ne $pwshPath) { $pwshPath } else { "not found (optional)" }
$vendorReady = Test-Path $vendorManifest
$snapshotReady = Test-Path $snapshotManifest
$setupReady = Test-Path $setupEntrypoint
$shellBridgeReady = ($null -ne $bashPath) -or ($null -ne $wslPath)
$runtimeStaticReady = (Test-Path $ethosPath) -and (Test-Path $reviewChecklistPath) -and (Test-Path $qaSourceSkillPath) -and (Test-Path $upgradeMigrationPath)
$buildSourceReady = (Test-Path $buildSourceMarkerPath) -and (Test-Path $browseSourceMarkerPath) -and (Test-Path $designSourceMarkerPath) -and (Test-Path $templateMarkerPath)
$generatedCodexSkillReady = Test-Path $generatedCodexSkillPath
$browseBinaryReady = (Test-Path $browseBinaryPath) -or (Test-Path $browseBinaryExePath)
$wslVendorRoot = Convert-WindowsPathToWsl -WindowsPath $resolvedVendorRoot
$gitBashVendorRoot = Convert-WindowsPathToGitBash -WindowsPath $resolvedVendorRoot
$vendorDetail = if ($vendorReady) { $vendorManifest } else { "VENDOR.md not found yet" }
$snapshotDetail = if ($snapshotReady) { $snapshotManifest } else { "Pinned upstream snapshot not found yet" }
$setupDetail = if ($setupReady) { $setupEntrypoint } else { "Repo-local upstream setup entrypoint not imported yet" }
$runtimeStaticDetail = if ($runtimeStaticReady) {
    "ETHOS.md, review/checklist.md, qa/SKILL.md.tmpl, and gstack-upgrade migration are present"
} else {
    "Static runtime subset is incomplete (ETHOS/review/qa/gstack-upgrade)"
}
$buildSourceDetail = if ($buildSourceReady) {
    "gen-skill-docs, browse/design source, and root skill template are present"
} else {
    "Build/generated-skill source layer is incomplete"
}
$generatedCodexSkillDetail = if ($generatedCodexSkillReady) {
    $generatedCodexSkillPath
} else {
    "Generated Codex skill layer not present yet (.agents/skills/gstack/SKILL.md)"
}
$browseBinaryDetail = if (Test-Path $browseBinaryPath) {
    $browseBinaryPath
} elseif (Test-Path $browseBinaryExePath) {
    $browseBinaryExePath
} else {
    "Compiled browse binary not present yet (browse/dist/browse or browse/dist/browse.exe)"
}
$shellBridgeDetail = if ($null -ne $bashPath) {
    "Git Bash: $bashPath"
} elseif ($null -ne $wslPath) {
    "WSL: $wslPath"
} else {
    "not found (Git Bash or WSL required for real runtime on Windows)"
}
$setupCommandDetail = if ($setupReady -and ($null -ne $bashPath)) {
    "& `"$bashPath`" -lc `"cd '$gitBashVendorRoot' && bash ./setup --host codex --no-prefix`""
} elseif ($setupReady -and ($null -ne $wslPath)) {
    "wsl bash -lc `"cd '$wslVendorRoot' && bash ./setup --host codex --no-prefix`""
} else {
    "Unavailable until repo-local setup entrypoint and shell bridge are present"
}

Write-Status -Label "PowerShell" -Ok $true -Detail "Version $($PSVersionTable.PSVersion)"
Write-Status -Label "git" -Ok ($null -ne $gitPath) -Detail $gitDetail
Write-Status -Label "node" -Ok ($null -ne $nodePath) -Detail $nodeDetail
Write-Status -Label "bun" -Ok ($null -ne $bunPath) -Detail $bunDetail
Write-Status -Label "bash" -Ok ($null -ne $bashPath) -Detail $bashDetail
Write-Status -Label "wsl" -Ok $wslReady -Detail $wslDetail
Write-Status -Label "shell bridge" -Ok $shellBridgeReady -Detail $shellBridgeDetail
Write-Status -Label "pwsh" -Ok ($null -ne $pwshPath) -Detail $pwshDetail
Write-Status -Label "vendor boundary" -Ok $vendorReady -Detail $vendorDetail
Write-Status -Label "vendor snapshot" -Ok $snapshotReady -Detail $snapshotDetail
Write-Status -Label "setup entrypoint" -Ok $setupReady -Detail $setupDetail
Write-Status -Label "runtime static subset" -Ok $runtimeStaticReady -Detail $runtimeStaticDetail
Write-Status -Label "build source layer" -Ok $buildSourceReady -Detail $buildSourceDetail
Write-Status -Label "generated codex skills" -Ok $generatedCodexSkillReady -Detail $generatedCodexSkillDetail
Write-Status -Label "browse binary" -Ok $browseBinaryReady -Detail $browseBinaryDetail
Write-Status -Label "codex setup command" -Ok ($setupReady -and $shellBridgeReady) -Detail $setupCommandDetail

if ($AllowInstall) {
    Write-Warning "Automatic install is intentionally not implemented in Phase 2 kickoff. Use this script for detection/reporting only."
}

if ($WhatIf) {
    Write-Host ""
    Write-Host "WhatIf summary:"
    Write-Host "- This script currently validates local prerequisites and vendor boundary readiness."
    Write-Host "- The pinned upstream snapshot is treated as the minimum import gate for later runtime work."
    Write-Host "- The pinned repo-local setup entrypoint is '.agents/skills/gstack/setup --host codex --no-prefix'."
    Write-Host "- The static runtime subset is imported separately from the generated-skill outputs."
    Write-Host "- The build/generated skill source layer is imported separately from generated skills and browse/dist."
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
