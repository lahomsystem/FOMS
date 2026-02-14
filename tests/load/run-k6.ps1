param(
    [ValidateSet("baseline", "soak", "spike")]
    [string]$TestProfile = "baseline",

    [string]$BaseUrl = "https://lahom-dev.up.railway.app",
    [string]$CookieName = "session_staging",
    [int]$TargetUsers = 150,
    [string]$Duration = "20m",
    [int]$SpikeUsers = 220,
    [string]$SpikeHold = "4m",

    [string]$SessionCookie = "",
    [string]$ChatRoomId = "",
    [string]$ChatDownloadKey = "",

    [switch]$DisableStrictCookiePool,
    [switch]$DisableTraceErrors,
    [switch]$EnableResponseBodyTrace,
    [ValidateRange(0, 100)]
    [int]$TraceErrorSamplePercent = 20,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ValidCookieCount {
    param(
        [string]$Path,
        [string]$CookieNameValue
    )

    if (-not (Test-Path $Path)) {
        return 0
    }

    $count = 0
    $lines = Get-Content $Path
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (($trimmed -eq "") -or ($trimmed.StartsWith("#"))) {
            continue
        }

        if ($trimmed.StartsWith("$CookieNameValue=")) {
            $trimmed = $trimmed.Substring($CookieNameValue.Length + 1).Trim()
        }

        if ($trimmed -ne "") {
            $count += 1
        }
    }

    return $count
}

try {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
    $testScript = Join-Path $repoRoot "tests/load/foms_150_realistic.js"
    $cookieFile = Join-Path $repoRoot "tests/load/session_cookies.txt"
    $resultsDir = Join-Path $repoRoot "tests/load/results"
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $summaryJsonRel = "tests/load/results/$($TestProfile)_$($timestamp).json"
    $summaryTxtRel = "tests/load/results/$($TestProfile)_$($timestamp).txt"

    $k6Cmd = Get-Command "k6" -ErrorAction SilentlyContinue
    if (-not $k6Cmd) {
        Write-Output "[X] k6 command not found."
        Write-Output "[i] Install: winget install -e --id k6.k6"
        exit 1
    }

    if (-not (Test-Path $testScript)) {
        Write-Output "[X] Test script not found: $testScript"
        exit 1
    }

    New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

    $strictCookiePool = "true"
    if ($DisableStrictCookiePool.IsPresent) {
        $strictCookiePool = "false"
    }

    $cookieCount = Get-ValidCookieCount -Path $cookieFile -CookieNameValue $CookieName
    if (($strictCookiePool -eq "true") -and ($cookieCount -lt $TargetUsers) -and ($SessionCookie -eq "")) {
        Write-Output "[X] Cookie pool is too small."
        Write-Output "[i] required=$TargetUsers current=$cookieCount file=$cookieFile"
        Write-Output "[i] Add more cookies or use -DisableStrictCookiePool for non-realistic smoke runs."
        exit 1
    }

    $traceSampleRate = [Math]::Round(($TraceErrorSamplePercent / 100.0), 2)
    $traceErrorsValue = "true"
    if ($DisableTraceErrors.IsPresent) {
        $traceErrorsValue = "false"
    }

    $discardBodiesValue = "true"
    if ($EnableResponseBodyTrace.IsPresent) {
        $discardBodiesValue = "false"
    }

    $k6Args = @(
        "run", $testScript,
        "-e", "BASE_URL=$BaseUrl",
        "-e", "COOKIE_NAME=$CookieName",
        "-e", "TARGET_USERS=$TargetUsers",
        "-e", "TEST_PROFILE=$TestProfile",
        "-e", "TEST_DURATION=$Duration",
        "-e", "SPIKE_USERS=$SpikeUsers",
        "-e", "SPIKE_HOLD=$SpikeHold",
        "-e", "STRICT_COOKIE_POOL=$strictCookiePool",
        "-e", "TRACE_ERRORS=$traceErrorsValue",
        "-e", "TRACE_ERROR_SAMPLE_RATE=$traceSampleRate",
        "-e", "DISCARD_RESPONSE_BODIES=$discardBodiesValue",
        "-e", "TRACE_SUMMARY_JSON=$summaryJsonRel",
        "-e", "TRACE_SUMMARY_TXT=$summaryTxtRel"
    )

    if ($SessionCookie -ne "") {
        $k6Args += @("-e", "SESSION_COOKIE=$SessionCookie")
    }
    if ($ChatRoomId -ne "") {
        $k6Args += @("-e", "CHAT_ROOM_ID=$ChatRoomId")
    }
    if ($ChatDownloadKey -ne "") {
        $k6Args += @("-e", "CHAT_DOWNLOAD_KEY=$ChatDownloadKey")
    }

    $previewParts = @()
    foreach ($arg in $k6Args) {
        if ($arg -match "\s") {
            $previewParts += "`"$arg`""
        } else {
            $previewParts += $arg
        }
    }
    $preview = "k6 " + ($previewParts -join " ")

    Write-Output "[i] profile=$TestProfile target_users=$TargetUsers duration=$Duration"
    Write-Output "[i] cookies=$cookieCount strict_cookie_pool=$strictCookiePool"
    Write-Output "[i] summary_json=$summaryJsonRel"
    Write-Output "[i] summary_txt=$summaryTxtRel"
    Write-Output "[i] command=$preview"

    if ($DryRun.IsPresent) {
        Write-Output "[OK] Dry run complete."
        exit 0
    }

    Push-Location $repoRoot
    try {
        & k6 @k6Args
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($exitCode -ne 0) {
        Write-Output "[X] k6 finished with exit code $exitCode"
        exit $exitCode
    }

    Write-Output "[OK] k6 run completed."
    Write-Output "[OK] summary files:"
    Write-Output "     $summaryJsonRel"
    Write-Output "     $summaryTxtRel"
    exit 0
}
catch {
    Write-Output "[X] run-k6.ps1 failed: $($_.Exception.Message)"
    exit 1
}
