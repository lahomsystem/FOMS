## Tools

§2.2.1 기준: 이 디렉터리는 **하네스·스모크**만 둔다. 운영/백필/DB 마이그레이션 스크립트는 `scripts/ops/`, `scripts/maintenance/`, `scripts/migrations/` 를 사용한다.

### 폴더 구조
- `tools/harness/`: 검증(`verify_result.py`), Codex/gstack 번들, 프로필 등
- `tools/smoke/`: 빠른 스모크 테스트(ERP/대시보드/첨부/자동화 등)
- `tools/drawing_ai/`: 도면 마법사 그림 종류 분류기 다시 가르치기(운영 읽기 전용 · 돌릴 때마다 사용자 허락, 사용법 `tools/drawing_ai/README.md`)

### WDCalculator 마이그레이션(별도 DB → 통합 스키마)
- 스크립트: `scripts/migrations/migrate_wdcalculator_from_separate_db.py`
- 실행 전 필요:
  - source(예전 별도 DB) 접속 문자열: `WD_SRC_DATABASE_URL`
  - dest(현재 통합 DB) 접속 문자열: `DATABASE_URL`

