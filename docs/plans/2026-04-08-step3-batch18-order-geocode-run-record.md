# Step 3 Batch 18 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch17-erp-template-filters-run-record.md`

- 일시: 2026-04-08 11:54:14
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `order_geocode`를 열여섯 번째 실제 `foms/services` source of truth로 이동하고 주소/좌표 초기화 helper caller 4곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 18 executed, `order_geocode` canonical migration completed without intended business logic changes**

이유:
- `foms/services/order_geocode.py`를 새 canonical source로 추가하고, 기존 `services/order_geocode.py`는 공개 helper 3개만 재수출하는 thin shim으로 전환했다.
- production caller 4곳(`apps/order_edit.py`, `apps/api/erp_orders_structured.py`, `apps/api/erp_measurement.py`, `apps/api/erp_map.py`)을 canonical import로 정리했고, legacy 경로는 thin shim과 namespace 계약 테스트만 남겼다.
- 주소/좌표/ERP Beta `structured_data.site` 정합 helper이므로 `tests/test_order_geocode.py`를 새로 추가해 빈 주소, `site` 없음, ERP Beta / non-Beta 경로, 좌표 초기화를 고정했다.
- `ORDER_GEOCODE_NS_OK`/`APP_OK`/`verify_result.py --json`/focused `pytest`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `menu_config`
2. `order_storage_cleanup`
3. `order_geocode`
4. 구조 배치 대신 별도 품질 배치

선정 이유:
- 전감리 순수 blast radius만 보면 `menu_config`, `order_storage_cleanup`가 더 가벼웠지만, `order_geocode`는 이미 Batch 5에서 canonicalized 된 `geocode_helpers`와 바로 맞물리는 구조 slice라 Step 3 흐름을 끊지 않고 이어가기 좋았다.
- caller 4곳이 모두 Python code path에 한정되어 있고 템플릿 축이 없어, 테스트를 충분히 묶으면 구조 배치로 통제 가능하다고 판단했다.
- 별도 품질 배치(`services/app_init.py`, `apps/api/erp_orders_structured.py`)는 Auth/API/부트스트랩 경계에 닿는 코어 변경이라 저장소 규칙상 Research→Plan→사용자 승인 흐름이 우선이므로 이번 구조 턴과 분리했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/order_geocode.py`
  - 기존 주소/좌표 초기화 helper 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `apply_erp_beta_site_address_to_sd`
    - `reset_order_geocode_on_address_change`
    - `clear_order_geocode_coords`

### 3.2 legacy shim 전환
- `services/order_geocode.py`
  - 위 3개 공개 helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/order_edit.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_measurement.py`
- `apps/api/erp_map.py`

각 파일에서:
- `from services.order_geocode import ...`
- → `from foms.services.order_geocode import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_order_geocode` / `namespaced_order_geocode` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_order_geocode.py`
  - `apply_erp_beta_site_address_to_sd` 주소 반영/blank address/site 생성 경로
  - `reset_order_geocode_on_address_change`의 ERP Beta / non-Beta 경로
  - `clear_order_geocode_coords` 좌표/상태 초기화 경로

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외했다.
- 구조 후보 비교상 blast radius는 `menu_config`/`order_storage_cleanup`가 더 낮았지만, 사용자가 같은 프로세스로 연속 진행을 요청한 흐름과 `geocode_helpers` 선행 canonicalization을 고려해 `order_geocode`를 선택했다.
- 품질 후보 비교에서는 `services/app_init.py` 기본 관리자 자격 증명/부트스트랩, `apps/api/erp_orders_structured.py` Channel gating 문제가 다시 고우선으로 식별됐지만 코어 변경이므로 별도 승인형 품질 배치로 유지했다.

### 4.2 사후 감리
- 후감리에서 high/medium 수준의 회귀나 구조 정책 위반은 없다는 판정을 받았다.
- low 수준 항목으로 (1) blank address/site 없음/non-Beta 분기 테스트 공백, (2) `geocode_status = "pending"` 매직 문자열 유지, (3) `apps/api/erp_orders_structured.py`의 빈 `new_addr` 조건 분기가 식별됐다.
- 이 중 테스트 공백 3건은 같은 배치 안에서 `tests/test_order_geocode.py`에 보강했고, 매직 문자열/빈 `new_addr` 조건은 기존 동작 유지가 우선인 구조 배치 원칙에 따라 별도 품질 검토 항목으로 남겼다.

## 5. 의도적으로 건드리지 않은 것
- `services/app_init.py`
- `apps/api/erp_orders_structured.py` 내부 Channel gating / 빈 주소 분기 로직
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `app.py`
- `run.py`
- `templates/`
- `static/`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.order_geocode import|import services\.order_geocode`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.order_geocode as legacy; import foms.services.order_geocode as ns; assert legacy.apply_erp_beta_site_address_to_sd is ns.apply_erp_beta_site_address_to_sd; assert legacy.reset_order_geocode_on_address_change is ns.reset_order_geocode_on_address_change; assert legacy.clear_order_geocode_coords is ns.clear_order_geocode_coords; print('ORDER_GEOCODE_NS_OK')"`
- 결과: `ORDER_GEOCODE_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_order_geocode.py tests/test_foms_namespace_imports.py`
- 결과: `24 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest`
- 결과: `250 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `order_geocode`는 열여섯 번째 실제 `foms/services` source of truth가 되었고, 주소 변경 시 geocode reset / ERP Beta site 동기화 helper도 Step 3 canonical namespace 안으로 들어왔다.
- 이번 배치는 주소/좌표/JSONB 정합 helper를 다뤘지만, 변경 범위를 import 정리 + thin shim + helper 계약 테스트로 제한해 business logic 확장은 피했다.
- 별도 품질 배치와 구조 배치의 경계가 더 선명해졌다. 특히 `erp_orders_structured.py`의 빈 주소 처리 조건은 “현재 동작 유지”로 남겼고, 이후 승인형 품질 턴에서 다뤄야 할 항목으로 분리했다.

## 8. 다음 단계
1. 다음 구조 후보는 `menu_config` 또는 `order_storage_cleanup`처럼 더 낮은 blast radius slice를 우선 비교
2. 별도 품질 배치로 `services/app_init.py` 기본 관리자 자격 증명/로깅, `apps/api/erp_orders_structured.py` Channel gating 및 빈 주소 reset 조건을 위한 Spec 초안을 준비
3. `geocode_status` 매직 문자열 상수화 여부는 위 품질/정리 턴에서 함께 검토
