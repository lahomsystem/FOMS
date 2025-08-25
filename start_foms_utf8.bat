@echo off
echo FOMS UTF-8 모드로 시작 중...
echo.

REM Python UTF-8 모드 강제 설정
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM 시스템 로케일 UTF-8 설정
set LC_ALL=C.UTF-8
set LANG=C.UTF-8

REM PostgreSQL 클라이언트 인코딩 설정
set PGCLIENTENCODING=UTF8

echo 환경 변수 설정 완료:
echo PYTHONUTF8=%PYTHONUTF8%
echo PYTHONIOENCODING=%PYTHONIOENCODING%
echo LC_ALL=%LC_ALL%
echo LANG=%LANG%
echo PGCLIENTENCODING=%PGCLIENTENCODING%
echo.

echo Flask 애플리케이션 시작...
python app.py

pause
