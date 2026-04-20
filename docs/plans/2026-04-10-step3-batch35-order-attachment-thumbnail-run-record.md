# Step 3 Batch 35 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch34-channel-client-run-record.md`

- 일시: 2026-04-10 11:47:42
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `order_attachment_thumbnail`를 서른세 번째 실제 `foms/services` source of truth로 이동하고 attachment API caller 1곳의 import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 35 executed, `order_attachment_thumbnail` canonical migration completed without changing thumbnail scheduling behavior**

이유:
- `foms/services/order_attachment_thumbnail.py`를 새 canonical source로 추가하고, 기존 `services/order_attachment_thumbnail.py`는 thin shim으로 전환했다.
- `apps/api/attachments.py`의 direct import를 canonical path로 정리했다.
- RQ enqueue 우선 + `ThreadPoolExecutor` fallback + background DB update라는 기존 실행 흐름을 canonical 모듈 한 곳에만 유지해 duplicate executor/state 리스크를 피했다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 34 완료 후 자동 전감리 결과:
1. `order_attachment_thumbnail`
2. `order_date_sync`
3. `channel_dispatch`

선정 이유:
- caller surface가 작고 (`apps/api/attachments.py` 1곳) 구조-only 이동 범위를 고정하기 쉬웠다.
- import 시 thread pool 초기화는 있지만 예측 가능하고, Flask request context / ChannelTalk / calendar 축과 결합되지 않았다.
- background thumbnail 경로는 storage + queue + DB session을 쓰지만 API contract가 단순해 shim/caller binding 검증과 focused behavior test를 함께 붙이기 적합했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/order_attachment_thumbnail.py`
  - thumbnail background helper 구현을 canonical 위치로 이동
  - module docstring, `__future__`, `__all__` 추가
  - 기존 의미론 유지:
    - `ORDER_ATTACHMENT_THUMBNAIL_WORKERS` 기반 worker 수 산정
    - `_thumbnail_executor` 전역 실행기
    - RQ enqueue 우선, 실패 시 `ThreadPoolExecutor` fallback
    - background storage thumbnail 생성 후 attachment `thumbnail_key` update

### 3.2 legacy shim 전환
- `services/order_attachment_thumbnail.py`
  - `schedule_order_attachment_thumbnail_generation`만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/attachments.py`
  - `schedule_order_attachment_thumbnail_generation` import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_order_attachment_thumbnail` / `namespaced_order_attachment_thumbnail` import 추가
  - `test_legacy_order_attachment_thumbnail_shim_preserves_canonical_contract()` 추가
  - `test_attachments_api_uses_canonical_order_attachment_thumbnail_import()` 추가

### 4.2 focused behavior verification
- `tests/test_order_attachment_thumbnail.py`
  - `test_schedule_order_attachment_thumbnail_generation_uses_rq_when_available()` 추가
  - `test_schedule_order_attachment_thumbnail_generation_falls_back_to_executor()` 추가
  - `test_generate_order_attachment_thumbnail_background_sets_thumbnail_when_missing()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - RQ enqueue 경로가 `except Exception: pass`를 유지해 import 실패 / queue 오류 / False 반환을 구분하지 못함
  - background/schedule 오류 출력이 `print` 기반이라 로깅 일관성은 약함
  - focused unit test가 queue 예외 fallback, storage 실패, 기존 `thumbnail_key` 유지 분기를 모두 덮지는 않음
  - worker 상한 `4`는 매직 넘버로 남아 있음

### 5.2 residual gap
- 실제 RQ worker/Redis가 연결된 환경에서의 end-to-end thumbnail job smoke는 이번 배치 범위에 포함하지 않았다.
- background thread에서의 `db_session()` / `remove()` 패턴은 기존 설계를 유지했으며 구조-only 이동 외의 보정은 하지 않았다.

## 6. 의도적으로 건드리지 않은 것
- thumbnail 생성 정책 자체
- storage backend 구현
- RQ/worker 배포 구성
- broad `except`/`print` 기반 기존 오류 처리
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_order_attachment_thumbnail.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `60 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.order_attachment_thumbnail as legacy; import foms.services.order_attachment_thumbnail as ns; assert legacy.schedule_order_attachment_thumbnail_generation is ns.schedule_order_attachment_thumbnail_generation; print('ORDER_ATTACHMENT_THUMBNAIL_NS_OK')"`
- 결과: `ORDER_ATTACHMENT_THUMBNAIL_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `333 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `order_attachment_thumbnail`는 서른세 번째 실제 `foms/services` source of truth가 되었고 attachment API caller 정리가 완료됐다.
- executor/queue/storage/DB session 흐름은 canonical 모듈 한 곳에만 남겨 duplicate state 리스크를 피했다.
- 자동 다음 구조 후보는 `order_date_sync`로 재선정됐다.
- 그 다음 비교 후보는 `channel_policy`, `channel_delivery` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `order_date_sync`
2. 그 다음 비교 후보는 `channel_policy`
3. `channel_delivery`는 outbox/ERP lazy import 결합이 더 넓어서 한 단계 뒤로 유지
