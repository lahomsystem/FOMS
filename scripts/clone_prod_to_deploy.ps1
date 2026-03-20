param(
    [string]$SourceDbUrl = $env:PRODUCTION_DB_URL,
    [string]$TargetDbUrl = $env:DEPLOY_DB_URL,
    [string]$BackupRoot,
    [string]$ExpectedSourceHost = "yamanote.proxy.rlwy.net",
    [string]$ExpectedTargetHost = "maglev.proxy.rlwy.net",
    [string[]]$Schemas = @("public"),
    [int]$RequiredPgMajorVersion = 17,
    [string]$PgDumpPath,
    [string]$PgRestorePath,
    [string]$PsqlPath,
    [switch]$SkipTargetBackup,
    [switch]$SkipAlembic,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Normalize-DbUrl {
    param([Parameter(Mandatory = $true)][string]$Url)

    # Leading/trailing spaces break libpq URI parsing and can force interactive Password: prompts.
    $Url = $Url.Trim()
    if ($Url.StartsWith("postgres://")) {
        return "postgresql://" + $Url.Substring("postgres://".Length)
    }
    return $Url
}

function Get-MaskedDbUrl {
    param([Parameter(Mandatory = $true)][string]$Url)

    $uri = [System.Uri]$Url
    $builder = [System.UriBuilder]::new($uri)
    if ($builder.UserName) {
        $builder.UserName = "***"
    }
    if ($builder.Password) {
        $builder.Password = "***"
    }
    return $builder.Uri.AbsoluteUri.TrimEnd("/")
}

function Get-DbInfo {
    param([Parameter(Mandatory = $true)][string]$Url)

    $uri = [System.Uri]$Url
    return [pscustomobject]@{
        Url      = $Url
        Host     = $uri.Host
        Port     = $uri.Port
        Database = $uri.AbsolutePath.TrimStart("/")
        Masked   = Get-MaskedDbUrl -Url $Url
    }
}

function Assert-SafeRouting {
    param(
        [Parameter(Mandatory = $true)]$Source,
        [Parameter(Mandatory = $true)]$Target,
        [Parameter(Mandatory = $true)][string]$ExpectedSourceHost,
        [Parameter(Mandatory = $true)][string]$ExpectedTargetHost
    )

    if ($Source.Url -eq $Target.Url) {
        throw "Source and target URLs are identical. Aborting."
    }
    if ($Source.Host -eq $Target.Host -and $Source.Port -eq $Target.Port -and $Source.Database -eq $Target.Database) {
        throw "Source and target resolve to the same database endpoint. Aborting."
    }
    if ($Source.Host -eq $ExpectedTargetHost) {
        throw "Source host points to the deploy/staging database. The URLs look swapped."
    }
    if ($Target.Host -eq $ExpectedSourceHost) {
        throw "Target host points to production. Refusing to continue."
    }
    if ($Source.Host -ne $ExpectedSourceHost) {
        throw "Unexpected production host '$($Source.Host)'. Expected '$ExpectedSourceHost'."
    }
    if ($Target.Host -ne $ExpectedTargetHost) {
        throw "Unexpected deploy host '$($Target.Host)'. Expected '$ExpectedTargetHost'."
    }
}

function Find-Executable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "$Name not found. Install PostgreSQL client tools and ensure $Name is available."
}

function Get-ExecutableVersionText {
    param([Parameter(Mandatory = $true)][string]$Exe)

    $output = & $Exe --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read version from $Exe."
    }
    return ($output | Out-String).Trim()
}

function Assert-PgMajorVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string]$ToolName,
        [Parameter(Mandatory = $true)][int]$RequiredMajorVersion
    )

    $versionText = Get-ExecutableVersionText -Exe $Exe
    if ($versionText -notmatch '(\d+)\.') {
        throw "Could not parse $ToolName version from '$versionText'."
    }

    $majorVersion = [int]$Matches[1]
    if ($majorVersion -lt $RequiredMajorVersion) {
        throw "$ToolName version $majorVersion is too old. PostgreSQL client $RequiredMajorVersion+ is required for Railway PostgreSQL 17."
    }

    return $versionText
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$StepName
    )

    Write-Host ""
    Write-Host "[$StepName]" -ForegroundColor Green
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE."
    }
}

function Get-SchemaArguments {
    param([Parameter(Mandatory = $true)][string[]]$SchemaNames)

    $arguments = @()
    foreach ($schemaName in $SchemaNames) {
        $arguments += "--schema"
        $arguments += $schemaName
    }
    return $arguments
}

$ProjectRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $ProjectRoot "app.py"))) {
    throw "Project root not found from script location."
}

Set-Location $ProjectRoot

if (-not $BackupRoot) {
    $BackupRoot = Join-Path $ProjectRoot "backups\prod-to-deploy"
}

if (-not $SourceDbUrl) {
    throw "SourceDbUrl is required. Set PRODUCTION_DB_URL or pass -SourceDbUrl."
}
if (-not $TargetDbUrl) {
    throw "TargetDbUrl is required. Set DEPLOY_DB_URL or pass -TargetDbUrl."
}

$SourceDbUrl = Normalize-DbUrl -Url $SourceDbUrl
$TargetDbUrl = Normalize-DbUrl -Url $TargetDbUrl

$source = Get-DbInfo -Url $SourceDbUrl
$target = Get-DbInfo -Url $TargetDbUrl
Assert-SafeRouting -Source $source -Target $target -ExpectedSourceHost $ExpectedSourceHost -ExpectedTargetHost $ExpectedTargetHost

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

$targetBackupPath = Join-Path $BackupRoot "deploy_before_clone_$timestamp.dump"
$sourceDumpPath = Join-Path $BackupRoot "prod_snapshot_$timestamp.dump"
$schemaArguments = Get-SchemaArguments -SchemaNames $Schemas
$targetBackupArguments = @(
    "--format=custom",
    "--no-owner",
    "--no-privileges",
    "--file", $targetBackupPath
)
$targetBackupArguments += $schemaArguments
$targetBackupArguments += $TargetDbUrl

$sourceDumpArguments = @(
    "--format=custom",
    "--no-owner",
    "--no-privileges",
    "--file", $sourceDumpPath
)
$sourceDumpArguments += $schemaArguments
$sourceDumpArguments += $SourceDbUrl

$pgDump = if ($PgDumpPath) {
    $PgDumpPath
} else {
    Find-Executable -Name "pg_dump" -Candidates @(
    "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
    "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe",
    "pg_dump",
    "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    "C:\Program Files\PostgreSQL\15\bin\pg_dump.exe"
)
}
$pgRestore = if ($PgRestorePath) {
    $PgRestorePath
} else {
    Find-Executable -Name "pg_restore" -Candidates @(
    "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe",
    "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe",
    "pg_restore",
    "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe",
    "C:\Program Files\PostgreSQL\15\bin\pg_restore.exe"
)
}
$psql = if ($PsqlPath) {
    $PsqlPath
} else {
    Find-Executable -Name "psql" -Candidates @(
    "C:\Program Files\PostgreSQL\17\bin\psql.exe",
    "C:\Program Files\PostgreSQL\18\bin\psql.exe",
    "psql",
    "C:\Program Files\PostgreSQL\16\bin\psql.exe",
    "C:\Program Files\PostgreSQL\15\bin\psql.exe"
)
}

$pgDumpVersion = Assert-PgMajorVersion -Exe $pgDump -ToolName "pg_dump" -RequiredMajorVersion $RequiredPgMajorVersion
$pgRestoreVersion = Assert-PgMajorVersion -Exe $pgRestore -ToolName "pg_restore" -RequiredMajorVersion $RequiredPgMajorVersion
$psqlVersion = Assert-PgMajorVersion -Exe $psql -ToolName "psql" -RequiredMajorVersion $RequiredPgMajorVersion

Write-Host "Client tools:" -ForegroundColor DarkGray
Write-Host "- pg_dump    : $pgDumpVersion"
Write-Host "- pg_restore : $pgRestoreVersion"
Write-Host "- psql       : $psqlVersion"

Write-Host "=== Clone production DB to deploy(staging) DB ===" -ForegroundColor Cyan
Write-Host "Source : $($source.Masked)"
Write-Host "Target : $($target.Masked)"
Write-Host "Backup : $BackupRoot"
Write-Host ""
Write-Host "Safety rules:" -ForegroundColor Yellow
Write-Host "- Production is read-only. This script only uses pg_dump against source."
Write-Host "- Deploy(staging) will be fully replaced."
Write-Host "- Host validation blocks a production target by default."
Write-Host "- Schemas included: $($Schemas -join ', ')"

if (-not $NonInteractive) {
    $confirm = Read-Host "Type the deploy host to confirm overwrite ($ExpectedTargetHost)"
    if ($confirm.Trim() -ne $ExpectedTargetHost) {
        throw "Confirmation text mismatch. Aborting."
    }
}

if (-not $SkipTargetBackup) {
    Invoke-Checked -Exe $pgDump -StepName "1/8 Backup current deploy(staging) DB" -Arguments $targetBackupArguments
    Write-Host "Saved deploy backup to $targetBackupPath" -ForegroundColor DarkGray
}
else {
    Write-Host ""
    Write-Host "[1/8 Backup current deploy(staging) DB]" -ForegroundColor Yellow
    Write-Host "Skipped by -SkipTargetBackup"
}

Invoke-Checked -Exe $pgDump -StepName "2/8 Dump production DB" -Arguments $sourceDumpArguments
Write-Host "Saved production snapshot to $sourceDumpPath" -ForegroundColor DarkGray

# DROP only: the archive contains CREATE SCHEMA public; pre-creating it causes duplicate errors.
# pg_dump --schema=public often omits EXTENSION; trigram indexes live in post-data, so we
# install pg_trgm after pre-data and before data/post-data.
Invoke-Checked -Exe $psql -StepName "3/8 Reset deploy(staging): DROP SCHEMA public" -Arguments @(
    $TargetDbUrl,
    "-v", "ON_ERROR_STOP=1",
    "-c", "DROP SCHEMA public CASCADE;"
)

Invoke-Checked -Exe $pgRestore -StepName "4/8 Restore pre-data (schema + table definitions)" -Arguments @(
    "--section=pre-data",
    "--no-owner",
    "--no-privileges",
    "--dbname", $TargetDbUrl,
    $sourceDumpPath
)

Invoke-Checked -Exe $psql -StepName "5/8 CREATE EXTENSION pg_trgm (for trigram indexes in post-data)" -Arguments @(
    $TargetDbUrl,
    "-v", "ON_ERROR_STOP=1",
    "-c", "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
)

Invoke-Checked -Exe $pgRestore -StepName "6/8 Restore table data" -Arguments @(
    "--section=data",
    "--no-owner",
    "--no-privileges",
    "--dbname", $TargetDbUrl,
    $sourceDumpPath
)

Invoke-Checked -Exe $pgRestore -StepName "7/8 Restore post-data (indexes incl. trigram)" -Arguments @(
    "--section=post-data",
    "--no-owner",
    "--no-privileges",
    "--dbname", $TargetDbUrl,
    $sourceDumpPath
)

if (-not $SkipAlembic) {
    Write-Host ""
    Write-Host "[8/8 Run Alembic migrations on deploy(staging)]" -ForegroundColor Green
    $previousDatabaseUrl = $env:DATABASE_URL
    try {
        $env:DATABASE_URL = $TargetDbUrl
        alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic upgrade failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}
else {
    Write-Host ""
    Write-Host "[8/8 Run Alembic migrations on deploy(staging)]" -ForegroundColor Yellow
    Write-Host "Skipped by -SkipAlembic"
}

Write-Host ""
Write-Host "Clone completed successfully." -ForegroundColor Cyan
Write-Host "Deploy backup : $targetBackupPath"
Write-Host "Prod snapshot : $sourceDumpPath"
Write-Host "Next step     : verify staging app behavior against the cloned data."
