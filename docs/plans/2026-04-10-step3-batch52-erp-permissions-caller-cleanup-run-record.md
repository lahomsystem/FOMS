# Step 3 Batch 52 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch51-erp-display-caller-cleanup-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Batch 42에서 canonical source로 고정된 `erp_permissions`의 남은 live caller를 `foms.services.erp_permissions` 경로로 정리해 production 앱 경로의 legacy `services.erp_permissions` import를 제거한다

## 1. 전체 판정
**Verdict: Step 3 Batch 52 executed, `erp_permissions` caller cleanup completed**

이유:
- `erp_permissions` 본체와 thin shim 계약은 이미 Batch 42에서 안정화되어 있어 이번 배치는 caller import cleanup에만 집중할 수 있었다.
- `apps/*` 및 `apps/api/*`에 남아 있던 live `services.erp_permissions` import를 모두 `foms.services.erp_permissions`로 정리했다.
- top-level import뿐 아니라 `erp_dashboard`의 lazy `build_mine_sql_filter` source-path까지 canonical path로 검증했다.
- 사용자 지시대로 삭제 예정 `business_calendar`/`/calendar` 축은 이번 범위에서 제외했다.

## 2. 사전 감리 요약
- Batch 42 run record와 shim 계약 테스트를 기준으로 `erp_permissions`는 canonical source + thin shim 구조가 이미 고정되어 있음을 재확인했다.
- 위험 요소는 권한 로직 변경이 아니라 app/API caller 폭과 lazy import 1건(`erp_dashboard`)뿐이었다.
- 따라서 service 본체와 권한 로직은 건드리지 않고 caller cleanup만 수행하는 범위 제한형 GO로 판정했다.

## 3. 실제 변경 범위
### 3.1 caller cleanup
- `apps/erp.py`
- `apps/erp_as_page.py`
- `apps/erp_construction_page.py`
- `apps/erp_dashboard.py`
- `apps/erp_drawing_workbench.py`
- `apps/erp_measurement_dashboard.py`
- `apps/erp_production_page.py`
- `apps/erp_shipment_page.py`
- `apps/order_edit.py`
- `apps/api/erp_map.py`
- `apps/api/erp_measurement.py`
- `apps/api/erp_orders_as.py`
- `apps/api/erp_orders_confirm.py`
- `apps/api/erp_orders_construction.py`
- `apps/api/erp_orders_cs.py`
- `apps/api/erp_orders_draftsman.py`
- `apps/api/erp_orders_drawing.py`
- `apps/api/erp_orders_production.py`
- `apps/api/erp_orders_revision.py`
- `apps/api/erp_shipment_settings.py`
- `apps/api/orders.py`
- `apps/api/quest.py`

### 3.2 테스트 보강
- `tests/test_foms_namespace_imports.py`

## 4. 변경 상세
- page/API caller의 top-level import를 `from foms.services.erp_permissions import ...`로 정렬했다.
- `apps/erp_dashboard.py`의 lazy `build_mine_sql_filter` import도 canonical path로 전환했다.
- `tests/test_foms_namespace_imports.py`에 page/API binding 테스트와 lazy import source-path 테스트를 추가했다.
- `apps/` 경로에서 `services.erp_permissions` live import가 0건임을 ripgrep로 확인했다.

## 5. 의도적으로 건드리지 않은 것
- `foms/services/erp_permissions.py` 본체 로직
- `services/erp_permissions.py` thin shim 계약
- `services.business_calendar.py`
- `/calendar` 관련 기능 축
- `as_content_safety`, `channel_delivery` 등 다른 legacy caller 축

## 6. 검증 결과
### 6.1 live import audit
- 실행: `rg "\bfrom services\.erp_permissions import|\bimport services\.erp_permissions\b" apps`
- 결과: no matches

### 6.2 caller smoke
- 실행: `python -c "... print('ERP_PERMISSIONS_CALLERS_NS_OK')"`
- 결과: `ERP_PERMISSIONS_CALLERS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_foms_namespace_imports.py -q`
- 결과: `129 passed`

### 6.4 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `421 passed, 3 warnings`
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
- Batch 42에서 canonical source로 만든 `erp_permissions`의 production caller cleanup이 이번 배치로 닫혔다.
- production 앱 경로 기준 `services.erp_permissions` live import는 제거됐고, legacy shim은 tests/compat 목적에만 남는다.
- 권한 로직 변경 없이 import 경로만 정리했기 때문에 저위험 구조 정렬 배치로 유지됐다.

## 8. 다음 단계
1. 다음 자동 후보로 `services.channel_delivery` live caller cleanup을 전감리한다.
2. `business_calendar`/`/calendar` 축은 사용자 지시대로 계속 migration scope 밖에 둔다.
3. `services.as_content_safety` 단일 caller(`apps/erp_as_page.py`)는 `channel_delivery` 정리 후 저비용 후속 배치로 검토한다.
