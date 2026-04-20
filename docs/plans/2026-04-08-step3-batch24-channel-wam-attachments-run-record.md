# Step 3 Batch 24 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch23-channel-wam-telemetry-run-record.md`

- 일시: 2026-04-08 15:20:38
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_wam_attachments`를 스물두 번째 실제 `foms/services` source of truth로 이동하고 WAM API/WAM service가 canonical attachment helper를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 24 executed, `channel_wam_attachments` canonical migration completed without changing attachment access behavior**

이유:
- `foms/services/channel_wam_attachments.py`를 새 canonical source로 추가하고, 기존 `services/channel_wam_attachments.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- `apps/api/channel_wam.py`와 `services/channel_wam_service.py`가 attachment helper를 canonical path에서 직접 import하도록 정리해 hot path도 shim 경유 없이 canonical namespace를 사용하게 만들었다.
- `tests/test_channel_wam_backend.py`의 storage monkeypatch target을 runtime이 실제 참조하는 canonical module로 갱신해 테스트/런타임 정합성을 맞췄다.
- `tests/test_foms_namespace_imports.py`에 attachment shim 계약 테스트와 API/service canonical import 고정 테스트를 추가했다.
- 후감리에서 나온 즉시 수정 가능 항목인 공개 함수 docstring 부재와 인라인 상수는 같은 배치 안에서 보강했다.
- `CHANNEL_WAM_ATTACHMENTS_NS_OK`/`APP_OK`/`verify_result.py --json`/최종 전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 23 완료 직후 자동 전감리 결과:
1. `channel_wam_attachments`
2. `channel_wam_service`

선정 이유:
- `channel_wam_attachments`는 storage와 presigned URL 연동이 있지만 역할이 leaf helper에 가깝고, caller가 `apps/api/channel_wam.py`와 `services/channel_wam_service.py` 두 곳으로 제한돼 있었다.
- `channel_wam_service`는 WAM 허브 오케스트레이션 모듈이라 attachment/read model/view model까지 여러 축을 묶는 중심축이어서 후순위가 적절했다.
- 이번 배치는 monkeypatch target만 함께 조정하면 구조-only로 닫을 수 있는 마지막 비교적 안전한 WAM slice였다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_wam_attachments.py`
  - 기존 attachment grouping/scoping/presigned URL 구현을 canonical 위치로 이동
  - 모듈 docstring 추가
  - 공개 API `__all__` 명시:
    - `get_scoped_attachment`
    - `list_attachment_groups`
    - `resolve_attachment_redirect_url`
  - `services.storage` import는 의도적으로 유지
  - 후감리 반영:
    - `ATTACHMENT_URL_EXPIRES_IN_SECONDS = 300`
    - `GROUP_SORT_FALLBACK_PRIORITY = 999`
    - 공개 함수 docstring 추가

### 3.2 legacy shim 전환
- `services/channel_wam_attachments.py`
  - `get_scoped_attachment`, `list_attachment_groups`, `resolve_attachment_redirect_url`를 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/channel_wam.py`
  - attachment helper 3종 import를 canonical path로 전환
- `services/channel_wam_service.py`
  - `list_attachment_groups` import를 canonical path로 전환

### 3.4 테스트 보강
- `tests/test_channel_wam_backend.py`
  - `monkeypatch.setattr("services.channel_wam_attachments.get_storage", ...)`
  - →
  - `monkeypatch.setattr("foms.services.channel_wam_attachments.get_storage", ...)`
  - 총 4개 patch target 갱신
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_wam_attachments` / `namespaced_channel_wam_attachments` import 추가
  - `test_legacy_channel_wam_attachments_shim_preserves_canonical_contract()` 추가
  - `test_channel_wam_api_uses_canonical_attachments_import()` 추가
  - `test_channel_wam_service_uses_canonical_attachments_import()` 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- attachment helper는 storage 의존이 있지만 WAM 허브 모듈보다는 안전한 다음 slice라는 판단이 유지됐다.
- 핵심 주의점은 import path 정리 이후 tests monkeypatch target이 runtime module과 어긋나지 않게 맞추는 것이었다.

### 4.2 사후 감리
- high/medium 수준의 회귀·shim drift·monkeypatch/runtime mismatch는 식별되지 않았다.
- low 수준으로 공개 함수 docstring 부재, 만료시간/정렬 폴백 매직 넘버, namespace test의 API 모듈 직접 import 패턴이 식별됐다.
- 이 중 즉시 수정 가능한 docstring/상수는 같은 배치 안에서 바로 보강했다.

## 5. 의도적으로 건드리지 않은 것
- `services/storage.py`
- `services/channel_wam_service.py` 내부 오케스트레이션 로직
- `apps/api/channel_wam.py`의 attachment 응답 구조/상태 코드 정책
- attachment category/title 정책
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 6. 검증 결과
### 6.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py`
  - 후감리 보강 후 동일 focused suite 재실행
- 결과:
  - 초기 `54 passed`
  - 후감리 보강 후 `54 passed`

### 6.2 namespace smoke
- 실행: `python -c "import services.channel_wam_attachments as legacy; import foms.services.channel_wam_attachments as ns; assert legacy.list_attachment_groups is ns.list_attachment_groups; assert legacy.get_scoped_attachment is ns.get_scoped_attachment; assert legacy.resolve_attachment_redirect_url is ns.resolve_attachment_redirect_url; print('CHANNEL_WAM_ATTACHMENTS_NS_OK')"`
- 결과: `CHANNEL_WAM_ATTACHMENTS_NS_OK`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest`
- 결과: `273 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `channel_wam_attachments`는 스물두 번째 실제 `foms/services` source of truth가 되었고, WAM leaf helper 축의 구조 정리가 telemetry 다음 단계까지 이어졌다.
- 이번 배치의 핵심은 import path만 옮기는 것이 아니라, runtime module에 맞게 monkeypatch target도 함께 옮겨 테스트/실행 경로를 일치시킨 점이다.
- 이제 WAM 축에서 남은 큰 구조 후보는 `channel_wam_service` 허브로 좁혀졌고, 위험도는 이전 배치들보다 높아졌다.

## 8. 다음 단계
1. 자동 다음 구조 후보는 `channel_wam_service`로 잡고, WAM read model/attachments/view models와의 결합 반경을 먼저 전감리한다
2. `channel_wam_service`가 허브 모듈이라면 Step 3 마지막 WAM slice인지, 아니면 별도 승인형 quality/refactor 배치로 분리할지 결정한다
3. 별도 품질 배치로 attachment helper와 telemetry helper의 docstring/상수 규칙을 더 넓게 통일할지 검토한다
