# Step 3 Batch 31 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch30-realtime-notifications-run-record.md`

- 일시: 2026-04-10 11:02:00
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `user_deletion`을 스물아홉 번째 실제 `foms/services` source of truth로 이동하고 user cleanup caller 2곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 31 executed, `user_deletion` canonical migration completed without changing user cleanup / FK repair behavior**

이유:
- `foms/services/user_deletion.py`를 새 canonical source로 추가하고, 기존 `services/user_deletion.py`는 thin shim으로 전환했다.
- caller 2곳(`apps/auth.py`, `apps/api/attachments.py`)을 모두 canonical import로 정리했다.
- 신규 단위 테스트로 reference cleanup summary 계약과 attachment FK repair 분기를 고정했고, 기존 삭제 라우트 테스트의 조회 범위도 안정화했다.
- 후감리에서 batch-introduced 회귀는 발견되지 않았고 `USER_DELETION_NS_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 선정 근거
Batch 30 완료 후 자동 전감리 결과:
1. `user_deletion`
2. `db_indexes`
3. `order_attachment_thumbnail`

선정 이유:
- `user_deletion`은 caller가 적고 import-time side effect가 없어서 structure-only slice로 다루기 쉬웠다.
- 실제 로직은 user delete 전에 FK nullify / dependent delete를 수행하는 helper와 Postgres FK repair helper 두 개로 경계가 분명했다.
- `business_calendar` 축과 결합되지 않았고, caller blast radius도 `auth` / `attachments` 두 곳으로 제한됐다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/user_deletion.py`
  - 기존 user cleanup / FK repair 구현을 canonical 위치로 이동
  - module docstring, `__all__`, 타입 힌트 추가
  - 기존 의미론 유지:
    - chat room owner의 message/member 선삭제
    - nullable user FK는 `None`으로 정리
    - delete 대상 FK는 bulk delete 유지
    - Postgres에서만 `order_attachments.user_id` FK를 `ON DELETE SET NULL`로 보정

### 3.2 legacy shim 전환
- `services/user_deletion.py`
  - `detach_user_references_for_delete`, `ensure_order_attachment_user_fk_set_null`를 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/auth.py`
  - `detach_user_references_for_delete` import를 canonical path로 전환
- `apps/api/attachments.py`
  - `ensure_order_attachment_user_fk_set_null` import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_user_deletion` / `namespaced_user_deletion` import 추가
  - `test_legacy_user_deletion_shim_preserves_canonical_contract()` 추가
  - `test_auth_uses_canonical_user_deletion_import()` 추가
  - `test_attachments_api_uses_canonical_user_deletion_import()` 추가

### 4.2 focused behavior verification
- `tests/test_user_deletion.py`
  - `test_detach_user_references_for_delete_returns_summary_and_applies_expected_operations()` 추가
  - `test_ensure_order_attachment_user_fk_set_null_returns_false_outside_postgres()` 추가
  - `test_ensure_order_attachment_user_fk_set_null_skips_when_constraint_already_normalized()` 추가
  - `test_ensure_order_attachment_user_fk_set_null_repairs_constraint_when_needed()` 추가
- `tests/test_user_delete.py`
  - 기존 삭제 라우트 테스트의 notification / estimate / manager_link 조회를 fixture-specific filter로 보강해 전역 `.one()` 취약성을 제거

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `apps/auth.py`의 try/except 양쪽 import 중복은 스타일 노이즈 수준
  - namespace test의 object identity 검증은 향후 lazy wrapper 도입 시 다소 취약할 수 있음

### 5.2 residual gap
- `ensure_order_attachment_user_fk_set_null()`의 실제 Postgres DDL 경로는 fake DB contract로만 검증했고, 실 Postgres smoke는 이번 배치에서 실행하지 않았다.
- `auth.log_access` 등의 기존 broad exception 패턴은 이번 구조 배치 범위 밖이므로 유지했다.

## 6. 의도적으로 건드리지 않은 것
- user delete business rule 자체
- attachment schema auto-init policy
- Postgres 외 DB에서의 동작 정책
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_user_deletion.py tests/test_user_delete.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `53 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.user_deletion, foms.services.user_deletion; print('USER_DELETION_NS_OK')"`
- 결과: `USER_DELETION_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `307 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `user_deletion`은 스물아홉 번째 실제 `foms/services` source of truth가 되었고, user cleanup / attachment FK repair caller 정리가 완료됐다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `db_indexes`다.
- 그 다음 비교 후보는 `estimate_service`, `order_attachment_thumbnail` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `db_indexes`
2. 그 다음 비교 후보는 `estimate_service`
3. `order_attachment_thumbnail`는 storage/jobs/thread pool 결합 때문에 비교 후보로 유지
