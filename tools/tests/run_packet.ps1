<#
.SYNOPSIS
    Local PR gate runner for a single FOMS bug-audit packet.

.DESCRIPTION
    Loads the packet entry from docs/harness/foms_bugfix_packet_tests.json,
    runs the common APP_OK gate, then runs the packet's own `commands` in order.
    Exits 1 on the first failure, 0 when all pass. Runs local tree/diff/test
    only -- it never inspects or guesses deploy state (report §8.1).

    PowerShell 5.x compatible.

.PARAMETER PacketId
    Literal PR/packet ID, e.g. BASE-00.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PacketId
)

# Win11 cp949 console: force UTF-8 output so Korean text is not mangled.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifestPath = Join-Path $repoRoot 'docs\harness\foms_bugfix_packet_tests.json'

if (-not (Test-Path $manifestPath)) {
    Write-Error "manifest not found: $manifestPath"
    exit 1
}

try {
    $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
} catch {
    Write-Error "manifest parse failed: $($_.Exception.Message)"
    exit 1
}

$names = @($manifest.PSObject.Properties.Name)
if ($names -notcontains $PacketId) {
    Write-Error "unknown packet id: $PacketId"
    exit 1
}
$entry = $manifest.$PacketId

Push-Location $repoRoot
try {
    # Common gate: application import must succeed.
    Write-Host "[run_packet] $PacketId :: APP_OK gate"
    python -c "import app; print('APP_OK')"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "APP_OK gate failed for $PacketId"
        exit 1
    }

    # Packet-owned commands (seed is empty; each packet appends its own).
    $commands = @($entry.commands)
    foreach ($cmd in $commands) {
        if ([string]::IsNullOrWhiteSpace($cmd)) { continue }
        Write-Host "[run_packet] $PacketId :: $cmd"
        Invoke-Expression $cmd
        if ($LASTEXITCODE -ne 0) {
            Write-Error "command failed ($PacketId): $cmd"
            exit 1
        }
    }

    Write-Host "[run_packet] OK: $PacketId"
    exit 0
} finally {
    Pop-Location
}
