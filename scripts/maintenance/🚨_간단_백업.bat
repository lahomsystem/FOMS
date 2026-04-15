@echo off
REM Wave 1 W1-B4: 배치 위치는 scripts\maintenance — 저장소 루트로 이동 후 실행
cd /d "%~dp0..\.."
chcp 65001 > nul
echo ════════════════════════════════════════════════════════════════
echo                    🚨 FOMS 간단 백업 시스템
echo ════════════════════════════════════════════════════════════════
echo.
echo 이 배치 파일은 FOMS 시스템의 간단한 백업을 실행합니다.
echo.
echo 백업 내용:
echo   📁 데이터베이스 (PostgreSQL furniture_orders)
echo   📄 시스템 파일들 (app.py, models.py, templates 등)
echo.
echo 백업 위치:
echo   1차: 로컬 백업 (backups/tier1_primary)
echo   2차: 다른 폴더 백업 (backups/tier2_secondary)
echo.
echo ════════════════════════════════════════════════════════════════
echo.

pause

echo 백업을 시작합니다...
echo.

python -m foms.services.admin.backup_service

echo.
echo ════════════════════════════════════════════════════════════════
echo                        백업 완료!
echo ════════════════════════════════════════════════════════════════
echo.
echo 복구가 필요할 때는:
echo 1. 각 백업 폴더의 "🔧_복구_스크립트.bat" 실행
echo 2. 또는 웹 관리자 페이지에서 백업 기능 사용
echo.
echo 백업 위치를 확인해보세요:
echo - backups/tier1_primary/
echo - backups/tier2_secondary/
echo.
pause 