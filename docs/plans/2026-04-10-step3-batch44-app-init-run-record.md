# Step 3 Batch 44 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch43-channel-quick-actions-run-record.md`

- 일시: 2026-04-10 15:31:48
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `app_init`을 마흔두 번째 실제 `foms/services` source of truth로 이동하고 cold-start caller를 최소 범위로 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 44 executed, `app_init` canonical migration completed with cold-start blast radius constrained to `app.py` caller binding only**

이유:
- `foms/services/app_init.py`를 새 canonical source로 추가하고, 기존 `services/app_init.py`는 `run_auto_init()`만 재수출하는 thin shim으로 전환했다.
- cold-start caller는 `app.py` 한 곳만 canonical import로 전환해 구조-only 범위를 유지했다.
- canonical module 내부의 main persistence import를 `foms.persistence.main.*` 경로로 정리하고, 기존 `db_indexes`/`order_date_sync` lazy import canonical 경로도 유지했다.
- shim/caller binding, canonical persistence import, `APP_INIT_NS_OK`, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 43 완료 후 자동 전감리 결과:
1. `app_init`
2. `storage`
3. `erp_policy`

선정 이유:
- cold-start 경로이지만 direct production caller가 `app.py` 한 곳뿐이라 blast radius를 통제하기 쉬웠다.
- `storage`는 singleton/runtime init과 넓은 fan-in 때문에 전용 배치가 필요했다.
- `erp_policy`는 `business_calendar` eager import와 광범위 caller 때문에 구조-only slice로 보기 어려웠다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/app_init.py`
  - `_backfill_erp_flat_columns()`, `run_auto_init()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - `get_db`, `init_db`, `User` import를 canonical persistence shim 경로로 정리
  - `db_indexes`, `order_date_sync` lazy import는 canonical 경로 유지

### 3.2 legacy shim 전환
- `services/app_init.py`
  - 공개 entrypoint `run_auto_init()`만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `app.py`
  - WSGI cold-start bootstrap import를 `from foms.services.app_init import run_auto_init`로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_app_init` / `namespaced_app_init` import 추가
  - `test_legacy_app_init_shim_preserves_canonical_contract()` 추가
  - `test_app_uses_canonical_app_init_import()` 추가
  - `test_app_init_canonical_module_uses_canonical_persistence_imports()` 추가
  - 기존 `db_indexes`/`order_date_sync` lazy import 검증은 canonical module 기준으로 유지

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - 기본 관리자 자격 증명 fallback은 여전히 품질/보안 배치로 분리 대상이다.
  - `run_auto_init()`의 print/logging 스타일과 broad exception 처리도 구조 배치 범위 밖으로 유지했다.

### 5.2 자동 다음 배치 전감리
- Batch 44 완료 후 자동 전감리 기준 다음 안전 구조 후보는 `order_date_sync_event`로 정리할 수 있다.
- 비교 후보:
  - `storage`: singleton/runtime init과 넓은 fan-in 때문에 여전히 dedicated batch 필요
  - `erp_policy`: `business_calendar` eager import와 광범위 caller 때문에 고위험 유지

## 6. 의도적으로 건드리지 않은 것
- 기본 관리자 계정 fallback 정책 자체
- `storage` singleton/runtime init
- `erp_policy` / `business_calendar`
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py -k "app_init or db_indexes or order_date_sync"`
- 결과:
  - `9 passed, 80 deselected`

### 7.2 namespace smoke
- 실행: `python -c "import services.app_init as legacy; import foms.services.app_init as ns; assert legacy.run_auto_init is ns.run_auto_init; print('APP_INIT_NS_OK')"`
- 결과: `APP_INIT_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `381 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `app_init`은 마흔두 번째 실제 `foms/services` source of truth가 되었고, `app.py`의 WSGI auto-init binding이 canonical module로 정리됐다.
- cold-start 경로라 범위를 최소화했고, business logic/보안 개선은 분리된 품질 배치로 유지했다.
- 자동 다음 구조 후보는 `order_date_sync_event`로 좁혀졌다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `order_date_sync_event`
2. `storage`는 singleton/runtime fan-in 때문에 계속 dedicated batch
3. `erp_policy`는 `business_calendar` eager import와 광범위 caller 때문에 고위험 후보 유지
