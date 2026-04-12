# Step 3 Batch 51 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch50-jobs-caller-cleanup-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: staged 상태로 남아 있던 `erp_display` live caller를 canonical `foms.services.erp_display` 경로로 정리해 legacy `services.erp_display` import를 production 앱 경로에서 제거한다

## 1. 전체 판정
**Verdict: Step 3 Batch 51 executed, `erp_display` caller cleanup completed**

이유:
- `erp_display` 자체는 이미 Batch 7에서 canonical source + thin shim 구조가 고정되어 있었고, 이번 배치는 호출부 import 정리에만 집중했다.
- `apps/*` 및 `apps/api/*`에 남아 있던 live `services.erp_display` import를 모두 `foms.services.erp_display`로 정리했다.
- private helper(`_ensure_dict`, `_erp_get_stage`)와 lazy import(`clean_dict_like_name`, `self_measurement_four_checks_done`)까지 포함해 caller binding 테스트를 보강했다.
- 사용자 지시대로 삭제 예정 `business_calendar`/`/calendar` 축은 이번 범위에서 제외하고 caller cleanup만 수행했다.

## 2. 사전 감리 요약
- 기존 Batch 7 run record를 기준으로 `erp_display`는 이미 canonical source가 존재하고 shim 계약도 안정적임을 재확인했다.
- 위험 요소는 service 본체가 아니라 호출부 폭(`apps/*`, `apps/api/*`)과 lazy import/private helper 사용이었다.
- 따라서 이번 배치는 `erp_display` 본체와 `services.business_calendar` 의존은 건드리지 않고, caller cleanup만 수행하는 범위 제한형 GO로 판정했다.

## 3. 실제 변경 범위
### 3.1 caller cleanup
- `apps/erp.py`
- `apps/erp_as_page.py`
- `apps/erp_construction_page.py`
- `apps/erp_dashboard.py`
- `apps/erp_drawing_workbench.py`
- `apps/erp_history_page.py`
- `apps/erp_measurement_dashboard.py`
- `apps/erp_production_page.py`
- `apps/erp_shipment_page.py`
- `apps/order_edit.py`
- `apps/order_trash.py`
- `apps/api/erp_map.py`
- `apps/api/erp_measurement.py`
- `apps/api/erp_orders_as.py`
- `apps/api/erp_orders_completion.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/orders.py`
- `apps/api/personal_board.py`

### 3.2 테스트 보강
- `tests/test_foms_namespace_imports.py`

## 4. 변경 상세
- top-level import caller를 `from foms.services.erp_display import ...`로 정렬했다.
- `erp_history_page`, `personal_board`, `erp_map`, `erp_measurement`, `orders`의 lazy import도 canonical path로 정리했다.
- `tests/test_foms_namespace_imports.py`에 page/API binding 테스트와 lazy import source-path 테스트를 추가했다.
- `apps/` 경로에서 `services.erp_display` live import가 0건임을 ripgrep로 확인했다.

## 5. 의도적으로 건드리지 않은 것
- `foms/services/erp_display.py` 본체 로직
- `services/erp_display.py` thin shim 계약
- `services.business_calendar.py`
- `/calendar` 관련 기능 축
- `erp_display`와 무관한 다른 legacy caller 축 (`erp_permissions`, `business_calendar` 등)

## 6. 검증 결과
### 6.1 live import audit
- 실행: `rg "\bfrom services\.erp_display import|\bimport services\.erp_display\b" apps`
- 결과: no matches

### 6.2 caller smoke
- 실행: `python -c "... print('ERP_DISPLAY_CALLERS_NS_OK')"`
- 결과: `ERP_DISPLAY_CALLERS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_foms_namespace_imports.py tests/test_erp_display.py -q`
- 결과: `129 passed`

### 6.4 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `418 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.5 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.6 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Batch 7에서 staged로 남겨 두었던 `erp_display` caller cleanup이 이번 배치로 닫혔다.
- production 앱 경로 기준 `services.erp_display` live import는 제거됐고, legacy shim은 tests/compat 목적에만 남는다.
- 삭제 예정 `business_calendar` 축을 일부러 건드리지 않았기 때문에, 이번 배치는 구조 정렬 효과를 얻으면서도 삭제 범위와 충돌하지 않았다.

## 8. 다음 단계
1. 다음 자동 후보로 `services.erp_permissions` live caller cleanup을 전감리한다.
2. `business_calendar`/`/calendar` 축은 사용자 지시대로 계속 migration scope 밖에 둔다.
3. 별도 품질 배치가 필요하면 `erp_display` 본체가 아니라 `orders.py`, `erp_orders_structured.py`, `app_init.py` 같은 대형 핫스팟을 승인형 코어 변경으로 분리한다.
