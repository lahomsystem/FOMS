#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("dry-run", "execute", "verify")]
    [string]$Mode = "dry-run",
    [string]$ProjectId = "cbe0af66-875b-460c-88f6-780dd705f45c",
    [string]$Environment = "production",
    [string]$Service = "FOMS",
    [int]$OrderId = 0,
    [int]$Limit = 0,
    [int]$SampleLimit = 20,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent | Split-Path -Parent
Set-Location $repoRoot

$scriptPath = "scripts/maintenance/erp_beta_placeholder_backfill.py"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Backfill script not found: $scriptPath"
}

$pythonArgs = @($scriptPath)
switch ($Mode) {
    "execute" {
        $pythonArgs += "--execute"
    }
    "verify" {
        $pythonArgs += "--verify-only"
    }
}

if ($OrderId -gt 0) {
    $pythonArgs += @("--order-id", "$OrderId")
}
if ($Limit -gt 0) {
    $pythonArgs += @("--limit", "$Limit")
}
if ($SampleLimit -gt 0) {
    $pythonArgs += @("--sample-limit", "$SampleLimit")
}
if ($Json) {
    $pythonArgs += "--json"
}

$railwayArgs = @(
    "run",
    "-p", $ProjectId,
    "-e", $Environment,
    "-s", $Service,
    "python"
) + $pythonArgs

Write-Host "=== ERP_BETA placeholder backfill one-off ===" -ForegroundColor Cyan
Write-Host ("Mode        : {0}" -f $Mode)
Write-Host ("Project ID  : {0}" -f $ProjectId)
Write-Host ("Environment : {0}" -f $Environment)
Write-Host ("Service     : {0}" -f $Service)
Write-Host ("Command     : railway {0}" -f (($railwayArgs | ForEach-Object {
            if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
        }) -join " "))

& railway @railwayArgs
exit $LASTEXITCODE
