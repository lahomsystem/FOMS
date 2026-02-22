# Phase C / Windows: alembic 실행 시 DATABASE_URL을 명시하여 UnicodeDecodeError 방지.
# 사용법: .\scripts\run_alembic.ps1 [alembic 인자...]
# 예: .\scripts\run_alembic.ps1 upgrade head
#     .\scripts\run_alembic.ps1 current

$DefaultDbUrl = "postgresql://postgres:lahom@localhost:5432/furniture_orders"
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = $DefaultDbUrl }
Push-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
try { alembic @args }
finally { Pop-Location }
