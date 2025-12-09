@echo off
chcp 65001 >nul
echo ====================================
echo WDPlanner 빌드 및 배치 스크립트
echo ====================================
echo.

REM WDPlanner 디렉토리로 이동
cd /d "%~dp0Add In Program\WDPlanner"

if not exist "package.json" (
    echo 오류: WDPlanner 디렉토리를 찾을 수 없습니다.
    echo 현재 위치: %CD%
    pause
    exit /b 1
)

echo [1/4] 의존성 확인 중...
if not exist "node_modules" (
    echo node_modules가 없습니다. npm install을 실행합니다...
    call npm install
    if errorlevel 1 (
        echo 오류: npm install 실패
        pause
        exit /b 1
    )
) else (
    echo 의존성이 이미 설치되어 있습니다.
)
echo.

echo [2/4] 이전 빌드 파일 정리 중...
if exist "dist" (
    rmdir /s /q "dist"
    echo 이전 빌드 파일 삭제 완료
)
echo.

echo [3/4] 웹 빌드 실행 중...
call npm run build
if errorlevel 1 (
    echo 오류: 빌드 실패
    pause
    exit /b 1
)
echo 빌드 완료!
echo.

echo [4/4] 빌드 파일을 static/wdplanner로 복사 중...
cd /d "%~dp0"

REM static/wdplanner 디렉토리 생성
if not exist "static\wdplanner" (
    mkdir "static\wdplanner"
)

REM 이전 파일 삭제
if exist "static\wdplanner\*" (
    echo 기존 파일 삭제 중...
    del /q "static\wdplanner\*"
    for /d %%d in ("static\wdplanner\*") do (
        rmdir /s /q "%%d"
    )
)

REM 새 파일 복사
echo 파일 복사 중...
xcopy /E /I /Y "Add In Program\WDPlanner\dist\*" "static\wdplanner\"
if errorlevel 1 (
    echo 오류: 파일 복사 실패
    pause
    exit /b 1
)

echo.
echo ====================================
echo 빌드 및 배치 완료!
echo ====================================
echo.
echo WDPlanner는 이제 FOMS 시스템에서 사용할 수 있습니다.
echo 브라우저에서 /wdplanner 경로로 접속하세요.
echo.
pause




