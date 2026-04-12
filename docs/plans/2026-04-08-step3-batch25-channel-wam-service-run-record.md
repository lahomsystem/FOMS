# Step 3 Batch 25 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch24-channel-wam-attachments-run-record.md`

- 일시: 2026-04-08 15:56:24
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_wam_service`를 스물세 번째 실제 `foms/services` source of truth로 이동하고 WAM API가 canonical WAM service helper를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 25 executed, `channel_wam_service` canonical migration completed without changing WAM bootstrap/page behavior**

이유:
- `foms/services/channel_wam_service.py`를 새 canonical source로 추가하고, 기존 `services/channel_wam_service.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- `apps/api/channel_wam.py`가 WAM service helper들을 canonical path에서 직접 import하도록 정리해 hot path도 shim 경유 없이 canonical namespace를 사용하게 만들었다.
- `tests/test_foms_namespace_imports.py`에 WAM service shim 계약 테스트와 API canonical import 고정 테스트를 추가했고, WAM service 내부가 canonical read model / attachments helper를 바인딩하는지 검증도 canonical module 기준으로 정리했다.
- 후감리에서 바로 해결 가능한 공개 함수 docstring과 import 가독성은 같은 배치 안에서 보강했다.
- `CHANNEL_WAM_SERVICE_NS_OK`/`APP_OK`/`verify_result.py --json`/최종 전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 24 완료 직후 자동 전감리 결과:
1. `channel_wam_service`
2. `channel_quick_actions`
3. 구조 배치 잠시 보류 후 품질 배치 분리

선정 이유:
- WAM leaf 축(`view_models`, `read_model`, `telemetry`, `attachments`)이 이미 canonicalized된 상태라, `channel_wam_service`는 Step 3 WAM 축에서 남은 마지막 허브 모듈이었다.
- 직접 production caller가 사실상 `apps/api/channel_wam.py` 한 곳으로 좁아, 허브 모듈이긴 해도 import 정리 표면은 제한적이었다.
- `channel_quick_actions`는 DB/storage/ERP display 의존과 caller 폭이 더 넓어 다음 safest라기보다 후속 구조 슬라이스에 가깝다고 판단했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_wam_service.py`
  - 기존 WAM page/bootstrap orchestration 구현을 canonical 위치로 이동
  - 모듈 docstring 추가
  - 공개 API `__all__` 명시:
    - `get_wam_feature_flags`
    - `build_wam_request_context`
    - `build_wam_page`
    - `build_wam_bootstrap`
    - `build_legacy_wam_context`
    - `build_legacy_summary`
    - `build_legacy_attachments`
  - 구조-only 원칙에 따라 `services.channel_quick_actions` 의존은 유지
  - 후감리 반영:
    - 공개 함수 docstring 추가
    - import 가독성 정리 (`foms.services.*` 묶음 뒤에 남은 legacy `channel_quick_actions`)

### 3.2 legacy shim 전환
- `services/channel_wam_service.py`
  - public WAM service helper 7종을 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/channel_wam.py`
  - `from services.channel_wam_service import ...`
  - →
  - `from foms.services.channel_wam_service import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `import foms.services.channel_wam_service as namespaced_channel_wam_service` 추가
  - `test_legacy_channel_wam_service_shim_preserves_canonical_contract()` 추가
  - `test_channel_wam_api_uses_canonical_service_import()` 추가
  - 기존 WAM service 내부 binding 테스트를 legacy shim이 아닌 canonical service module 기준으로 정리:
    - `test_channel_wam_service_uses_canonical_read_model_import()`
    - `test_channel_wam_service_uses_canonical_attachments_import()`

## 4. 감리 결과 요약
### 4.1 사전 감리
- `channel_wam_service`는 허브·대형 모듈이라 위험도는 medium으로 판정됐지만, WAM 구조 슬라이스를 닫기 위해서는 가장 일관된 다음 후보라는 의견이 우세했다.
- 핵심 안전장치는 caller import를 `apps/api/channel_wam.py` 한 곳만 정리하고, 나머지는 shim + namespace contract 테스트로 고정하는 것이었다.

### 4.2 사후 감리
- high 수준의 회귀·shim drift는 식별되지 않았다.
- medium 수준으로 canonical WAM service가 여전히 `services.channel_quick_actions`에 의존하는 점, 그리고 허브 모듈의 함수 길이/정책 부채가 식별됐다.
- low 수준으로 공개 함수 docstring 부재와 import 가독성이 식별돼, 이 중 즉시 수정 가능한 항목은 같은 배치 안에서 바로 보강했다.
- `category` vs `category_label` preview 필드 의미 차이는 기존 계약 차이로 판단해 이번 구조-only 배치에서는 유지했다.

## 5. 의도적으로 건드리지 않은 것
- `services/channel_quick_actions.py`
- `services/channel_identity.py`
- `services/channel_security.py`
- WAM bootstrap payload/attachments API의 클라이언트 계약 자체
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 6. 검증 결과
### 6.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py tests/test_channel_wam_templates.py`
  - 후감리 보강 후 동일 focused suite 재실행
- 결과:
  - 초기 `58 passed`
  - 후감리 보강 후 `58 passed`

### 6.2 namespace smoke
- 실행: `python -c "import services.channel_wam_service as legacy; import foms.services.channel_wam_service as ns; assert legacy.build_wam_page is ns.build_wam_page; assert legacy.build_wam_bootstrap is ns.build_wam_bootstrap; assert legacy.get_wam_feature_flags is ns.get_wam_feature_flags; print('CHANNEL_WAM_SERVICE_NS_OK')"`
- 결과: `CHANNEL_WAM_SERVICE_NS_OK`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `275 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `channel_wam_service`는 스물세 번째 실제 `foms/services` source of truth가 되었고, Step 3의 WAM 허브 축 canonicalization까지 완료됐다.
- 이번 배치로 WAM vertical slice는 `apps/api/channel_wam.py` caller까지 canonical path를 직접 사용하는 상태가 되었고, legacy `services/channel_wam_service.py`는 pure shim으로만 남는다.
- 다만 canonical WAM service가 여전히 `services.channel_quick_actions`에 의존하므로, WAM/Channel 축 전체가 완전히 `foms.services.*`로 닫힌 것은 아니다. 이건 후속 구조 배치로 분리하는 것이 안전하다.

## 8. 다음 단계
1. 자동 다음 구조 후보는 `channel_identity`를 가장 안전한 next slice로 두고, 그 다음 `channel_security`, `channel_quick_actions` 순으로 전감리한다
2. `channel_quick_actions`는 storage/ERP display 의존이 있는 만큼, `channel_identity` / `channel_security`보다 후순위로 유지한다
3. 별도 품질 배치에서 `channel_wam_service`의 대형 함수 분리와 첨부 preview 계약(`category` vs `category_label`) 정합성을 검토한다
