param(
    [int]$Days = 9,
    [int]$ApplyLimit = 12,
    [switch]$SyncRadar = $true,
    [switch]$SyncBacklog = $true,
    [string]$SelfManifest = "",
    [string]$McpConfig = "",
    [switch]$SelfUpgradeCreateStubs = $false,
    [switch]$SelfUpgradeInstallSkills = $false,
    [switch]$SelfUpgradeSyncMcp = $true
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$args = @(
    "tools/research_center/coding_research_center.py",
    "--days", "$Days",
    "--apply-limit", "$ApplyLimit"
)

if ($SyncRadar) { $args += "--sync-radar" }
if ($SyncBacklog) { $args += "--sync-backlog" }
if ($SelfManifest -ne "") { $args += @("--self-manifest", "$SelfManifest") }
if ($McpConfig -ne "") { $args += @("--mcp-config", "$McpConfig") }
if ($SelfUpgradeCreateStubs) { $args += "--self-upgrade-create-stubs" }
if ($SelfUpgradeInstallSkills) { $args += "--self-upgrade-install-skills" }
if ($SelfUpgradeSyncMcp) { $args += "--self-upgrade-sync-mcp" }

python @args

Write-Host "[research-center] completed"
