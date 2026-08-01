<#
.SYNOPSIS
    PostgreSQL test-lane runner (PGTEST-00). PowerShell 5.x compatible.

.DESCRIPTION
    Runs the opt-in PostgreSQL lane (tests/postgres) used by the downstream
    concurrency / lock / SKIP LOCKED packets. Requires FOMS_TEST_DATABASE_URL
    (or the PG* env family) to point at a LOCAL PostgreSQL. Fails clearly and
    early when the env var is missing or targets a non-local host -- mirroring
    the authoritative guard in tests/postgres/conftest.py. Never hard-codes
    credentials; the DSN comes from the environment.

    Local example (dev credentials passed via env, never committed):
        $env:FOMS_TEST_DATABASE_URL = 'postgresql://postgres:<pw>@127.0.0.1:5432/postgres'
        powershell -NoProfile -File tools/tests/run_postgres_concurrency.ps1

.PARAMETER PytestArgs
    Extra args forwarded to pytest (default: -q).

.NOTES
    Exit codes: 2 = misconfiguration (missing/non-local DSN); otherwise the
    pytest exit code is propagated.
#>
[CmdletBinding()]
param(
    [string[]]$PytestArgs = @('-q')
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$dsn = $env:FOMS_TEST_DATABASE_URL
if ([string]::IsNullOrWhiteSpace($dsn) -and -not [string]::IsNullOrWhiteSpace($env:PGHOST)) {
    # conftest assembles the real DSN from PG*; build a parseable stand-in for the host guard.
    $pgUser = if ([string]::IsNullOrWhiteSpace($env:PGUSER)) { 'postgres' } else { $env:PGUSER }
    $pgPort = if ([string]::IsNullOrWhiteSpace($env:PGPORT)) { '5432' } else { $env:PGPORT }
    $pgDb   = if ([string]::IsNullOrWhiteSpace($env:PGDATABASE)) { 'postgres' } else { $env:PGDATABASE }
    $dsn = "postgresql://$pgUser@$($env:PGHOST):$pgPort/$pgDb"
}

if ([string]::IsNullOrWhiteSpace($dsn)) {
    # Write-Error would terminate under ErrorActionPreference=Stop before exit 2 runs.
    [Console]::Error.WriteLine("FOMS_TEST_DATABASE_URL not set. The PostgreSQL lane requires a local PG DSN, e.g. postgresql://postgres:<pw>@127.0.0.1:5432/postgres")
    exit 2
}

try {
    $uri = [System.Uri]$dsn
    $pgHostName = $uri.Host.Trim('[', ']')
} catch {
    [Console]::Error.WriteLine("FOMS_TEST_DATABASE_URL is not a parseable URL: $dsn")
    exit 2
}

$localHosts = @('localhost', '127.0.0.1', '::1')
if ($localHosts -notcontains $pgHostName.ToLower()) {
    [Console]::Error.WriteLine("Refusing non-local PostgreSQL host '$pgHostName'. The lane allows only: $($localHosts -join ', ').")
    exit 2
}

Push-Location $repoRoot
try {
    Write-Host "[pg-lane] host=$pgHostName :: python -m pytest tests/postgres $($PytestArgs -join ' ')"
    & python -m pytest tests/postgres @PytestArgs
    $rc = $LASTEXITCODE
    exit $rc
} finally {
    Pop-Location
}
