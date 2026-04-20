# Step 3 Batch 12 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch11-erp-sync-columns-run-record.md`

- 일시: 2026-04-08 09:31:21
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `business_calendar` 축을 계속 제외한 채, 다음 root service 소형 slice로 `erp_product_items`를 `foms/services` canonical source로 이동하고 caller 3곳만 최소 범위로 canonical import 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 12 executed, `erp_product_items` moved under `foms/services` as the next narrow root service slice**

이유:
- `foms/services/erp_product_items.py`를 열한 번째 canonical service source of truth로 추가했다.
- legacy `services/erp_product_items.py`는 공개 함수 2개만 재수출하는 thin shim으로 전환했다.
- caller 3곳(`apps/erp_drawing_workbench.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_history_page.py`)을 canonical import로 정리했다.
- 새 행위 테스트와 shim 계약 테스트를 추가하고, `ERP_PRODUCT_ITEMS_NS_OK`/`APP_OK`/`verify_result.py --json`/전체 `pytest -q`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `erp_sync_columns` caller cleanup
2. root service slice `erp_product_items`
3. root service slice `channel_quick_actions`

선정 이유:
- `erp_sync_columns` caller cleanup은 import-only 성격이 강하지만, 현재 dirty worktree에서 여러 API/주문 경로를 다시 건드려야 해서 충돌 및 재검증 범위가 컸다.
- `channel_quick_actions`는 DB/스토리지/WAM/권한이 한 모듈에 응축되어 있어 구조-only 배치로 보기 어려웠다.
- `erp_product_items`는 attachment 조회와 URL 조합이라는 도메인 결합은 있지만 caller가 3곳뿐이고, 이미 canonical화된 `erp_display` helper에만 추가 의존한다.
- 따라서 이번 배치는 넓은 caller cleanup보다 더 작은 범위의 새 source of truth 1개를 추가하는 편이 현재 작업 상태에서 더 안전하다고 판단했다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/erp_product_items.py`
  - canonical module 신설
  - `services.erp_display._ensure_dict` 의존을 `foms.services.erp_display._ensure_dict`로 정렬
  - `__all__ = ["build_product_items_for_order", "build_product_items_for_orders"]` 도입

### 3.2 legacy compatibility shim
- `services/erp_product_items.py`
  - 공개 함수 2개만 재수출하는 thin shim으로 전환

### 3.3 caller 정리
- `apps/erp_drawing_workbench.py`
  - `build_product_items_for_order` import를 canonical path로 전환
- `apps/erp_measurement_dashboard.py`
  - `build_product_items_for_orders` import를 canonical path로 전환
- `apps/erp_history_page.py`
  - 함수 내부 delayed import를 canonical path로 전환

### 3.4 테스트 추가/보강
- `tests/test_erp_product_items.py`
  - single-order path의 dimension normalization + attachment mapping 검증
  - batched-order path의 attachment grouping/mapping 검증
  - ID 없는 주문 배열에서 빈 `product_items` 초기화 검증
- `tests/test_foms_namespace_imports.py`
  - legacy shim과 canonical module의 `__all__`/object identity 계약 테스트 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외하기로 유지했다.
- 읽기 전용 감리에서 `erp_product_items`는 caller 3곳과 `OrderAttachment`/URL 조합/JSONB `items|products|product_items` 폴백 계약을 가진 것으로 확인됐다.
- 별도 코드 리뷰 감리에서는 `erp_sync_columns` caller cleanup도 후보였지만, 현재 dirty worktree 겹침이 더 큰 점이 지적됐다.
- 이에 따라 이번 배치는 구조-only 원칙을 유지하면서 source of truth 이동 + thin shim + caller 3곳 import 정리만 수행했다.

### 4.2 사후 감리
- `services/erp_product_items.py`는 private helper를 노출하지 않고 공개 함수 2개만 재수출하는 shim으로 유지됨을 확인했다.
- canonical module은 `foms.services.erp_display`를 직접 참조하도록 정렬돼 `foms/services` 내부 의존 방향이 올바르게 맞춰졌다.
- 새 테스트 작성 중 `spec_width` 같은 원본 키가 유지되는 기존 계약이 확인됐고, 구현 변경 없이 테스트 기대값만 실제 계약에 맞게 조정했다.
- low 수준 residual risk로는 raw item normalization 로직이 single/batch 경로에 중복돼 있다는 점이 남아 있지만, 이번 배치는 구조-only 원칙 때문에 의도적으로 리팩터하지 않았다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/channel_quick_actions.py`
- `services/erp_policy.py`
- staged 상태인 `erp_sync_columns`의 잔여 caller cleanup
- root `db.py`
- root `models.py`
- `templates/`
- `static/`
- `app.py`
- `run.py`

## 6. 검증 결과
### 6.1 caller/import 상태 확인
- 실행: `rg`
- legacy 패턴: `from services\.erp_product_items import|import services\.erp_product_items`
- 결과: production caller 기준 legacy import 없음. `tests/test_foms_namespace_imports.py`의 shim identity import만 잔존
- canonical 패턴: `from foms\.services\.erp_product_items import|import foms\.services\.erp_product_items`
- 결과: `apps/erp_drawing_workbench.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_history_page.py` 확인

### 6.2 namespace smoke
- 실행: `python -c "import services.erp_product_items as legacy; import foms.services.erp_product_items as ns; assert legacy.build_product_items_for_order is ns.build_product_items_for_order; assert legacy.build_product_items_for_orders is ns.build_product_items_for_orders; print('ERP_PRODUCT_ITEMS_NS_OK')"`
- 결과: `ERP_PRODUCT_ITEMS_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_erp_product_items.py tests/test_foms_namespace_imports.py`
- 결과: `16 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `224 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`, `erp_shipment_settings`, `erp_display`, `erp_order_detail`, `db_url_resolver`, `erp_utils`, `erp_sync_columns`, `erp_product_items`까지 총 11개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치는 staged cleanup이 아닌 새로운 소형 root service slice를 다시 하나 추가한 것으로, 넓은 caller cleanup 전에 blast radius를 통제하는 목적에 맞는다.
- 다음 선택지는 `erp_sync_columns` caller cleanup을 이어갈지, `channel_quick_actions`/`erp_policy` 같은 고위험 후보를 다시 감리할지, 또는 별도 품질 배치로 전환할지 세 갈래로 정리된다.

## 8. 다음 단계
1. staged 상태인 `erp_sync_columns`의 남은 caller cleanup을 별도 배치로 이어갈지 판단
2. `channel_quick_actions` 또는 `erp_policy`를 다음 구조 후보로 볼 수 있을지 재감리
3. 별도 품질 배치로 `manager_filter`, `lat/lng`, `erp_shipment_settings` 예외 처리, `orders.py`의 `ensure_path` 중복, `erp_sync_columns` parse fallback 우선순위 재평가
