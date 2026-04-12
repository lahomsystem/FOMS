# Step 3 Batch 43 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch42-erp-permissions-run-record.md`

- 일시: 2026-04-10 15:16:28
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_quick_actions`를 마흔한 번째 실제 `foms/services` source of truth로 이동하고 canonical WAM/function caller를 최소 범위로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 43 executed, `channel_quick_actions` canonical migration completed while deliberately deferring `storage` to its own batch**

이유:
- `foms/services/channel_quick_actions.py`를 새 canonical source로 추가하고, 기존 `services/channel_quick_actions.py`는 thin shim으로 전환했다.
- `foms/services/channel_wam_service.py`와 `apps/api/channel_functions.py`의 quick-action caller를 canonical path로 정리했다.
- canonical module 내부에서는 persistence/ERP display import만 canonical로 바꾸고, `services.storage` import는 의도적으로 legacy 경로로 유지해 storage batch를 섞지 않았다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 42 완료 후 자동 전감리 결과:
1. `channel_quick_actions`
2. `app_init`
3. `storage`

선정 이유:
- direct caller가 좁았다: canonical `channel_wam_service` 1곳, `channel_functions`의 lazy import 1곳, focused test 1곳.
- `storage`처럼 process-wide singleton/runtime init을 갖지 않아 structure-only slice로 유지하기 쉬웠다.
- `app_init`은 파일은 작지만 cold-start/DB init path라 운영 blast radius가 더 컸다.
- `storage`는 넓은 fan-in과 singleton contract 때문에 여전히 dedicated batch가 필요했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_quick_actions.py`
  - `STATUS_MAP`, `parse_foms_command()`, `process_foms_command()`, `get_order_summary_for_wam()`, `get_order_attachments_for_wam()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - `Order`, `OrderAttachment`, `get_db` import를 canonical persistence shim 경로로 정리
  - `erp_display` private helper import를 `foms.services.erp_display` 경로로 정리
  - `services.storage.get_storage`는 의도적으로 유지

### 3.2 legacy shim 전환
- `services/channel_quick_actions.py`
  - 공개 quick-action API만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `foms/services/channel_wam_service.py`
  - `get_order_summary_for_wam`, `get_order_attachments_for_wam` import를 canonical path로 전환
- `apps/api/channel_functions.py`
  - `process_foms_command` lazy import를 canonical path로 전환
- `tests/test_channel_quick_actions.py`
  - focused quick-action test import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 기존 focused quick-action 테스트 유지
- `tests/test_channel_quick_actions.py`
  - parse/path invalid/order not found/success/WAM summary/identity lazy import/ERP beta summary/short link flow까지 canonical module 기준으로 재검증

### 4.2 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_quick_actions` / `namespaced_channel_quick_actions` import 추가
  - `test_legacy_channel_quick_actions_shim_preserves_canonical_contract()` 추가
  - `test_channel_quick_actions_canonical_module_uses_canonical_imports()` 추가
  - `test_channel_quick_actions_keeps_storage_import_on_legacy_path()` 추가
  - `test_channel_wam_service_uses_canonical_quick_actions_import()` 추가
  - `test_channel_functions_api_uses_canonical_quick_actions_import()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `_ensure_dict`, `_erp_get_stage`, `apply_erp_display_fields` 같은 `erp_display` private helper 결합은 구조 배치 범위 밖으로 유지
  - `storage` import는 deliberate legacy retention이다. `channel_quick_actions` 배치에서 storage singleton contract를 건드리지 않는다.

### 5.2 자동 다음 배치 전감리
- Batch 43 완료 후 자동 전감리 기준 다음 안전 구조 후보는 `app_init`으로 정리할 수 있다.
- 비교 후보:
  - `storage`: singleton/runtime init과 넓은 fan-in 때문에 여전히 전용 배치 필요
  - 더 작은 잔여 leaf는 있어도 Step 3 서비스 슬라이스 가치가 `app_init`보다 낮음

## 6. 의도적으로 건드리지 않은 것
- `services.storage` / `get_storage()` singleton
- `erp_display` private helper 구조 개선
- `storage` batch, `app_init` batch
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_channel_quick_actions.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `94 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_quick_actions as legacy; import foms.services.channel_quick_actions as ns; assert legacy.process_foms_command is ns.process_foms_command; assert legacy.get_order_summary_for_wam is ns.get_order_summary_for_wam; assert legacy.get_order_attachments_for_wam is ns.get_order_attachments_for_wam; print('CHANNEL_QUICK_ACTIONS_NS_OK')"`
- 결과: `CHANNEL_QUICK_ACTIONS_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `378 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_quick_actions`는 마흔한 번째 실제 `foms/services` source of truth가 되었고, WAM/bootstrap/function endpoint의 quick-action import가 canonical module로 정리됐다.
- Step 3 범위를 넘기지 않기 위해 `storage`는 의도적으로 legacy import로 남겼다.
- 자동 다음 구조 후보는 `app_init`으로 좁혀졌다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `app_init`
2. `storage`는 singleton/runtime fan-in 때문에 계속 dedicated batch
3. `erp_display` private helper 결합 해소는 별도 품질 배치로 분리
