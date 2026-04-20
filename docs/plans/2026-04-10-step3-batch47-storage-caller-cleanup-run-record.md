# Step 3 Batch 47 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch46-storage-run-record.md`

- 일시: 2026-04-10 17:05:00
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Batch 46에서 canonical source로 고정한 `storage`에 대해, 남아 있던 live app/API/worker caller의 legacy `services.storage` import를 canonical `foms.services.storage` 경로로 정렬해 runtime namespace 전환을 한 단계 더 닫는다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 47 executed, remaining live storage callers were aligned to the canonical namespace without changing storage runtime behavior**

이유:
- `foms/services/storage.py`를 source of truth로 유지한 상태에서 `app.py`, `apps/*`, `services/jobs/tasks.py`의 live caller를 canonical import로 정렬했다.
- `services/storage.py` thin shim은 계속 유지하되, 실동작 경로는 테스트/백업 파일을 제외하고 더 이상 legacy path에 의존하지 않도록 정리했다.
- 별도 caller smoke와 namespace 회귀 테스트를 통해 app/API/worker 결합점이 동일한 `get_storage` singleton을 계속 바인딩함을 확인했다.

## 2. 선정 근거
Batch 46 완료 후 자동 전감리 결과:
1. `erp_policy` (고위험, 즉시 진행 no-go)
2. `business_calendar` (계속 제외)
3. `storage` legacy caller cleanup (저위험 후속 slice)

선정 이유:
- 남은 실질 구조 후보인 `erp_policy`는 여전히 `business_calendar` eager import와 `__file__` 기반 `data/` 경로 계산 때문에 승인형 고위험 배치가 필요했다.
- 반면 `storage`는 이미 Batch 46에서 singleton/shim 계약이 검증되어 있었기 때문에, 남아 있던 live caller import 경로만 canonical path로 정리하는 후속 배치는 구조-only 범위에서 안전하게 수행 가능했다.
- 이 후속 cleanup을 마치면 `services.storage` legacy import는 테스트/문서/백업을 제외하고 live runtime 코드에서 사실상 제거된다.

## 3. 실제 변경 범위
### 3.1 app/bootstrap caller 정렬
- `app.py`
  - `from services.storage import get_storage` → `from foms.services.storage import get_storage`

### 3.2 Flask Blueprint / API caller 정렬
- `apps/admin.py`
- `apps/api/attachments.py`
- `apps/api/files.py`
- `apps/api/channel_integration.py`
- `apps/api/chat/routes.py`
- `apps/api/chat/utils.py`
- `apps/api/erp_orders_blueprint.py`
- `apps/api/erp_orders_draftsman.py`
- `apps/api/erp_orders_drawing.py`

위 파일들의 storage import를 모두 `from foms.services.storage import get_storage`로 정렬했다.

### 3.3 worker caller 정렬
- `services/jobs/tasks.py`
  - `create_thumbnail_for_attachment()` 내부 lazy import를 canonical path로 전환했다.

## 4. 테스트 보강
### 4.1 namespace / caller contract
- `tests/test_foms_namespace_imports.py`
  - `test_app_and_api_modules_use_canonical_storage_imports()` 추가
  - `test_jobs_tasks_uses_canonical_storage_lazy_import()` 추가

### 4.2 검증 의도
- app/API module source가 실제로 canonical import 문자열을 갖는지 확인
- import 결과로 바인딩된 `get_storage`가 `foms.services.storage.get_storage`와 동일한 singleton function인지 확인
- worker thumbnail task의 lazy import가 canonical path를 가리키는지 확인

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- `storage` canonical source 수는 그대로 44개이며, 이번 배치는 source 이동이 아니라 live caller cleanup 배치다.
- repo search 기준 `from services.storage import get_storage`는 이제 backup 파일만 남고, live runtime 코드에서는 제거됐다.

### 5.2 자동 다음 배치 전감리
- 다음 남은 구조 후보는 여전히 `erp_policy`
- 단, `services.business_calendar` eager import와 `_DATA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 기반 data 경로 계산 때문에 현재 규칙(캘린더 축 제외, structure-only)에서는 바로 진행 불가
- 따라서 다음 단계는
  1. `erp_policy` 승인형 고위험 배치 계획 수립, 또는
  2. 별도 저위험 cleanup slice 추가 발굴
  중 하나로 분기해야 한다

## 6. 의도적으로 건드리지 않은 것
- `foms/services/storage.py` 본체 로직
- `services/storage.py` thin shim
- `business_calendar` / `/calendar`
- `erp_policy`
- backup 경로의 legacy `services.storage` import

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py`
- 결과:
  - `98 passed`

### 7.2 caller namespace smoke
- 실행: `python -c "import inspect; import app; from apps import admin; from apps.api import attachments, channel_integration, erp_orders_blueprint, erp_orders_draftsman, erp_orders_drawing, files; from apps.api.chat import routes as chat_routes, utils as chat_utils; import services.jobs.tasks as jobs_tasks; import foms.services.storage as namespaced_storage; modules = [app, admin, attachments, channel_integration, erp_orders_blueprint, erp_orders_draftsman, erp_orders_drawing, files, chat_routes, chat_utils]; assert all(module.get_storage is namespaced_storage.get_storage for module in modules); assert 'from foms.services.storage import get_storage' in inspect.getsource(jobs_tasks.create_thumbnail_for_attachment); print('STORAGE_CALLERS_NS_OK')"`
- 결과: `STORAGE_CALLERS_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- Batch 46이 `storage`의 source of truth와 singleton contract를 고정한 배치였다면, Batch 47은 그 canonical 경로를 실제 app/API/worker caller까지 확장한 cleanup 배치다.
- 이로써 `storage`는 canonical source + live canonical caller 구조가 완성되었고, legacy shim은 호환성 안전망 역할만 남게 됐다.

## 9. 다음 단계
1. `erp_policy`를 계속 다음 후보로 보되, 이는 승인형 고위험 배치로 계획을 먼저 세워야 한다.
2. 사용자 지시가 유지되는 한 `business_calendar` / `/calendar` 축은 계속 제외한다.
3. 필요 시 `services/jobs/*` 패키지 전체 canonical화는 별도 중·고위험 배치로 분리한다.
