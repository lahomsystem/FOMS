# Step 3 Batch 21 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch20-channel-wam-view-models-run-record.md`

- 일시: 2026-04-08 14:24:04
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `file_utils`를 열아홉 번째 실제 `foms/services` source of truth로 이동하고 `apps/excel_import.py`의 중복 확장자 helper를 canonical helper로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 21 executed, `file_utils` canonical migration completed without intended upload validation behavior changes**

이유:
- `foms/services/file_utils.py`를 새 canonical source로 추가하고, 기존 `services/file_utils.py`는 공개 helper 2개만 재수출하는 thin shim으로 전환했다.
- 기존에는 production import caller가 사실상 없었지만, `apps/excel_import.py`의 로컬 `_allowed_file()` 중복 구현을 제거하고 canonical `allowed_file()` helper를 직접 사용하도록 정리해 구조 이득을 실제 caller 1곳으로 연결했다.
- `tests/test_file_utils.py`를 추가해 Excel/ERP media 확장자 허용·거부 계약을 고정했고, `tests/test_foms_namespace_imports.py`에 shim 동일성 검증을 추가했다.
- 후감리에서 지적된 저위험 항목은 신규 테스트 함수 docstring 보강으로 즉시 반영했다.
- `FILE_UTILS_NS_OK`/`APP_OK`/`verify_result.py --json`/focused `pytest`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `file_utils`
2. `channel_wam_read_model`
3. `order_storage_cleanup`

선정 이유:
- `file_utils`는 가장 기계적으로 안전한 remaining slice였고 DB/Auth/bootstrap/destructive path를 전혀 건드리지 않았다.
- 단순 path-only 이동이면 구조 가치가 낮았지만, `apps/excel_import.py`의 로컬 `_allowed_file()` 중복 구현을 canonical helper로 통일할 수 있어 실제 구조 이득도 확보할 수 있었다.
- `channel_wam_read_model`은 의미 있는 다음 후보였지만 DB read model과 `erp_display` 연동이 있어 Batch 21에서는 더 안전한 slice를 먼저 닫고 다음 자동 단계 후보로 남기는 편이 적절했다.
- `order_storage_cleanup`는 영구 삭제/스토리지 정합 리스크 때문에 이번 배치에서도 계속 보류했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/file_utils.py`
  - 확장자 검사 helper 구현 전체 이관
  - 공개 API `__all__` 명시:
    - `allowed_file`
    - `allowed_erp_media_file`
  - 모듈/함수 docstring 및 타입 힌트 추가

### 3.2 legacy shim 전환
- `services/file_utils.py`
  - 위 공개 helper 2개만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/excel_import.py`
  - `constants.ALLOWED_EXTENSIONS` 직접 사용 + 로컬 `_allowed_file()` 중복 구현 제거
  - `from foms.services.file_utils import allowed_file`로 canonical helper 사용

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_file_utils` / `namespaced_file_utils` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_file_utils.py`
  - Excel 확장자 허용 (`.xlsx`, `.xls`, 대소문자 혼합)
  - Excel 확장자 거부 (확장자 없음, `.csv`)
  - ERP media 확장자 허용 (`.jpg`, `.mp4`)
  - ERP media 확장자 거부 (`.pdf`)
  - 후감리 반영으로 각 테스트 함수 docstring 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `file_utils`는 가장 안전한 low-blast-radius slice로 확인됐다.
- `channel_wam_read_model`은 다음 의미 있는 후보였지만 DB read model/ERP display 연계 때문에 한 단계 뒤로 미뤘다.
- `order_storage_cleanup`는 영구 삭제/스토리지 정합 리스크 때문에 계속 제외했다.

### 4.2 사후 감리
- high/medium 수준의 회귀·shim drift·행동 변화 finding은 없었다.
- low 수준으로 신규 테스트 함수 docstring 부재, 공개 API 목록이 canonical/shim/test 세 곳에 수동 복제된다는 유지보수 메모가 식별됐다.
- 이 중 즉시 수정 가능한 항목인 테스트 docstring은 같은 배치 안에서 바로 보강했다.

## 5. 의도적으로 건드리지 않은 것
- `services/order_storage_cleanup.py`
- `services/channel_wam_read_model.py`
- `services/channel_wam_service.py`
- `services/channel_wam_attachments.py`
- `services/channel_wam_telemetry.py`
- `constants.py`
- `app.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.file_utils import|import services\.file_utils`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.file_utils as legacy; import foms.services.file_utils as ns; assert legacy.allowed_file is ns.allowed_file; assert legacy.allowed_erp_media_file is ns.allowed_erp_media_file; print('FILE_UTILS_NS_OK')"`
- 결과: `FILE_UTILS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_file_utils.py tests/test_foms_namespace_imports.py`
- 결과: 초기 `25 passed` → 후감리 보강 후 `25 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest`
- 결과: `266 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `file_utils`는 열아홉 번째 실제 `foms/services` source of truth가 되었고, 이전까지 사실상 dead helper였던 확장자 검사 유틸이 `excel_import`에서 실제 canonical caller를 가지게 됐다.
- 이번 배치는 구조-only 원칙을 유지하면서도, 중복 helper 제거를 통해 단순 path migration보다 한 단계 더 의미 있는 정리를 만들었다.
- destructive path를 피하고 ultra-safe slice로 한 턴 더 전진한 덕분에, 다음 자동 단계에서는 `channel_wam_read_model` 같은 조금 더 의미 있는 read model slice로 자연스럽게 넘어갈 수 있다.

## 8. 다음 단계
1. 자동 다음 구조 후보는 `channel_wam_read_model`로 잡고, caller/테스트/후속 `channel_wam_service` 연계까지 전감리 후 착수 여부를 판정한다
2. `order_storage_cleanup`는 여전히 영구 삭제/스토리지 정합 리스크 때문에 별도 검증 전략 없이는 뒤로 유지한다
3. 별도 품질 배치로 `services/app_init.py` 기본 관리자 자격 증명/로깅, `apps/api/erp_orders_structured.py` Channel gating 및 빈 주소 reset 조건을 위한 Spec 초안을 준비한다
