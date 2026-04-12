# Step 3 Batch 36 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch35-order-attachment-thumbnail-run-record.md`

- 일시: 2026-04-10 12:07:10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `order_date_sync`를 서른네 번째 실제 `foms/services` source of truth로 이동하고 lazy/direct caller import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 36 executed, `order_date_sync` canonical migration completed without changing schedule-date sync behavior**

이유:
- `foms/services/order_date_sync.py`를 새 canonical source로 추가하고, 기존 `services/order_date_sync.py`는 thin shim으로 전환했다.
- `services/app_init.py`의 lazy listener import와 `scripts/backfill_phase4_dates.py`의 backfill helper import를 canonical path로 정리했다.
- dead stub 성격의 `services/order_date_sync_event.py`도 canonical helper를 바라보도록 맞춰 내부 legacy dependency를 하나 더 줄였다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 35 완료 후 자동 전감리 결과:
1. `order_date_sync`
2. `channel_policy`
3. `channel_delivery`

선정 이유:
- caller surface가 제한적이고 (`app_init` lazy import 1곳, backfill script 1곳, dead stub 1곳) 구조-only 이동 범위를 고정하기 쉬웠다.
- import 시 network/storage singleton/Flask context processor 부수효과가 없고, 실제 listener 등록은 `register_date_sync_listener()` 호출 시점에만 발생한다.
- `business_calendar` 축과 직접 연결되지 않아 사용자 제외 범위를 침범하지 않았다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/order_date_sync.py`
  - 날짜 정규화 / `OrderScheduleDate` spec 수집 / relationship sync / SQLAlchemy `before_flush` listener 등록 로직을 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - 기존 의미론 유지:
    - `_normalize_date_str()`의 유연 파싱
    - measurement / as_visit / construction spec 수집 순서
    - `sync_order_dates()`의 relationship 재구성 방식
    - `register_date_sync_listener()`의 `Session.before_flush` 훅 등록

### 3.2 legacy shim 전환
- `services/order_date_sync.py`
  - 공개 helper 3개만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `services/app_init.py`
  - `register_date_sync_listener` lazy import를 canonical path로 전환
- `scripts/backfill_phase4_dates.py`
  - `collect_order_schedule_date_specs`, `sync_order_dates` import를 canonical path로 전환
- `services/order_date_sync_event.py`
  - dead stub의 `sync_order_dates` import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_order_date_sync` / `namespaced_order_date_sync` import 추가
  - `test_legacy_order_date_sync_shim_preserves_canonical_contract()` 추가
  - `test_app_init_uses_canonical_order_date_sync_lazy_import()` 추가
  - `test_order_date_sync_event_uses_canonical_order_date_sync_import()` 추가
  - `test_backfill_phase4_dates_uses_canonical_order_date_sync_imports()` 추가

### 4.2 focused behavior verification
- `tests/test_order_date_sync.py`
  - `test_collect_order_schedule_date_specs_normalizes_and_deduplicates_dates()` 추가
  - `test_sync_order_dates_uses_get_db_when_session_missing()` 추가
  - `test_register_date_sync_listener_syncs_only_changed_orders()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `services/order_date_sync_event.py`에 미사용 `Order` import가 남아 있음
  - `sync_order_dates()`의 `db_session` 파라미터는 기존처럼 실질 사용처가 없어 문맥 전달용으로만 남아 있음
  - `register_date_sync_listener()`는 다중 호출 시 listener 중복 등록 가능성이 있음
  - backfill script import 검증 테스트가 현재 작업 디렉터리(CWD)에 의존함
  - `collect_order_schedule_date_specs()`는 여전히 장함수이고 달력상 무효 날짜를 엄격 검증하지 않음
  - `order_date_sync_event.py` 자체는 여전히 `pass` 스텁이며 실제 등록 경로는 `app_init`에 남아 있음

### 5.2 residual gap
- 실제 listener 중복 등록 방지나 session-local guard 보강은 이번 구조-only 배치 범위에 포함하지 않았다.
- `order_date_sync_event.py`는 기능 스텁 상태를 유지했고 canonical import 정렬만 수행했다.

## 6. 의도적으로 건드리지 않은 것
- 날짜 정규화 규칙 자체
- listener idempotency / recursion guard 개선
- backfill script의 런타임/CLI 동작
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_order_date_sync.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `64 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.order_date_sync as legacy; import foms.services.order_date_sync as ns; assert legacy.collect_order_schedule_date_specs is ns.collect_order_schedule_date_specs; assert legacy.sync_order_dates is ns.sync_order_dates; assert legacy.register_date_sync_listener is ns.register_date_sync_listener; print('ORDER_DATE_SYNC_NS_OK')"`
- 결과: `ORDER_DATE_SYNC_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `340 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `order_date_sync`는 서른네 번째 실제 `foms/services` source of truth가 되었고 listener/backfill caller 정리가 완료됐다.
- listener 등록 로직과 spec 수집 동작은 canonical 모듈 한 곳에만 남겨 동일 로직의 이중 관리 리스크를 피했다.
- 자동 다음 구조 후보는 `channel_policy`로 재선정됐다.
- 그 다음 비교 후보는 `erp_permissions`, `channel_delivery` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_policy`
2. 그 다음 비교 후보는 `erp_permissions`
3. `channel_delivery`는 DB/outbox 결합이 더 넓어서 한 단계 뒤로 유지
