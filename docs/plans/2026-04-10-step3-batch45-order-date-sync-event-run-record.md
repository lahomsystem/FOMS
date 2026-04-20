# Step 3 Batch 45 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch44-app-init-run-record.md`

- 일시: 2026-04-10 15:36:22
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: dead-stub 성격의 `order_date_sync_event`를 마흔세 번째 실제 `foms/services` source of truth로 이동하고 legacy shim contract를 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 45 executed, `order_date_sync_event` canonical migration completed as a minimal dead-stub slice without changing runtime behavior**

이유:
- `foms/services/order_date_sync_event.py`를 새 canonical source로 추가하고, 기존 `services/order_date_sync_event.py`는 thin shim으로 전환했다.
- stub의 `pass` 동작은 그대로 유지하면서 persistence/order-date helper import만 canonical namespace로 정렬했다.
- production caller 추가 변경 없이 shim contract, canonical import, `ORDER_DATE_SYNC_EVENT_NS_OK`, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 44 완료 후 자동 전감리 결과:
1. `order_date_sync_event`
2. `storage`
3. `erp_policy`

선정 이유:
- `order_date_sync_event`는 dead-stub 성격이라 구조-only slice로 다루기 가장 쉬웠다.
- 실제 production caller blast radius가 거의 없고, 기존 테스트 표면만으로 shim contract를 검증할 수 있었다.
- `storage`는 singleton/runtime init과 넓은 fan-in 때문에 여전히 dedicated batch가 필요했다.
- `erp_policy`는 `business_calendar` eager import와 광범위 caller 때문에 고위험 유지였다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/order_date_sync_event.py`
  - `sync_order_dates`, `register_order_date_sync_listener()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - `Order` import를 canonical persistence shim 경로로 정리
  - dead-stub `after_flush` listener의 inert behavior 유지

### 3.2 legacy shim 전환
- `services/order_date_sync_event.py`
  - 공개 API(`sync_order_dates`, `register_order_date_sync_listener`)만 재수출하는 thin shim으로 전환

## 4. 테스트 보강
### 4.1 namespace / shim contract
- `tests/test_foms_namespace_imports.py`
  - `namespaced_order_date_sync_event` import 추가
  - `test_legacy_order_date_sync_event_shim_preserves_canonical_contract()` 추가
  - `test_order_date_sync_event_canonical_module_uses_canonical_persistence_import()` 추가
  - 기존 `test_order_date_sync_event_uses_canonical_order_date_sync_import()` 유지

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `order_date_sync_event` 자체는 여전히 dead-stub이며 실제 등록 경로는 `foms/services/app_init.py`에 남아 있다.
  - `storage`와 `erp_policy`는 다음 구조 후보이지만 둘 다 별도 감리/전용 배치가 필요하다.

### 5.2 자동 다음 배치 전감리
- Batch 45 완료 후 자동 전감리 기준 다음 구조 후보는 `storage`를 dedicated batch로 다루는 쪽이 가장 현실적이다.
- 비교 후보:
  - `erp_policy`: `business_calendar` eager import + 광범위 caller로 고위험
  - `business_calendar`: 사용자 지시에 따라 계속 제외

## 6. 의도적으로 건드리지 않은 것
- `order_date_sync_event`의 dead-stub behavior 자체
- 실제 listener 등록 경로(`app_init`)
- `storage`
- `erp_policy` / `business_calendar`
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py -k "order_date_sync_event or order_date_sync or app_init"`
- 결과:
  - `10 passed, 81 deselected`

### 7.2 namespace smoke
- 실행: `python -c "import services.order_date_sync_event as legacy; import foms.services.order_date_sync_event as ns; assert legacy.sync_order_dates is ns.sync_order_dates; assert legacy.register_order_date_sync_listener is ns.register_order_date_sync_listener; print('ORDER_DATE_SYNC_EVENT_NS_OK')"`
- 결과: `ORDER_DATE_SYNC_EVENT_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `383 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `order_date_sync_event`는 마흔세 번째 실제 `foms/services` source of truth가 되었고, dead-stub도 runtime namespace 기준으로 정리됐다.
- 남은 구조 후보는 사실상 `storage`와 `erp_policy` 두 축인데, 이 중 `storage`만 dedicated batch로 접근 가능한 상태다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `storage` dedicated batch
2. `erp_policy`는 `business_calendar` eager import와 광범위 caller 때문에 고위험 유지
3. `business_calendar` / `/calendar` 축은 계속 제외
