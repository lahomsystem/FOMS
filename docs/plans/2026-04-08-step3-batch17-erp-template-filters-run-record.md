# Step 3 Batch 17 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch16-order-display-utils-run-record.md`

- 일시: 2026-04-08 11:18:28
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `erp_template_filters`를 열다섯 번째 실제 `foms/services` source of truth로 이동하고 ERP blueprint/출고 page caller를 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 17 executed, `erp_template_filters` canonical migration completed without intended business logic changes**

이유:
- `foms/services/erp_template_filters.py`를 새 canonical source로 추가하고, 기존 `services/erp_template_filters.py`는 공개 helper 11개만 재수출하는 thin shim으로 전환했다.
- production caller 2곳을 canonical import로 정리했고, legacy 경로는 thin shim 자체와 namespace 계약 테스트만 남겼다.
- 템플릿 필터는 Jinja 계약이 넓기 때문에 `tests/test_erp_template_filters.py`를 추가해 핵심 helper 함수와 Blueprint 필터 등록을 고정했다.
- 초기 focused 검증 중 shim 파일에 legacy 본문이 뒤에 남아 동일성 검증이 깨지는 drift가 발견됐고, 같은 배치 안에서 thin shim만 남도록 정리한 뒤 `ERP_TEMPLATE_FILTERS_NS_OK`를 재통과했다.
- 후감리 low 항목 중 무해한 테스트 공백(`item_spec_w300_display(spec_rows)`, 필터 등록 키 존재)도 같은 배치 안에서 보강했다.
- `ERP_TEMPLATE_FILTERS_NS_OK`/`APP_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `erp_template_filters`
2. `order_geocode`
3. 구조 배치 대신 별도 품질 배치

선정 이유:
- 전감리에서 `erp_template_filters`는 Python caller 2곳으로 좁고, 순수 helper + Blueprint filter 등록이라는 구조 패턴이 이미 잘 드러나는 slice로 판정됐다.
- `order_geocode`는 caller 4곳/템플릿 0으로 구조상 후보가 될 수 있었지만, 주소/lat/lng/JSONB 정합에 직접 연결되어 데이터 회귀 비용이 더 컸다.
- 별도 품질 배치(`services/app_init.py`, `apps/api/erp_orders_structured.py`)는 Auth/API/부트스트랩 경계와 겹쳐 저장소 규칙상 Research→Plan→사용자 승인 흐름이 우선이라 이번 Step 3 구조 턴과 분리했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/erp_template_filters.py`
  - 기존 필터/helper 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `split_count_filter`
    - `split_list_filter`
    - `strip_product_w_filter`
    - `spec_w300_filter`
    - `format_phone_filter`
    - `spec_w300_value`
    - `item_spec_w300_display`
    - `item_spec_w300_value`
    - `schedule_datetime_display`
    - `payment_confirmed_bool`
    - `register_erp_template_filters`

### 3.2 legacy shim 전환
- `services/erp_template_filters.py`
  - 위 11개 공개 helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/erp.py`
- `apps/erp_shipment_page.py`

각 파일에서:
- `from services.erp_template_filters import ...`
- → `from foms.services.erp_template_filters import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_erp_template_filters` / `namespaced_erp_template_filters` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_erp_template_filters.py`
  - 문자열 split/strip helper
  - phone/payment helper
  - `spec_w300_filter`
  - `item_spec_w300_display` / `item_spec_w300_value`의 `spec_rows` 합산
  - `register_erp_template_filters` Blueprint 등록 및 Jinja filter key 존재 검증

### 3.5 배치 중 수정된 drift
- 첫 focused 검증에서 `services/erp_template_filters.py`가 thin shim 뒤에 legacy 본문이 잔존해 canonical 동일성 테스트가 실패했다.
- 해당 파일을 다시 정리해 thin shim만 남기고 동일성 smoke/test를 재통과시켰다.

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외했다.
- 구조 후보 비교에서는 `erp_template_filters`가 1순위, `order_geocode`가 2순위로 정리됐다.
- 품질 후보 비교에서는 `services/app_init.py` 기본 관리자 자격 증명/부트스트랩, `apps/api/erp_orders_structured.py` Channel gating 문제가 고우선으로 식별됐지만, 두 파일 모두 코어 Auth/API 경계에 닿아 별도 승인형 품질 배치로 분리해야 한다는 판정을 받았다.
- 따라서 이번 배치는 `erp_template_filters` canonical 이동 + shim + caller import 정리 + 필터 계약 테스트 보강까지로 scope를 고정했다.

### 4.2 사후 감리
- 후감리에서 치명적 회귀나 구조 정책 위반은 없다는 판정을 받았다.
- low 수준 항목으로 `apps/erp.py`의 `spec_w300_value` 불용 import, `item_spec_w300_display(spec_rows)` 테스트 공백, 신규 canonical 파일의 타입 힌트 미보강이 식별됐다.
- 이 중 테스트 공백 2건은 이번 배치 안에서 보강했고, `apps/erp.py` 불용 import와 타입 힌트 보강은 별도 품질/정리 후보로 남겼다.

## 5. 의도적으로 건드리지 않은 것
- `services/app_init.py`
- `apps/api/erp_orders_structured.py`
- `services/order_geocode.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `apps/erp.py`의 `spec_w300_value` re-export/noqa 정리
- `services/erp_policy.py`
- `app.py`
- `run.py`
- `templates/`
- `static/`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.erp_template_filters import|import services\.erp_template_filters`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.erp_template_filters as legacy; import foms.services.erp_template_filters as ns; assert legacy.split_count_filter is ns.split_count_filter; assert legacy.register_erp_template_filters is ns.register_erp_template_filters; print('ERP_TEMPLATE_FILTERS_NS_OK')"`
- 결과: `ERP_TEMPLATE_FILTERS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_erp_template_filters.py tests/test_foms_namespace_imports.py`
- 결과: `22 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest`
- 결과: `243 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `erp_template_filters`는 열다섯 번째 실제 `foms/services` source of truth가 되었고, ERP 템플릿 필터 계약도 Step 3 canonical namespace 안으로 들어왔다.
- 이번 배치는 `apps/erp.py`와 `apps/erp_shipment_page.py`처럼 ERP 핵심 caller를 건드렸지만, 변경 범위를 import 정리와 filter 계약 테스트 보강으로 통제했다.
- 구조 배치와 별도로, `app_init.py`/`erp_orders_structured.py` 품질 수정은 이제 “필요하지만 승인형 코어 변경”으로 명확히 분리되었다.

## 8. 다음 단계
1. 구조 후보는 `order_geocode`와 다른 low-risk slice를 다시 비교
2. 별도 품질 배치로 `services/app_init.py` 기본 관리자 자격 증명/로깅, `apps/api/erp_orders_structured.py` Channel gating 및 대형 handler 분해를 위한 Spec 초안을 준비
3. `apps/erp.py`의 `spec_w300_value` 불용 import/noqa 정리와 `foms/services/erp_template_filters.py` 타입 힌트 보강은 위 품질/정리 턴에서 함께 검토
