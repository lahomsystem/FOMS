# Step 3 Batch 20 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch19-menu-config-run-record.md`

- 일시: 2026-04-08 13:55:15
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_wam_view_models`를 열여덟 번째 실제 `foms/services` source of truth로 이동하고 WAM service caller 3곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 20 executed, `channel_wam_view_models` canonical migration completed without intended WAM payload behavior changes**

이유:
- `foms/services/channel_wam_view_models.py`를 새 canonical source로 추가하고, 기존 `services/channel_wam_view_models.py`는 공개 dataclass/serializer만 재수출하는 thin shim으로 전환했다.
- production caller 3곳(`services/channel_wam_service.py`, `services/channel_wam_attachments.py`, `services/channel_wam_telemetry.py`)을 canonical import로 정리했고, legacy 경로는 shim 계약 테스트만 남겼다.
- `tests/test_channel_wam_view_models.py`를 추가해 request context 권한 판정, nested dataclass 직렬화, page section lookup, empty scopes 계약을 고정했다.
- 후감리에서 지적된 저위험 문서화/계약 테스트 공백은 같은 배치 안에서 module/vm_to_dict docstring과 empty scopes 테스트로 보강했다.
- `CHANNEL_WAM_VIEW_MODELS_NS_OK`/`APP_OK`/`verify_result.py --json`/focused `pytest`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `channel_wam_view_models`
2. `file_utils`
3. `order_storage_cleanup`

선정 이유:
- `file_utils`는 실제 production import 소비자가 거의 없어 가장 기계적으로 안전했지만, 이번 Step 3 진행 맥락에서는 구조 이득이 너무 작았다.
- `channel_wam_view_models`는 dataclass/serializer 중심의 pure helper이며 DB/스토리지/부트스트랩을 직접 건드리지 않으면서도 WAM caller 3곳을 정리할 수 있어 “안전하면서도 의미 있는” 다음 구조 slice였다.
- `order_storage_cleanup`는 caller 수는 적어도 영구 삭제·스토리지 정합에 연결되어 회귀 비용이 더 컸으므로 계속 보류했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_wam_view_models.py`
  - 기존 WAM view model/dataclass/serializer 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `WamRequestContext`
    - `WamBadgeVM`
    - `WamActionVM`
    - `AttachmentItemVM`
    - `AttachmentGroupVM`
    - `WamSectionVM`
    - `WamStickyActionBarVM`
    - `WamPageVM`
    - `vm_to_dict`
  - 후감리 반영으로 모듈 설명과 `vm_to_dict` docstring 추가

### 3.2 legacy shim 전환
- `services/channel_wam_view_models.py`
  - 위 공개 dataclass/serializer만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `services/channel_wam_service.py`
- `services/channel_wam_attachments.py`
- `services/channel_wam_telemetry.py`

각 파일에서:
- `from services.channel_wam_view_models import ...`
- → `from foms.services.channel_wam_view_models import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_wam_view_models` / `namespaced_channel_wam_view_models` import 추가
  - `__all__` 일치와 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_channel_wam_view_models.py`
  - `WamRequestContext` permission / `to_public_dict` 계약
  - empty scopes + empty allowed_sections + attachment_scope=`all` 허용 계약
  - nested dataclass(`WamPageVM`/`WamSectionVM`/`AttachmentGroupVM`/`AttachmentItemVM`) 직렬화 계약
  - `WamPageVM.get_section()` lookup 계약

## 4. 감리 결과 요약
### 4.1 사전 감리
- `order_storage_cleanup`는 영구 삭제/스토리지 정합 리스크 때문에 이번 배치에서도 제외했다.
- `file_utils`는 가장 안전했지만 production import 소비자가 거의 없어 이번 턴 구조 가치가 낮았다.
- `channel_wam_view_models`는 WAM 공개 API 축에 닿지만 순수 dataclass/serializer 모듈이라 Step 3 구조-only 배치로 통제 가능하다고 판단했다.

### 4.2 사후 감리
- 사후 감리에서는 high/medium 수준의 회귀·직렬화 계약 깨짐·shim drift finding은 없었다.
- low 수준으로 (1) canonical 모듈 docstring/`vm_to_dict` docstring 부재, (2) empty scopes 계약 테스트 공백이 식별됐다.
- 두 항목 모두 같은 배치 안에서 바로 보강해 종료 시점에는 새 high/medium finding이 남지 않도록 정리했다.

## 5. 의도적으로 건드리지 않은 것
- `services/order_storage_cleanup.py`
- `services/file_utils.py`
- `apps/api/channel_wam.py`
- WAM template / static asset 구조
- `services/app_init.py`
- `apps/api/erp_orders_structured.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `app.py`
- `run.py`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.channel_wam_view_models import|import services\.channel_wam_view_models`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.channel_wam_view_models as legacy; import foms.services.channel_wam_view_models as ns; assert legacy.WamRequestContext is ns.WamRequestContext; assert legacy.WamPageVM is ns.WamPageVM; assert legacy.vm_to_dict is ns.vm_to_dict; print('CHANNEL_WAM_VIEW_MODELS_NS_OK')"`
- 결과: `CHANNEL_WAM_VIEW_MODELS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_channel_wam_view_models.py tests/test_foms_namespace_imports.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py tests/test_channel_wam_templates.py`
- 결과: 초기 `51 passed` → 후감리 보강 후 `52 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest`
- 결과: `260 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `channel_wam_view_models`는 열여덟 번째 실제 `foms/services` source of truth가 되었고, WAM request context / attachment / page serializer 계약도 canonical namespace 안으로 들어왔다.
- 이번 배치는 WAM API 축에 닿았지만, 동작 변경 대신 구조 이동 + thin shim + caller import 정리 + serializer 계약 테스트로만 통제했다.
- `order_storage_cleanup`처럼 복구가 어려운 destructive path는 계속 뒤로 미루고, `file_utils`처럼 구조 이득이 작은 dead-ish helper보다 실제 caller가 있는 pure module을 우선 정리하는 기준을 유지했다.

## 8. 다음 단계
1. 다음 구조 후보는 `file_utils` 같은 초저위험 slice와 `order_storage_cleanup` 같은 고위험 slice를 다시 분리해, 구조 가치 대비 리스크가 맞는 후보를 Batch 21로 좁힌다
2. 별도 품질 배치로 `services/app_init.py` 기본 관리자 자격 증명/로깅, `apps/api/erp_orders_structured.py` Channel gating 및 빈 주소 reset 조건을 위한 Spec 초안을 준비
3. WAM 축에서는 이번 구조 이동과 별도로, 필요 시 bootstrap payload snapshot이나 template-facing JSON 키 검증을 추가 품질 배치로 검토한다
