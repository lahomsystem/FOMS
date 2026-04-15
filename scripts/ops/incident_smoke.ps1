param(
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [string]$Username = "",
    [string]$Password = "",
    [int]$TimeoutSec = 8
)

$ErrorActionPreference = "Stop"

function Invoke-RawRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Body = $null,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session = $null
    )

    try {
        $params = @{
            Method            = $Method
            Uri               = $Uri
            TimeoutSec        = $TimeoutSec
            MaximumRedirection = 0
            ErrorAction       = "Stop"
        }
        if ($Body) { $params["Body"] = $Body }
        if ($Session) { $params["WebSession"] = $Session }

        $resp = Invoke-WebRequest @params
        return @{
            status  = [int]$resp.StatusCode
            headers = $resp.Headers
            content = [string]$resp.Content
            error   = ""
        }
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            $content = ""
            try {
                $stream = $resp.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $content = $reader.ReadToEnd()
                    $reader.Dispose()
                }
            } catch {}

            return @{
                status  = [int]$resp.StatusCode
                headers = $resp.Headers
                content = [string]$content
                error   = $_.Exception.Message
            }
        }

        return @{
            status  = 0
            headers = @{}
            content = ""
            error   = $_.Exception.Message
        }
    }
}

function Add-Result {
    param(
        [System.Collections.Generic.List[object]]$Bucket,
        [string]$Name,
        [bool]$Pass,
        [string]$Detail
    )
    $Bucket.Add([pscustomobject]@{
        Check  = $Name
        Pass   = $Pass
        Detail = $Detail
    })
}

$results = New-Object 'System.Collections.Generic.List[object]'

Write-Host "[SMOKE] BaseUrl=$BaseUrl TimeoutSec=$TimeoutSec"

# 1) /debug-redirect
$r1 = Invoke-RawRequest -Method "GET" -Uri "$BaseUrl/debug-redirect"
$ok1 = ($r1.status -eq 200 -or $r1.status -eq 404)
$d1 = if ($r1.status -eq 404) { "status=404 (optional endpoint missing)" } else { "status=$($r1.status)" }
Add-Result -Bucket $results -Name "GET /debug-redirect" -Pass $ok1 -Detail $d1

# 2) /login
$r2 = Invoke-RawRequest -Method "GET" -Uri "$BaseUrl/login"
$ok2 = ($r2.status -eq 200 -or $r2.status -eq 302)
Add-Result -Bucket $results -Name "GET /login" -Pass $ok2 -Detail "status=$($r2.status)"

# 3) /debug-db
$r3 = Invoke-RawRequest -Method "GET" -Uri "$BaseUrl/debug-db"
$ok3 = (($r3.status -eq 200 -and $r3.content -match '"status"\s*:\s*"(SUCCESS|WARNING)"') -or $r3.status -eq 404)
$d3 = if ($r3.status -eq 404) { "status=404 (optional endpoint missing)" } else { "status=$($r3.status)" }
Add-Result -Bucket $results -Name "GET /debug-db" -Pass $ok3 -Detail $d3

# 4) Optional login flow
if ($Username -and $Password) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $loginResp = Invoke-RawRequest -Method "POST" -Uri "$BaseUrl/login" -Body @{
        username = $Username
        password = $Password
        next     = "/"
    } -Session $session

    $homeResp = Invoke-RawRequest -Method "GET" -Uri "$BaseUrl/" -Session $session
    $isLoginPage = ($homeResp.content -match 'id="username"' -and $homeResp.content -match 'autocomplete="current-password"')
    $isOrderPage = ($homeResp.content -match "order-list-search" -or $homeResp.content -match "table-fixed-header")
    $homePass = ($homeResp.status -eq 200 -and -not $isLoginPage -and $isOrderPage)
    $loginPass = ($loginResp.status -eq 302 -or $loginResp.status -eq 303 -or $loginResp.status -eq 200 -or $homePass)
    $loginDetail = "status=$($loginResp.status)"
    if ($loginResp.error) { $loginDetail = "$loginDetail, error=$($loginResp.error)" }
    Add-Result -Bucket $results -Name "POST /login ($Username)" -Pass $loginPass -Detail $loginDetail
    Add-Result -Bucket $results -Name "GET / after login" -Pass $homePass -Detail "status=$($homeResp.status)"
}

Write-Host ""
Write-Host "=== Incident Smoke Result ==="
$results | Format-Table -AutoSize

$failed = @($results | Where-Object { -not $_.Pass })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "[SMOKE] FAILED ($($failed.Count) checks)"
    exit 1
}

Write-Host ""
Write-Host "[SMOKE] PASSED"
exit 0
