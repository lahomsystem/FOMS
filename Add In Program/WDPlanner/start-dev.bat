@echo off
chcp 65001 >nul
echo ====================================
echo WDPlanner 개발 서버 시작
echo ====================================
echo.

REM Vite 캐시 강제 삭제
if exist "node_modules\.vite" (
    echo Vite 캐시 삭제 중...
    rmdir /s /q "node_modules\.vite"
    echo Vite 캐시 삭제 완료
    echo.
) else (
    echo Vite 캐시 폴더가 없습니다.
    echo.
)

echo 개발 서버 시작 중...
echo.

REM Electron 개발 서버 시작
call npm run electron:dev

pause

