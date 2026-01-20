## Tools

이 폴더는 운영/배포/점검/마이그레이션용 스크립트를 모아두는 공간입니다.

### 폴더 구조
- `tools/smoke/`: 빠른 스모크 테스트(ERP/대시보드/첨부/자동화 등)

### WDCalculator 마이그레이션(별도 DB → 통합 스키마)
- 스크립트: `tools/migrate_wdcalculator_from_separate_db.py`
- 실행 전 필요:
  - source(예전 별도 DB) 접속 문자열: `WD_SRC_DATABASE_URL`
  - dest(현재 통합 DB) 접속 문자열: `DATABASE_URL`

