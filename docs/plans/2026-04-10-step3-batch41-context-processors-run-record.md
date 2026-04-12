# Step 3 Batch 41 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch40-channel-inbound-run-record.md`

- 일시: 2026-04-10 14:46:06
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `context_processors`를 서른아홉 번째 실제 `foms/services` source of truth로 이동하고 app bootstrap/test import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 41 executed, `context_processors` canonical migration completed without changing Flask template context injection behavior**

이유:
- `foms/services/context_processors.py`를 새 canonical source로 추가하고, 기존 `services/context_processors.py`는 thin shim으로 전환했다.
- `app.py`가 context processor registrar를 canonical path에서 바라보도록 정리했다.
- `storage` lazy import는 의도적으로 `services.storage` 경로를 유지해 Batch 41 범위를 넓히지 않았다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 40 완료 후 자동 전감리 결과:
1. `context_processors`
2. `erp_permissions`
3. `channel_quick_actions`

선정 이유:
- 모듈 자체가 작고 cohesive하며, direct production caller가 사실상 `app.py` 한 곳이라 blast radius를 가장 작게 유지할 수 있었다.
- 이미 `foms.services.menu_config`를 사용 중이라 Step 3의 canonical service line을 이어가기 좋았다.
- `services.storage`는 약 500줄 규모와 넓은 fan-in 때문에 전용 배치로 미루고, 이번 배치에서는 `inject_status_list()`의 lazy import를 그대로 둬 구조-only 원칙을 지켰다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/context_processors.py`
  - `parse_json_string_filter()`, `parse_json_string()`, `inject_statuses()`, `inject_status_list()`, `utility_processor()`, `inject_menu()`, `register_context_processors()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - `get_db`, `User` import를 `foms.persistence.main.*` 경로로 정렬
  - 기존 의미론 유지:
    - JSON template filter/helper 동작 유지
    - status / role / impersonation / beta flag 주입 유지
    - construction team용 메뉴 축소 로직 유지
    - direct upload 계산을 위한 `services.storage.get_storage` lazy import 유지

### 3.2 legacy shim 전환
- `services/context_processors.py`
  - 공개 context processor/filter helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `app.py`
  - `register_context_processors` import를 canonical path로 전환
- `tests/test_menu_config.py`
  - `context_processors` import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_context_processors` / `namespaced_context_processors` import 추가
  - `test_legacy_context_processors_shim_preserves_canonical_contract()` 추가
  - `test_context_processors_canonical_module_uses_canonical_persistence_imports()` 추가
  - `test_context_processors_keeps_storage_lazy_import_on_legacy_path()` 추가
  - `test_app_uses_canonical_context_processors_import()` 추가

### 4.2 focused behavior verification
- `tests/test_menu_config.py`
  - construction team 메뉴 제한, non-construction menu 보존, menu cache invalidation 경로가 canonical context processor import 기준에서도 그대로 통과하는지 확인

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `inject_status_list()`는 의도적으로 `services.storage` lazy import를 유지한다. 이는 storage 전용 배치를 별도로 분리하기 위한 결정이다.
  - 권한/세션/메뉴 주입 의미론은 유지했고, broad `except Exception` 기반 direct upload fallback 같은 기존 동작도 structure-only 원칙에 따라 그대로 뒀다.

### 5.2 자동 다음 배치 전감리
- Batch 41 완료 후 자동 전감리 결과 다음 안전 구조 후보는 `erp_permissions`로 정리됐다.
- 비교 후보:
  - `channel_quick_actions`: direct caller surface는 좁지만 storage + `erp_display` private helper 결합이 있어 Batch 42 단독 slice로는 더 무겁다.
  - `storage`: 테스트가 이미 “다음 전용 배치” 전제를 갖고 있고, 약 500줄 규모/넓은 fan-in/optional adapter side effect 때문에 계속 dedicated batch로 미룬다.

## 6. 의도적으로 건드리지 않은 것
- `inject_status_list()` 내부의 `services.storage` lazy import
- `storage` singleton / boto3 / Pillow / presigned upload 동작
- `erp_permissions`, `channel_quick_actions`
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_menu_config.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `83 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.context_processors as legacy; import foms.services.context_processors as ns; assert legacy.register_context_processors is ns.register_context_processors; assert legacy.inject_menu is ns.inject_menu; assert legacy.inject_status_list is ns.inject_status_list; print('CONTEXT_PROCESSORS_NS_OK')"`
- 결과: `CONTEXT_PROCESSORS_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `365 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `context_processors`는 서른아홉 번째 실제 `foms/services` source of truth가 되었고, Flask template context/filter wiring이 canonical 모듈 한 곳으로 모였다.
- app bootstrap이 canonical registrar를 직접 바라보게 되어 template layer 구조 정리가 한 단계 더 진행됐다.
- `storage`는 이번 배치에서 의도적으로 묶지 않았고, 자동 다음 구조 후보는 `erp_permissions`로 정리했다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `erp_permissions`
2. 그 다음 비교 후보는 `channel_quick_actions`
3. `storage`는 규모와 singleton/runtime fan-in 때문에 별도 dedicated batch로 유지
