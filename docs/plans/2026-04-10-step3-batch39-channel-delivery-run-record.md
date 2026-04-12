# Step 3 Batch 39 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch38-channel-dispatch-run-record.md`

- 일시: 2026-04-10 13:18:53
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_delivery`를 서른일곱 번째 실제 `foms/services` source of truth로 이동하고 channel admin/queue caller import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 39 executed, `channel_delivery` canonical migration completed without changing ChannelTalk outbox/delivery behavior**

이유:
- `foms/services/channel_delivery.py`를 새 canonical source로 추가하고, 기존 `services/channel_delivery.py`는 thin shim으로 전환했다.
- `foms/services/channel_dispatch.py`, `apps/api/channel_integration.py`, `services/jobs/queue.py`가 delivery helper를 canonical path에서 바라보도록 정리했다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 38 완료 후 자동 전감리 결과:
1. `channel_delivery`
2. `erp_permissions`
3. `channel_inbound`

선정 이유:
- `channel_client`/`channel_policy`/`channel_dispatch`가 이미 canonicalized된 상태라 delivery layer까지 이어서 정리하면 channel stack의 outbound 경로를 한 단계 더 닫을 수 있었다.
- 실제 production caller를 작은 슬라이스로 제한할 수 있었다. 이번 배치에서는 `channel_dispatch`, `channel_integration`, queue lazy import만 canonical import로 전환하고, ERP 쪽 lazy import는 의도적으로 shim에 남겨 blast radius를 줄였다.
- module 자체가 outbox/status/metrics helper 중심이라 structure-only 원칙을 유지하면서 shim/contract 테스트를 추가하기 적합했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_delivery.py`
  - `create_pending_delivery()`, `mark_delivery_status()`, `mark_api_failed()`, `mark_api_rejected()`, `mark_token_rate_limited()`, `get_delivery_metrics()`, `get_queue_backlog()`, `check_legacy_only_success_after_cutover()`, `mark_order_updated_for_channel()`, `mask_payload()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - 기존 의미론 유지:
    - pending outbox row 생성 + `channel_source_seq` 기반 event key 유지
    - status transition/message id/sent timestamp 갱신 유지
    - backlog/metrics/drift 계산 로직 유지
    - presigned URL masking 유지

### 3.2 legacy shim 전환
- `services/channel_delivery.py`
  - 공개 delivery helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `foms/services/channel_dispatch.py`
  - `dispatch_channel_push()` 내부 delivery lazy import를 canonical path로 전환
- `apps/api/channel_integration.py`
  - health/admin API가 `get_delivery_metrics()`, `get_queue_backlog()`, `check_legacy_only_success_after_cutover()`를 canonical path에서 import하도록 정리
- `services/jobs/queue.py`
  - queue unavailable / enqueue failed 분기에서 `mark_delivery_status()` lazy import를 canonical path로 전환
- `tests/test_channel_integration_smoke.py`
  - `mark_order_updated_for_channel()` import를 canonical path로 전환
- `tests/test_channel_push_messages.py`
  - `mark_order_updated_for_channel()` import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_delivery` / `namespaced_channel_delivery` import 추가
  - `test_legacy_channel_delivery_shim_preserves_canonical_contract()` 추가
  - `test_channel_dispatch_canonical_module_uses_canonical_channel_delivery_lazy_imports()` 추가
  - `test_channel_delivery_canonical_module_uses_canonical_channel_policy_lazy_import()` 추가
  - `test_channel_integration_uses_canonical_channel_delivery_imports()` 추가
  - `test_queue_uses_canonical_channel_delivery_lazy_imports()` 추가

### 4.2 focused behavior verification
- `tests/test_channel_delivery.py`
  - `test_create_pending_delivery_uses_policy_group_and_flushes()` 추가
  - `test_mark_delivery_status_updates_message_and_sent_timestamp()` 추가
  - `test_mask_payload_redacts_urls_without_mutating_input()` 추가
- `tests/test_channel_integration_smoke.py`
  - channel delivery smoke 경로가 canonical 모듈을 직접 바라보도록 import 정렬
- `tests/test_channel_push_messages.py`
  - push regression 테스트가 canonical delivery helper를 직접 바라보도록 import 정렬

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - broader ERP lazy import (`apps/api/erp_measurement.py`, `apps/api/erp_orders_structured.py`, `apps/api/erp_shipment_settings.py`)는 이번 배치에서 의도적으로 shim 경로를 유지했다.
  - `channel_delivery` canonical module은 기존 outbox/status/metrics 의미론을 그대로 보존했고, root `db`/`models` import 스타일 같은 기존 기술부채는 structure-only 원칙에 따라 이번 배치에서 손대지 않았다.

### 5.2 자동 다음 배치 전감리
- Batch 39 완료 후 자동 전감리 결과 다음 안전 구조 후보는 `channel_inbound`로 정리됐다.
- 비교 후보:
  - `erp_permissions`: self-contained helper 성격은 있으나 caller surface가 ERP 전역으로 넓어 한 배치 blast radius가 크다.
  - `context_processors`: leaf에 가깝지만 channel stack closure를 이어가는 효과는 작다.
- 보류 메모:
  - `storage`는 caller fan-in과 adapter/runtime side effect 때문에 별도 배치로 분리하는 편이 더 안전하다는 판단이 나왔다.

## 6. 의도적으로 건드리지 않은 것
- `apps/api/erp_measurement.py` / `apps/api/erp_orders_structured.py` / `apps/api/erp_shipment_settings.py`의 `mark_order_updated_for_channel()` lazy import
- `storage` backend/presigned URL/thumbnail 동작
- `channel_inbound` webhook/queue 처리
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `pytest tests/test_channel_delivery.py tests/test_foms_namespace_imports.py tests/test_channel_integration_smoke.py tests/test_channel_push_messages.py -q`
- 결과:
  - `88 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_delivery as legacy; import foms.services.channel_delivery as ns; assert legacy.create_pending_delivery is ns.create_pending_delivery; assert legacy.mark_delivery_status is ns.mark_delivery_status; assert legacy.get_delivery_metrics is ns.get_delivery_metrics; print('CHANNEL_DELIVERY_NS_OK')"`
- 결과: `CHANNEL_DELIVERY_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `357 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`tests/test_channel_webhooks.py`, `services/channel_inbound.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_delivery`는 서른일곱 번째 실제 `foms/services` source of truth가 되었고, ChannelTalk outbox/status/metrics helper가 canonical 모듈 한 곳으로 모였다.
- dispatch/admin/queue의 clean edge가 canonical delivery로 정렬되어 channel stack 구조 정리가 한 단계 더 진행됐다.
- 자동 다음 구조 후보는 `channel_inbound`로 정리했고, 비교 후보는 `erp_permissions`, `context_processors` 순으로 유지한다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_inbound`
2. 그 다음 비교 후보는 `erp_permissions`
3. `context_processors`는 작은 대안이지만 channel stack closure 관점에서는 후순위로 유지
