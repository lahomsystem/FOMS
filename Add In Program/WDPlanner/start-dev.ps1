# WDPlanner 개발 서버 시작 스크립트 (PowerShell)

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "WDPlanner 개발 서버 시작" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Vite 캐시 삭제 (선택사항)
if (Test-Path "node_modules\.vite") {
    Write-Host "Vite 캐시 삭제 중..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "node_modules\.vite"
    Write-Host "Vite 캐시 삭제 완료" -ForegroundColor Green
    Write-Host ""
}

Write-Host "개발 서버 시작 중..." -ForegroundColor Green
Write-Host ""

# Electron 개발 서버 시작
npm run electron:dev




