# Step 3 Batch 30 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch29-rate-limit-run-record.md`

- 일시: 2026-04-10 10:45:09
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `realtime_notifications`를 스물여덟 번째 실제 `foms/services` source of truth로 이동하고 ERP 알림 caller 3곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 30 executed, `realtime_notifications` canonical migration completed without changing Socket.IO emit behavior**

이유:
- `foms/services/realtime_notifications.py`를 새 canonical source로 추가하고, 기존 `services/realtime_notifications.py`는 thin shim으로 전환했다.
- caller 3곳(`apps/api/notifications.py`, `apps/api/erp_orders_drawing.py`, `apps/api/erp_orders_revision.py`)을 모두 canonical import로 정리했다.
- 신규 단위 테스트로 empty user list, Socket.IO 미초기화 warning path, valid user room emit/default kind 규칙을 고정했다.
- 후감리에서 batch-introduced 회귀는 발견되지 않았고 `REALTIME_NOTIFICATIONS_NS_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 선정 근거
Batch 29 완료 후 자동 전감리 결과:
1. `realtime_notifications`
2. `user_deletion`
3. `order_attachment_thumbnail`

선정 이유:
- `realtime_notifications`는 코드가 작고 cross-service import가 거의 없는 leaf helper였다.
- caller는 3곳이지만 모두 grep-friendly한 ERP 알림 축에 모여 있어 import 정리 blast radius가 제한적이었다.
- Socket.IO emit helper 하나만 canonical source로 떼어내면 되는 전형적인 structure-only slice였다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/realtime_notifications.py`
  - 기존 실시간 알림 emit 구현을 canonical 위치로 이동
  - module docstring, `__all__`, 타입 힌트 추가
  - 기존 의미론 유지:
    - 빈 `user_ids` → `0`
    - `_SOCKETIO_INSTANCE` 없음 → warning + `0`
    - valid user id만 `user_{id}` room으로 emit
    - payload에 `kind` 기본값 `erp_notification`

### 3.2 legacy shim 전환
- `services/realtime_notifications.py`
  - `emit_erp_notification_to_users`를 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/notifications.py`
  - `api_notifications_send()` 내부 lazy import를 canonical path로 전환
  - `api_order_urgent_mention()` 내부 lazy import를 canonical path로 전환
- `apps/api/erp_orders_drawing.py`
  - top-level import를 canonical path로 전환
- `apps/api/erp_orders_revision.py`
  - top-level import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_realtime_notifications` / `namespaced_realtime_notifications` import 추가
  - `test_legacy_realtime_notifications_shim_preserves_canonical_contract()` 추가
  - `test_erp_orders_drawing_uses_canonical_realtime_notification_import()` 추가
  - `test_erp_orders_revision_uses_canonical_realtime_notification_import()` 추가
  - `test_notifications_api_uses_canonical_realtime_notification_lazy_imports()` 추가

### 4.2 focused behavior verification
- `tests/test_realtime_notifications.py`
  - `test_emit_erp_notification_to_users_returns_zero_when_user_ids_empty()` 추가
  - `test_emit_erp_notification_to_users_returns_zero_and_logs_when_socketio_missing()` 추가
  - `test_emit_erp_notification_to_users_sends_to_valid_rooms_and_sets_default_kind()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium/low 회귀 없음
- shim/caller binding과 helper 동작이 모두 의도와 일치

### 5.2 residual gap
- `apps/api/notifications.py`의 lazy import canonical path는 `inspect.getsource()` 기반으로 고정되어 있어, 향후 helper 추출/alias 변경 같은 비기능 리팩터링에도 테스트가 깨질 수 있다.
- legacy shim path에 대해 behavior test를 별도로 다시 실행하지는 않았지만, function object identity 계약으로 canonical behavior를 공유함을 고정했다.

## 6. 의도적으로 건드리지 않은 것
- Socket.IO runtime 초기화 방식
- `_SOCKETIO_INSTANCE` 설정 책임
- 알림 payload 스키마
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_realtime_notifications.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `47 passed`

### 7.2 namespace smoke
- 실행: `python -c "import foms.services.realtime_notifications as m; print('REALTIME_NOTIFICATIONS_NS_OK')"`
- 결과: `REALTIME_NOTIFICATIONS_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `300 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `realtime_notifications`는 스물여덟 번째 실제 `foms/services` source of truth가 되었고, ERP 알림 emit helper caller 정리가 완료됐다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `user_deletion`이다.
- 그 다음 비교 후보는 `db_indexes`, `order_attachment_thumbnail` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `user_deletion`
2. 그 다음 비교 후보는 `db_indexes`
3. `order_attachment_thumbnail`는 storage/jobs/thread pool 결합 때문에 그 다음 비교 후보로 유지
