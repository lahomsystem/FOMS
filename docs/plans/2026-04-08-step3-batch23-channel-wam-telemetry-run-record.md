# Step 3 Batch 23 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch22-channel-wam-read-model-run-record.md`

- 일시: 2026-04-08 15:06:57
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_wam_telemetry`를 스물한 번째 실제 `foms/services` source of truth로 이동하고 WAM API가 canonical telemetry helper를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 23 executed, `channel_wam_telemetry` canonical migration completed without intended telemetry behavior changes**

이유:
- `foms/services/channel_wam_telemetry.py`를 새 canonical source로 추가하고, 기존 `services/channel_wam_telemetry.py`는 공개 API를 재수출하는 thin shim으로 전환했다.
- `apps/api/channel_wam.py`가 `record_wam_telemetry`를 canonical path에서 직접 import하도록 정리해 hot path도 shim 경유 없이 canonical namespace를 사용하게 만들었다.
- `tests/test_foms_namespace_imports.py`에 telemetry shim 계약 테스트와 `apps/api/channel_wam.py`의 canonical import 고정 테스트를 추가했다.
- 후감리에서 나온 즉시 수정 가능 항목인 `_safe_int` docstring 부재는 같은 배치 안에서 보강했다.
- `CHANNEL_WAM_TELEMETRY_NS_OK`/`APP_OK`/`verify_result.py --json`/최종 전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 22 완료 직후 자동 전감리 결과:
1. `channel_wam_telemetry`
2. `channel_wam_attachments`
3. `channel_wam_service`

선정 이유:
- `channel_wam_telemetry`는 production caller가 `apps/api/channel_wam.py` 한 곳뿐이어서 blast radius가 가장 작았다.
- DB/스토리지/RQ/외부 presigned URL 발급이 없고 허용 이벤트 화이트리스트 + 로그 기록만 담당해 구조-only 배치로 다루기 쉬웠다.
- `channel_wam_attachments`는 storage 연계와 test monkeypatch 경로가 섞여 있어 다음 단계로 미루는 것이 안전했다.
- `channel_wam_service`는 WAM 허브 오케스트레이션 모듈이라 반경이 가장 커서 후순위가 적절했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_wam_telemetry.py`
  - 기존 telemetry 구현을 canonical 위치로 이동
  - 모듈 docstring 추가
  - 공개 API `__all__` 명시:
    - `ALLOWED_EVENTS`
    - `record_wam_telemetry`
  - `record_wam_telemetry()` docstring 유지
  - 후감리 반영으로 내부 helper `_safe_int()` docstring 추가

### 3.2 legacy shim 전환
- `services/channel_wam_telemetry.py`
  - `ALLOWED_EVENTS`, `record_wam_telemetry`를 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/channel_wam.py`
  - `from services.channel_wam_telemetry import record_wam_telemetry`
  - →
  - `from foms.services.channel_wam_telemetry import record_wam_telemetry`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_wam_telemetry` / `namespaced_channel_wam_telemetry` import 추가
  - `test_legacy_channel_wam_telemetry_shim_preserves_canonical_contract()` 추가
    - `__all__` 일치
    - 공개 심볼 객체 동일성(`is`) 검증
  - `test_channel_wam_api_uses_canonical_telemetry_import()` 추가
    - `apps.api.channel_wam.record_wam_telemetry`가 canonical helper 객체와 동일한지 검증

## 4. 감리 결과 요약
### 4.1 사전 감리
- `channel_wam_service`는 허브 모듈이라 변경 반경이 가장 커 후순위가 적절하다는 판단이 나왔다.
- `channel_wam_attachments`는 storage/presigned URL과 monkeypatch 표면이 있어 telemetry보다 위험도가 높았다.
- `channel_wam_telemetry`는 허용 이벤트 검증 + 로깅만 담당하므로 가장 안전한 다음 slice로 판정됐다.

### 4.2 사후 감리
- high/medium 수준의 회귀·shim drift·보안 이슈는 식별되지 않았다.
- low 수준으로 `_safe_int` docstring 부재, `apps/api/channel_wam.py` import 그룹 혼재, telemetry return 값 미사용 메모가 식별됐다.
- 이 중 즉시 수정 가능한 `_safe_int` docstring은 같은 배치 안에서 바로 보강했다.

## 5. 의도적으로 건드리지 않은 것
- `services/channel_wam_attachments.py`
- `services/channel_wam_service.py`
- `services/channel_wam_read_model.py`
- `apps/api/channel_wam.py` 내부 telemetry 204 응답 정책
- telemetry payload 필드 스키마 자체
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 6. 검증 결과
### 6.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py`
  - 후감리 보강 후 `python -m pytest tests/test_foms_namespace_imports.py tests/test_channel_wam_backend.py`
- 결과:
  - 초기 `51 passed`
  - 후감리 보강 후 `46 passed`

### 6.2 namespace smoke
- 실행: `python -c "import services.channel_wam_telemetry as legacy; import foms.services.channel_wam_telemetry as ns; assert legacy.record_wam_telemetry is ns.record_wam_telemetry; assert legacy.ALLOWED_EVENTS is ns.ALLOWED_EVENTS; print('CHANNEL_WAM_TELEMETRY_NS_OK')"`
- 결과: `CHANNEL_WAM_TELEMETRY_NS_OK`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `270 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `channel_wam_telemetry`는 스물한 번째 실제 `foms/services` source of truth가 되었고, WAM 축의 가장 안전한 leaf helper를 먼저 canonical namespace로 정리했다.
- 이번 배치는 DB/스토리지/오케스트레이션을 건드리지 않고, telemetry helper와 API import 경로만 canonical로 고정해 same-process 원칙을 유지했다.
- 다음 자동 단계에서는 storage 연계가 있는 `channel_wam_attachments`를 다루는 것이 가장 자연스럽고, 그 뒤에 `channel_wam_service` 허브를 정리하는 순서가 안전하다.

## 8. 다음 단계
1. 자동 다음 구조 후보는 `channel_wam_attachments`로 잡고, storage/presigned URL/test monkeypatch 경로를 전감리해 Batch 24 적합성을 판단한다
2. 그 다음 순서는 `channel_wam_service`와 `channel_wam_attachments` 사이의 결합을 고려해 `channel_wam_service` 후순위 유지 여부를 재검토한다
3. 별도 품질 배치로 telemetry route가 unknown event에서 `False`를 반환해도 항상 `204`를 주는 정책을 제품 관점에서 유지할지 검토한다
