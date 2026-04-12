# Step 3 Batch 40 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch39-channel-delivery-run-record.md`

- 일시: 2026-04-10 13:54:13
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_inbound`를 서른여덟 번째 실제 `foms/services` source of truth로 이동하고 webhook/worker caller import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 40 executed, `channel_inbound` canonical migration completed without changing ChannelTalk inbound webhook/worker behavior**

이유:
- `foms/services/channel_inbound.py`를 새 canonical source로 추가하고, 기존 `services/channel_inbound.py`는 thin shim으로 전환했다.
- `apps/api/channel_webhooks.py`, `services/jobs/tasks.py`가 inbound helper를 canonical path에서 바라보도록 정리했다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 39 완료 후 자동 전감리 결과:
1. `channel_inbound`
2. `erp_permissions`
3. `context_processors`

선정 이유:
- `channel_client`/`channel_policy`/`channel_dispatch`/`channel_delivery`가 이미 canonicalized된 상태라 webhook receipt -> dedupe/log -> queue worker -> order 생성 경로까지 이어서 정리하면 ChannelTalk stack의 inbound 경로도 작은 vertical slice로 닫을 수 있었다.
- 실제 production caller를 작은 슬라이스로 제한할 수 있었다. 이번 배치에서는 `channel_webhooks`, `jobs.tasks`, webhook-focused tests만 canonical import로 전환하고 queue 구현 자체는 의도적으로 건드리지 않아 blast radius를 줄였다.
- canonical module 내부에서 persistence import를 `foms.persistence.main.*`로 정렬할 수 있어 Step 3 구조 정리 방향과 잘 맞았다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_inbound.py`
  - `generate_payload_hash()`, `extract_keys()`, `receive_webhook()`, `parse_order_text()`, `process_inbound_job()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - `db_session`/`get_db`, `ChannelInboundEventLog`/`Order` import를 `foms.persistence.main.*` 경로로 정렬
  - 기존 의미론 유지:
    - provider event id / stable id / hash fallback 기반 dedupe + creation key 생성 유지
    - whitelist group reject / duplicate ignore / enqueue retry 흐름 유지
    - 텍스트 파싱, PII masking, dry-run vs 실제 주문 생성 흐름 유지

### 3.2 legacy shim 전환
- `services/channel_inbound.py`
  - 공개 inbound helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/channel_webhooks.py`
  - webhook endpoint의 `receive_webhook()` lazy import를 canonical path로 전환
- `services/jobs/tasks.py`
  - worker task의 `process_inbound_job()` lazy import를 canonical path로 전환
- `tests/test_channel_webhooks.py`
  - inbound helper import를 canonical path로 전환
  - `enqueue_channeltalk_inbound` patch target을 canonical module 기준으로 정렬

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_inbound` / `namespaced_channel_inbound` import 추가
  - `test_legacy_channel_inbound_shim_preserves_canonical_contract()` 추가
  - `test_channel_inbound_canonical_module_uses_canonical_persistence_imports()` 추가
  - `test_channel_webhooks_uses_canonical_channel_inbound_lazy_import()` 추가
  - `test_tasks_use_canonical_channel_inbound_lazy_import()` 추가

### 4.2 focused behavior verification
- `tests/test_channel_webhooks.py`
  - `test_extract_keys()`
  - `test_parse_order_text()`
  - `test_receive_webhook_success()`
  - `test_receive_webhook_duplicate()`
  - `test_process_inbound_job_dry_run()`
  - `test_process_inbound_job_create_enabled()`
  - 위 테스트들이 canonical inbound module 기준 patch/import로 계속 통과하는지 확인

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `parse_order_text()` docstring은 여전히 3-tuple 설명을 유지하지만 실제 런타임 계약은 4-value 반환이다. 이는 pre-existing 문서 drift로 남겼다.
  - `process_inbound_job()`와 해당 테스트는 기존 SQLAlchemy `Query.get()` legacy warning 3건을 계속 노출한다.
  - canonical module 내부의 `enqueue_channeltalk_inbound`는 의도적으로 `services.jobs.queue` 경로를 유지했다. queue canonicalization까지 이번 배치에 묶지 않기 위한 결정이다.

### 5.2 자동 다음 배치 전감리
- Batch 40 완료 후 자동 전감리 결과 다음 안전 구조 후보는 `context_processors`로 정리됐다.
- 비교 후보:
  - `erp_permissions`: self-contained helper 성격은 있으나 caller surface가 ERP 전역으로 넓어 shim contract 실수 비용이 크다.
  - `channel_quick_actions`: channel 축 연속성은 있으나 DB + storage + `erp_display` 결합으로 slice 크기가 커진다.
- 보류 메모:
  - `storage`는 일부 감리에서 후보로 재거론됐지만, direct caller surface 재검토 결과 약 500줄 규모, 넓은 fan-in, optional adapter/runtime side effect 때문에 dedicated batch로 미루는 편이 더 안전하다고 정리했다.

## 6. 의도적으로 건드리지 않은 것
- `services/jobs/queue.py`의 inbound enqueue 구현 자체
- `storage` backend / presigned upload / thumbnail 동작
- `erp_permissions`, `context_processors`, `channel_quick_actions`
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_channel_webhooks.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `80 passed, 3 warnings`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_inbound as legacy; import foms.services.channel_inbound as ns; assert legacy.receive_webhook is ns.receive_webhook; assert legacy.process_inbound_job is ns.process_inbound_job; assert legacy.parse_order_text is ns.parse_order_text; print('CHANNEL_INBOUND_NS_OK')"`
- 결과: `CHANNEL_INBOUND_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `361 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_inbound`는 서른여덟 번째 실제 `foms/services` source of truth가 되었고, ChannelTalk inbound webhook/worker helper가 canonical 모듈 한 곳으로 모였다.
- webhook endpoint와 worker task의 clean edge가 canonical inbound helper로 정렬되어 ChannelTalk 구조 정리가 한 단계 더 진행됐다.
- 자동 다음 구조 후보는 `context_processors`로 정리했고, 비교 후보는 `erp_permissions`, `channel_quick_actions` 순으로 유지한다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `context_processors`
2. 그 다음 비교 후보는 `erp_permissions`
3. `storage`는 규모와 fan-in 때문에 별도 dedicated batch로 유지
