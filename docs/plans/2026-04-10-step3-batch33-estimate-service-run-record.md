# Step 3 Batch 33 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch32-db-indexes-run-record.md`

- 일시: 2026-04-10 11:19:51
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `estimate_service`를 서른한 번째 실제 `foms/services` source of truth로 이동하고 estimate API caller 1곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 33 executed, `estimate_service` canonical migration completed without changing estimate generation/update behavior**

이유:
- `foms/services/estimate_service.py`를 새 canonical source로 추가하고, 기존 `services/estimate_service.py`는 thin shim으로 전환했다.
- 실 caller인 `apps/api/erp_estimates.py`의 helper import를 canonical path로 정리했다.
- 신규 단위 테스트로 번호 채번, structured_data 추출, create override / payment_info deepcopy, update balance 재계산과 `flag_modified` 경로를 고정했다.
- 후감리에서 batch-introduced 회귀는 발견되지 않았고 `ESTIMATE_SERVICE_NS_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 선정 근거
Batch 32 완료 후 자동 전감리 결과:
1. `estimate_service`
2. `channel_client`
3. `order_attachment_thumbnail`

선정 이유:
- `estimate_service`는 실 caller가 `apps/api/erp_estimates.py` 한 곳뿐인 가장 조용한 leaf helper였다.
- import-time thread / storage / Flask session / SQLAlchemy event listener가 없어서 structure-only 이동 리스크가 낮았다.
- public helper 경계(`generate_estimate_number`, `extract_estimate_data_from_order`, `create_estimate`, `update_estimate`)가 뚜렷해 shim/API 계약 테스트를 고정하기 쉬웠다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/estimate_service.py`
  - 기존 견적서 helper 구현을 canonical 위치로 이동
  - module docstring, `__all__`, 타입 힌트 추가
  - 기존 의미론 유지:
    - 날짜별 견적번호 채번
    - `structured_data`에서 customer/site/manager/item/payment 추출
    - override_data 적용 시 total/balance 재계산
    - `payment_info` deepcopy 유지
    - `update_estimate()`에서 `items` 변경 시 `flag_modified` 호출 유지

### 3.2 legacy shim 전환
- `services/estimate_service.py`
  - `generate_estimate_number`, `extract_estimate_data_from_order`, `create_estimate`, `update_estimate`를 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/erp_estimates.py`
  - top-level estimate helper import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_estimate_service` / `namespaced_estimate_service` import 추가
  - `test_legacy_estimate_service_shim_preserves_canonical_contract()` 추가
  - `test_erp_estimates_api_uses_canonical_estimate_service_imports()` 추가

### 4.2 focused behavior verification
- `tests/test_estimate_service.py`
  - `test_generate_estimate_number_skips_invalid_suffixes_and_increments_max()` 추가
  - `test_extract_estimate_data_from_order_formats_spec_rows_and_payments()` 추가
  - `test_create_estimate_applies_overrides_and_uses_deep_copied_payment_info()` 추가
  - `test_update_estimate_recalculates_totals_and_marks_items_modified()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `extract_estimate_data_from_order()` / `create_estimate()`는 기존 구조 이전 기준으로도 함수 길이가 긴 편
  - focused test가 "해당 일자 첫 견적번호", `payments` only, non-dict item skip 같은 엣지를 모두 덮지는 않음

### 5.2 residual gap
- 견적 생성/수정 API의 실 DB / 세션 기반 통합 smoke는 이번 배치에서 추가하지 않았다.
- override_data에서 `items`와 `total_amount`를 동시에 넣었을 때 합계 불일치가 허용되는 기존 동작은 그대로 유지했다.

## 6. 의도적으로 건드리지 않은 것
- estimate business rule 자체
- API error handling / status policy
- override_data validation 강화
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_estimate_service.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `55 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.estimate_service, foms.services.estimate_service; print('ESTIMATE_SERVICE_NS_OK')"`
- 결과: `ESTIMATE_SERVICE_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `319 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `estimate_service`는 서른한 번째 실제 `foms/services` source of truth가 되었고, estimate API helper caller 정리가 완료됐다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `channel_client`다.
- 그 다음 비교 후보는 `order_attachment_thumbnail`, `order_date_sync` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_client`
2. 그 다음 비교 후보는 `order_attachment_thumbnail`
3. `order_date_sync`는 SQLAlchemy listener 등록 결합 때문에 그 다음 비교 후보로 유지
