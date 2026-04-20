# Step 3 Batch 42 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch41-context-processors-run-record.md`

- 일시: 2026-04-10 14:59:14
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `erp_permissions`를 마흔 번째 실제 `foms/services` source of truth로 이동하고, app bootstrap의 clean edge 하나를 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 42 executed, `erp_permissions` canonical migration completed without changing ERP permission semantics**

이유:
- `foms/services/erp_permissions.py`를 새 canonical source로 추가하고, 기존 `services/erp_permissions.py`는 thin shim으로 전환했다.
- `app.py`가 `can_edit_erp`를 canonical path에서 import하도록 정리했다.
- `build_mine_sql_filter()`의 lazy model import는 canonical persistence shim 경로(`foms.persistence.main.models`)로 정리했다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 41 완료 후 자동 전감리 결과:
1. `erp_permissions`
2. `channel_quick_actions`
3. `storage`

선정 이유:
- `erp_permissions`는 import 시점에 스토리지 singleton/boto3/DB session 초기화 같은 무거운 side effect가 없고, 권한 체크/SQL filter helper 위주라 structure-only batch로 다루기 쉬웠다.
- caller fan-out은 넓지만, thin shim을 유지하면 production caller 전체를 한 번에 건드리지 않아도 되어 배치 크기를 작게 유지할 수 있었다.
- `storage`는 광범위 fan-in과 singleton/runtime side effect 때문에 여전히 dedicated batch가 필요하고, `channel_quick_actions`는 `storage` + `erp_display` private helper 결합이 남아 있어 이번보다 약간 더 무거운 slice로 분류했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/erp_permissions.py`
  - `build_mine_sql_filter()`, `can_edit_erp()`, `can_edit_erp_construction()`, `erp_edit_required()`, `erp_construction_edit_required()`를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - `build_mine_sql_filter()` 내부의 `Order` lazy import를 `foms.persistence.main.models` 경로로 정리
  - 권한 의미론 유지:
    - ADMIN은 ERP 수정 가능
    - CS/SALES는 ERP 수정 가능
    - CONSTRUCTION은 시공 전용 action만 허용
    - decorator의 401/403 메시지 및 응답 형식 유지

### 3.2 legacy shim 전환
- `services/erp_permissions.py`
  - 공개 helper/decorator만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `app.py`
  - `can_edit_erp` import를 canonical path로 전환
- 나머지 ERP/Blueprint caller는 thin shim을 통해 그대로 유지해 batch blast radius를 제한

## 4. 테스트 보강
### 4.1 focused behavior verification
- `tests/test_erp_permissions.py` 신규 추가
  - 관리자/CS/SALES 허용 규칙 검증
  - `build_mine_sql_filter()`의 LIKE escape와 condition 개수 검증
  - duplicate username filter group 생략 검증
  - `erp_edit_required()` 401 응답 검증
  - `erp_construction_edit_required()`의 시공팀 허용 경로 검증

### 4.2 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_erp_permissions` / `namespaced_erp_permissions` import 추가
  - `test_legacy_erp_permissions_shim_preserves_canonical_contract()` 추가
  - `test_erp_permissions_build_mine_sql_filter_uses_canonical_persistence_import()` 추가
  - `test_app_uses_canonical_erp_permissions_import()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - 기존 wide caller fan-out은 thin shim으로 완충했고, 이번 배치에서는 `app.py` clean edge만 canonical import로 바꿨다.
  - `erp_permissions` 자체의 unused import/메시지 문구 정합성 같은 품질 메모는 구조 배치 범위 밖으로 유지했다.

### 5.2 자동 다음 배치 전감리
- Batch 42 완료 후 자동 전감리 결과 다음 안전 구조 후보는 `channel_quick_actions`로 정리됐다.
- 비교 후보:
  - `storage`: ~555줄, 넓은 fan-in, `get_storage()` singleton/runtime init 때문에 계속 dedicated batch가 필요
  - `app_init`: 파일은 작지만 app cold-start/DB init path라 구조 배치로는 `channel_quick_actions`보다 operational blast radius가 큼

## 6. 의도적으로 건드리지 않은 것
- 다수의 ERP API/page caller import (`services.erp_permissions` shim 유지)
- `channel_quick_actions`, `storage`, `app_init`
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_erp_permissions.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `86 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.erp_permissions as legacy; import foms.services.erp_permissions as ns; assert legacy.can_edit_erp is ns.can_edit_erp; assert legacy.erp_edit_required is ns.erp_edit_required; assert legacy.build_mine_sql_filter is ns.build_mine_sql_filter; print('ERP_PERMISSIONS_NS_OK')"`
- 결과: `ERP_PERMISSIONS_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `373 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `erp_permissions`는 마흔 번째 실제 `foms/services` source of truth가 되었고, app bootstrap이 canonical 권한 helper를 직접 바라보게 됐다.
- 구조-only 원칙을 지키기 위해 wide ERP caller는 shim 뒤에 남겨두고, app/bootstrap + focused tests + namespace contract만 정리했다.
- 자동 다음 구조 후보는 `channel_quick_actions`로 정리됐고, `storage`는 계속 dedicated batch로 유지한다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_quick_actions`
2. 그 다음 비교 후보는 `app_init`
3. `storage`는 singleton/runtime fan-in 때문에 전용 dedicated batch 유지
