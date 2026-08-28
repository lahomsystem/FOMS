# Phase C / Windows: alembic 실행 시 DATABASE_URL을 명시하여 UnicodeDecodeError 방지.
# 사용법: .\scripts\migrations\run_alembic.ps1 [alembic 인자...]
# 예: .\scripts\migrations\run_alembic.ps1 upgrade head
#     .\scripts\migrations\run_alembic.ps1 current

# Win11 cp949 console: force UTF-8 output so Korean text is not mangled.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$DefaultDbUrl = "postgresql://postgres:lahom@localhost:5432/furniture_orders"
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = $DefaultDbUrl }
Push-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
try { alembic @args }
finally { Pop-Location }
