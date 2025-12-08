@echo off
chcp 65001 >nul
echo ========================================
echo   가구 견적 계산기 (WDCalculator) 실행
echo ========================================
echo.

REM 현재 스크립트의 디렉토리로 이동
cd /d "%~dp0"

REM FOMS 프로젝트 루트 디렉토리로 이동
cd ..\..

REM Python UTF-8 모드 강제 설정
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM 시스템 로케일 UTF-8 설정
set LC_ALL=C.UTF-8
set LANG=C.UTF-8

echo 환경 변수 설정 완료
echo.
echo Flask 애플리케이션 시작 중...
echo 서버가 시작되면 브라우저에서 다음 주소로 접속하세요:
echo   http://localhost:5000/wdcalculator
echo.
echo 종료하려면 Ctrl+C를 누르세요.
echo.

REM Flask 앱 실행
python app.py

pause

