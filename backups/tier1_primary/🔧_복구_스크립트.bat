@echo off
echo 🚨 FOMS 시스템 복구 스크립트
echo 실행 전 PostgreSQL 서비스가 실행 중인지 확인하세요.
echo.
echo 현재 백업 위치: backups/tier1_primary
echo 데이터베이스 백업 파일: database_backup_20260115_154100.sql
echo.
pause

echo 데이터베이스 복구를 시작합니다...
set PGPASSWORD=lahom

REM 기존 데이터베이스 삭제 (주의: 모든 데이터가 삭제됩니다!)
psql -U postgres -h localhost -c "DROP DATABASE IF EXISTS furniture_orders;" postgres

REM 새 데이터베이스 생성
psql -U postgres -h localhost -c "CREATE DATABASE furniture_orders;" postgres

REM 백업 데이터 복원
psql -U postgres -h localhost -d furniture_orders -f "backups/tier1_primary\database_backup_20260115_154100.sql"

echo 데이터베이스 복구가 완료되었습니다!
echo.
echo 시스템 파일들을 수동으로 복원하려면:
echo 1. system_files 폴더의 내용을 프로젝트 루트로 복사
echo 2. app.py를 재시작
echo.
pause
