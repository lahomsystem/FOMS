@echo off
echo 🚀 주소변환시스템 개발 모드 시작...
echo 📝 소스코드 변경사항이 자동으로 반영됩니다.
echo.

echo 🔍 Python 및 Streamlit 설치 확인 중...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python이 설치되지 않았습니다.
    pause
    exit /b 1
)

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Streamlit이 설치되지 않았습니다. 설치 중...
    pip install streamlit
)

echo ✅ 환경 확인 완료
echo.
echo 🌐 브라우저에서 자동으로 열립니다...
echo 💡 종료하려면 Ctrl+C를 누르세요.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

streamlit run main_app.py --server.headless true --browser.gatherUsageStats false

echo.
echo 👋 개발 서버가 종료되었습니다.
pause 