param(
    [string]$TaskName = "FOMS-Coding-Research-Center",
    [string]$DayOfWeek = "MON",
    [string]$StartTime = "09:00",
    [string]$SelfManifest = "",
    [string]$McpConfig = "",
    [switch]$SelfUpgradeCreateStubs = $false,
    [switch]$SelfUpgradeInstallSkills = $false,
    [switch]$SelfUpgradeSyncMcp = $true
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonCmd = (Get-Command python -ErrorAction Stop).Source
$scriptPath = Join-Path $repoRoot "tools\\research_center\\coding_research_center.py"

$taskArgs = @(
    "`"$pythonCmd`"",
    "`"$scriptPath`"",
    "--days 9",
    "--apply-limit 12",
    "--sync-radar",
    "--sync-backlog"
)

if ($SelfManifest -ne "") { $taskArgs += "--self-manifest `"$SelfManifest`"" }
if ($McpConfig -ne "") { $taskArgs += "--mcp-config `"$McpConfig`"" }
if ($SelfUpgradeCreateStubs) { $taskArgs += "--self-upgrade-create-stubs" }
if ($SelfUpgradeInstallSkills) { $taskArgs += "--self-upgrade-install-skills" }
if ($SelfUpgradeSyncMcp) { $taskArgs += "--self-upgrade-sync-mcp" }

$taskRun = $taskArgs -join " "

schtasks /Create /F /SC WEEKLY /D $DayOfWeek /ST $StartTime /TN $TaskName /TR $taskRun | Out-Null

Write-Host "[research-center] scheduled task registered: $TaskName ($DayOfWeek $StartTime)"
