# Step 3 Batch 38 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch37-channel-policy-run-record.md`

- 일시: 2026-04-10 12:43:04
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_dispatch`를 서른여섯 번째 실제 `foms/services` source of truth로 이동하고 manual/worker caller import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 38 executed, `channel_dispatch` canonical migration completed without changing ChannelTalk dispatch behavior**

이유:
- `foms/services/channel_dispatch.py`를 새 canonical source로 추가하고, 기존 `services/channel_dispatch.py`는 thin shim으로 전환했다.
- `apps/api/channel_integration.py`와 `services/jobs/tasks.py`가 dispatch helper를 canonical path에서 바라보도록 정리했다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 37 완료 후 자동 전감리 결과:
1. `channel_dispatch`
2. `erp_permissions`
3. `channel_delivery`

선정 이유:
- `channel_client`와 `channel_policy`가 이미 canonicalized된 상태라 dispatch layer까지 이어서 정리하면 channel stack의 얇은 전송층을 `foms/services` 아래로 한 단계 더 닫을 수 있었다.
- runtime caller가 `channel_integration` 1곳, worker lazy import 1곳으로 좁아 small-slice 구조 배치에 적합했다.
- top-level import는 `requests`와 이미 canonicalized된 channel helper들뿐이라 앱 부팅 순서 변경 리스크가 낮았다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_dispatch.py`
  - `dispatch_channel_push()`, `dispatch_order_event()`와 내부 event/data extraction helper를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - 기존 의미론 유지:
    - event key/template payload 기반 event type 추론
    - stale source_version 차단
    - attachment presigned URL 수집 + attachment cap 적용
    - HTTPError status code별 delivery status 전이

### 3.2 legacy shim 전환
- `services/channel_dispatch.py`
  - 공개 dispatch helper 2개만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/channel_integration.py`
  - `dispatch_order_event` import를 canonical path로 전환
- `services/jobs/tasks.py`
  - `dispatch_channel_push` worker lazy import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_dispatch` / `namespaced_channel_dispatch` import 추가
  - `test_legacy_channel_dispatch_shim_preserves_canonical_contract()` 추가
  - `test_channel_dispatch_canonical_module_uses_canonical_channel_client_and_policy_imports()` 추가
  - `test_channel_integration_uses_canonical_channel_dispatch_import()` 추가
  - `test_tasks_use_canonical_channel_dispatch_lazy_import()` 추가

### 4.2 focused behavior verification
- `tests/test_channel_dispatch.py`
  - `test_dispatch_order_event_returns_failure_when_group_missing()` 추가
  - `test_dispatch_order_event_applies_attachment_policy_before_send()` 추가
- `tests/test_channel_push_messages.py`
  - dispatch behavior regression 테스트가 canonical `channel_dispatch`를 직접 바라보도록 import 정렬

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - canonical `channel_dispatch`는 여전히 `services.channel_delivery`, `services.storage`를 lazy import로 참조한다.
  - broad inventory 기준으로는 `erp_permissions`가 낮은 결합 대안으로 남아 있지만, channel stack closure 관점에서는 `channel_delivery`가 다음 구조 배치로 더 자연스럽다는 판단이 나왔다.

### 5.2 residual gap
- dispatch canonicalization만으로 channel stack 전체가 `foms/services`로 닫힌 것은 아니며, delivery/storage lazy import 경계가 남아 있다.
- manual push/outbox/worker semantics 자체는 구조-only 원칙에 따라 변경하지 않았다.

## 6. 의도적으로 건드리지 않은 것
- `channel_delivery`의 outbox/status/metrics 로직
- `storage`의 presigned URL/thumbnail/storage backend 동작
- ChannelTalk 메시지 문구/라우팅 규칙 자체
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `pytest tests/test_channel_dispatch.py tests/test_channel_push_messages.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `75 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_dispatch as legacy; import foms.services.channel_dispatch as ns; assert legacy.dispatch_channel_push is ns.dispatch_channel_push; assert legacy.dispatch_order_event is ns.dispatch_order_event; print('CHANNEL_DISPATCH_NS_OK')"`
- 결과: `CHANNEL_DISPATCH_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `pytest`
- 결과: `350 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_dispatch`는 서른여섯 번째 실제 `foms/services` source of truth가 되었고 manual push/worker dispatch 진입점이 canonical 모듈 한 곳으로 모였다.
- `channel_integration`과 worker task import가 canonical dispatch로 정렬되어 channel stack 구조 정리가 한 단계 더 진행됐다.
- 자동 다음 구조 후보는 `channel_delivery`로 정리했고, 비교 후보는 `erp_permissions`, `channel_inbound` 순으로 유지한다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_delivery`
2. 그 다음 비교 후보는 `erp_permissions`
3. `channel_inbound`는 queue/webhook 결합 때문에 그 다음 단계로 유지
