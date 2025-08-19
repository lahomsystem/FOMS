@echo off
echo 🔄 주소변환시스템 재빌드를 시작합니다...
echo.

echo 📁 이전 빌드 파일 정리 중...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo 🛠️ 새로운 실행 파일 빌드 중...
pyinstaller build_exe.spec --clean

echo.
if exist "dist\주소변환시스템.exe" (
    echo ✅ 빌드 완료! 
    echo 📍 파일 위치: dist\주소변환시스템.exe
    echo.
    echo 🚀 실행 파일을 바로 실행하시겠습니까? (Y/N)
    set /p choice=
    if /i "%choice%"=="Y" (
        echo 실행 중...
        start "" "dist\주소변환시스템.exe"
    )
) else (
    echo ❌ 빌드 실패! 오류를 확인해주세요.
)

echo.
pause 