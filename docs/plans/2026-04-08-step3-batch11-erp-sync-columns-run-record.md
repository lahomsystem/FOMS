# Step 3 Batch 11 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch10-utility-slices-run-record.md`

- 일시: 2026-04-08 09:17:23
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `business_calendar` 축을 계속 제외한 채, 다음 root service 소형 slice로 `erp_sync_columns`를 `foms/services` canonical source로 이동하되 caller 폭이 넓은 점을 감안해 staged 방식으로 thin shim과 최소 caller 정리만 수행한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 11 executed, `erp_sync_columns` moved under `foms/services` as a staged slice with thin legacy shim**

이유:
- `foms/services/erp_sync_columns.py`를 열 번째 canonical service source of truth로 추가했다.
- legacy `services/erp_sync_columns.py`는 공개 함수 `sync_erp_flat_columns`만 재수출하는 thin shim으로 전환했다.
- caller가 넓은 모듈이라는 감리 결과에 따라, production/runtime caller 전면 정리 대신 `scripts/migrations/backfill_erp_flat_columns.py` 1곳만 canonical import로 정리하는 staged 배치로 마감했다.
- 새 행위 테스트와 shim 계약 테스트를 추가하고, `ERP_SYNC_COLUMNS_NS_OK`/`APP_OK`/`verify_result.py --json`/전체 `pytest -q`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. root service slice `erp_sync_columns`
2. root service slice `erp_product_items`
3. root service slice `channel_quick_actions`

선정 이유:
- `erp_product_items`는 caller 수는 적지만 attachment 조회, URL 조합, JSONB 표시 계약이 함께 묶여 있어 구조-only 배치로 보기 어려웠다.
- `channel_quick_actions`는 DB/스토리지/WAM/권한/ERP 표시 규칙이 한 모듈에 응축되어 통합 리스크가 컸다.
- `erp_sync_columns`는 caller는 넓지만 모듈 자체는 작고 공개 API가 1개뿐이며, 이미 canonical화된 `erp_display`에만 의존한다.
- 다만 전용 테스트가 없고 caller 폭이 넓다는 감리 결과에 따라, 이번 배치는 source of truth 이동 + thin shim + 최소 caller 1곳만 canonical path로 맞추는 staged 방식으로 축소했다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/erp_sync_columns.py`
  - canonical module 신설
  - `services.erp_display` 의존을 `foms.services.erp_display` 경로로 정렬
  - `__all__ = ["sync_erp_flat_columns"]` 도입

### 3.2 legacy compatibility shim
- `services/erp_sync_columns.py`
  - 공개 함수 `sync_erp_flat_columns`만 재수출하는 thin shim으로 전환

### 3.3 staged caller 정리
- `scripts/migrations/backfill_erp_flat_columns.py`
  - `from services.erp_sync_columns ...` → `from foms.services.erp_sync_columns ...`

### 3.4 테스트 추가/보강
- `tests/test_erp_sync_columns.py`
  - non-ERP Beta 주문일 때 early-return 유지
  - ERP Beta 주문에서 manager/date/stage/urgent/stage_updated_at/owner_team flat column 동기화 검증
- `tests/test_foms_namespace_imports.py`
  - legacy shim과 canonical module의 `__all__`/object identity 계약 테스트 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서 계속 제외하기로 유지했다.
- 읽기 전용 감리에서 `erp_sync_columns`의 실코드 caller 12개(api 9, order_pages 1, services/app_init 1, script 1)와 전용 테스트 부재가 확인되었다.
- 코드 리뷰 감리에서는 “진행 가능하되, thin shim 유지와 shim 동일성 테스트 추가를 전제로 조건부 proceed” 판정이 내려졌다.
- 이에 따라 전체 caller 정리 대신 source of truth 이동과 최소 script caller 1곳 정리만 수행하는 staged 배치로 결정했다.

### 4.2 사후 감리
- `services/erp_sync_columns.py`는 private helper를 새로 노출하지 않고 공개 함수만 재수출하는 shim으로 유지됨을 확인했다.
- canonical module은 `foms.services.erp_display`를 직접 참조하도록 정렬돼 `foms/services` 내부 의존 방향이 올바르게 맞춰졌다.
- low 수준 residual risk로는 `stage_updated_at` 파싱 실패 시 기존처럼 `pass`하는 품질 부채와, 앱 전역에 남아 있는 legacy caller 11곳이 있다. 이번 배치는 구조-only/staged 배치라 의도적으로 건드리지 않았다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `apps/api/orders.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_measurement.py`
- `apps/api/erp_orders_as.py`
- `apps/api/erp_orders_production.py`
- `apps/api/erp_orders_cs.py`
- `apps/api/erp_orders_draftsman.py`
- `apps/api/erp_orders_construction.py`
- `apps/api/quest.py`
- `apps/order_pages.py`
- `services/app_init.py`
- `services/erp_policy.py`
- `services/erp_product_items.py`
- `services/channel_quick_actions.py`
- root `db.py`
- root `models.py`
- `templates/`
- `static/`
- `app.py`
- `run.py`

## 6. 검증 결과
### 6.1 staged caller 상태 확인
- 실행: `rg`
- legacy 패턴: `from services\.erp_sync_columns import|import services\.erp_sync_columns`
- 결과: `apps/*`, `services/app_init.py`, `tests/test_foms_namespace_imports.py` 등 staged 잔여 caller가 의도대로 남아 있음
- canonical 패턴: `from foms\.services\.erp_sync_columns import|import foms\.services\.erp_sync_columns`
- 결과: `scripts/migrations/backfill_erp_flat_columns.py` 1곳 확인

### 6.2 namespace smoke
- 실행: `python -c "from services.erp_sync_columns import sync_erp_flat_columns as legacy_sync; from foms.services.erp_sync_columns import sync_erp_flat_columns as namespaced_sync; assert legacy_sync is namespaced_sync; print('ERP_SYNC_COLUMNS_NS_OK')"`
- 결과: `ERP_SYNC_COLUMNS_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_erp_sync_columns.py tests/test_foms_namespace_imports.py`
- 결과: `14 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `220 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`, `erp_shipment_settings`, `erp_display`, `erp_order_detail`, `db_url_resolver`, `erp_utils`, `erp_sync_columns`까지 총 10개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치는 utility slice 다음에 다시 root service slice로 복귀했지만, caller 폭을 이유로 `erp_display` 때와 유사한 staged 방식을 재사용했다는 점에서 구조 거버넌스와 정합적이다.
- 다음 선택지는 `erp_sync_columns`의 caller cleanup을 이어갈지, 아니면 새로운 소형 slice(`erp_product_items`)로 넘어갈지, 또는 품질 배치로 전환할지 세 갈래로 정리된다.

## 8. 다음 단계
1. `erp_sync_columns` staged caller cleanup을 별도 배치로 이어갈지 판단
2. 또는 다음 root service 후보(`erp_product_items`, `channel_quick_actions`)를 다시 비교
3. 별도 품질 배치로 `manager_filter`, `lat/lng`, `erp_shipment_settings` 예외 처리, `orders.py`의 `ensure_path` 중복, `erp_sync_columns`의 조용한 parse fallback 우선순위 재평가
