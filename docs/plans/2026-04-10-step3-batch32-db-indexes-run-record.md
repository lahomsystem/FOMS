# Step 3 Batch 32 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch31-user-deletion-run-record.md`

- 일시: 2026-04-10 11:11:00
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `db_indexes`를 서른 번째 실제 `foms/services` source of truth로 이동하고 startup caller 1곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 32 executed, `db_indexes` canonical migration completed without changing startup DDL helper behavior**

이유:
- `foms/services/db_indexes.py`를 새 canonical source로 추가하고, 기존 `services/db_indexes.py`는 thin shim으로 전환했다.
- 실 caller인 `services/app_init.py`의 lazy import를 canonical path로 정리했다.
- 신규 단위 테스트로 trigram/partial index helper의 commit/rollback 분기와 ERP flat column helper의 warning path를 고정했다.
- 후감리에서 batch-introduced 회귀는 발견되지 않았고 `DB_INDEXES_NS_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 선정 근거
Batch 31 완료 후 자동 전감리 결과:
1. `db_indexes`
2. `estimate_service`
3. `order_attachment_thumbnail`

선정 이유:
- `db_indexes`는 import-time side effect가 없고, 실 caller가 `services/app_init.py` 한 곳뿐이었다.
- DDL 자체는 고위험이지만 이번 배치는 "언제 실행되는지"를 바꾸지 않는 structure-only 이동으로 한정할 수 있었다.
- thin shim + lazy import source string 검증으로 compatibility를 고정하기 쉬웠다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/db_indexes.py`
  - 기존 startup DDL helper 구현을 canonical 위치로 이동
  - module docstring, `__all__`, 타입 힌트 추가
  - 기존 의미론 유지:
    - `pg_trgm` extension 확인 후 trigram index 생성
    - `order_schedule_dates` partial index 생성
    - ERP flat column/secondary index 보장
    - block 단위 commit / rollback / warning 흐름 유지

### 3.2 legacy shim 전환
- `services/db_indexes.py`
  - `apply_phase2_indexes`, `ensure_erp_date_columns`를 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `services/app_init.py`
  - `run_auto_init()` 내부 lazy import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_db_indexes` / `namespaced_db_indexes` import 추가
  - `test_legacy_db_indexes_shim_preserves_canonical_contract()` 추가
  - `test_app_init_uses_canonical_db_indexes_lazy_import()` 추가

### 4.2 focused behavior verification
- `tests/test_db_indexes.py`
  - `test_apply_phase2_indexes_executes_expected_sql_and_commits()` 추가
  - `test_apply_phase2_indexes_rolls_back_failed_trigram_block_and_continues()` 추가
  - `test_ensure_erp_date_columns_executes_expected_sql_and_commits()` 추가
  - `test_ensure_erp_date_columns_rolls_back_and_logs_warning_on_error()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `app_init.run_auto_init()` 검증이 source string 부분 문자열에 의존해 줄바꿈/포매팅에 다소 취약함
  - `apply_phase2_indexes()`는 기존 구조 이전 기준으로도 함수 길이가 긴 편이지만 신규 논리 버그는 아님

### 5.2 residual gap
- `run_auto_init()` 전체 startup path를 실제 DB와 함께 기동하는 통합 테스트는 이번 배치에서 추가하지 않았다.
- `ensure_erp_date_columns()` warning path는 `exc_info=True` 없이 유지되며, 이는 기존 구현 의미를 그대로 보존한 것이다.

## 6. 의도적으로 건드리지 않은 것
- startup auto-init 시점
- 실제 DDL 목록/정책
- `app_init`의 기본 관리자 생성/print 로깅 문제
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_db_indexes.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `53 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.db_indexes, foms.services.db_indexes; print('DB_INDEXES_NS_OK')"`
- 결과: `DB_INDEXES_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `313 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `db_indexes`는 서른 번째 실제 `foms/services` source of truth가 되었고, startup DDL helper caller 정리가 완료됐다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `estimate_service`다.
- 그 다음 비교 후보는 `channel_client`, `order_attachment_thumbnail` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `estimate_service`
2. 그 다음 비교 후보는 `channel_client`
3. `order_attachment_thumbnail`는 import-time thread pool / storage 결합 때문에 그 다음 비교 후보로 유지
