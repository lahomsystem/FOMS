# Step 3 Batch 26 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch25-channel-wam-service-run-record.md`

- 일시: 2026-04-08 16:16:43
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_identity`를 스물네 번째 실제 `foms/services` source of truth로 이동하고 Channel/WAM identity caller가 canonical path를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 26 executed, `channel_identity` canonical migration completed without changing manager-link or permission semantics**

이유:
- `foms/services/channel_identity.py`를 새 canonical source로 추가하고, 기존 `services/channel_identity.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- `apps/api/channel_wam.py`가 `get_user_by_manager_id`를 canonical path에서 직접 import하도록 정리했다.
- `services/channel_quick_actions.py`의 lazy import도 `foms.services.channel_identity.is_action_allowed_for_manager`를 직접 바라보도록 전환했다.
- `tests/test_foms_namespace_imports.py`에 identity shim 계약 테스트와 WAM API canonical import 고정 테스트를 추가했고, `tests/test_channel_quick_actions.py`에 lazy import가 canonical 경로를 실제로 쓰는지 검증하는 테스트를 추가했다.
- `CHANNEL_IDENTITY_NS_OK`/`verify_result.py --json`/최종 전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 25 완료 후 자동 전감리 결과:
1. `channel_identity`
2. `channel_security`
3. `channel_quick_actions`

선정 이유:
- `channel_identity`는 약 44줄의 소형 모듈이고, production caller가 `apps/api/channel_wam.py`와 `services/channel_quick_actions.py`의 lazy import 두 곳으로 제한됐다.
- 스토리지/Flask/Redis 없이 DB 읽기와 manager-user mapping 조회만 수행해 structure-only 배치로 옮기기 가장 안전했다.
- `channel_quick_actions`보다 먼저 identity 축을 canonical로 옮기면, 이후 quick actions가 의존하는 identity 경로도 먼저 정리돼 후속 구조 배치가 가벼워진다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_identity.py`
  - 기존 manager identity / action permission helper 구현을 canonical 위치로 이동
  - module docstring 추가
  - `__all__` 명시:
    - `get_user_by_manager_id`
    - `is_action_allowed_for_manager`
  - 기존 동작(광범위 `except Exception`, `action_type` 미사용)은 structure-only 원칙에 따라 유지

### 3.2 legacy shim 전환
- `services/channel_identity.py`
  - 공개 helper 2종을 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/channel_wam.py`
  - `get_user_by_manager_id` import를 canonical path로 전환
- `services/channel_quick_actions.py`
  - `process_foms_command()` 내부 lazy import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace contract
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_identity` / `namespaced_channel_identity` import 추가
  - `test_legacy_channel_identity_shim_preserves_canonical_contract()` 추가
  - `test_channel_wam_api_uses_canonical_identity_import()` 추가

### 4.2 lazy import caller verification
- `tests/test_channel_quick_actions.py`
  - `test_process_foms_command_uses_canonical_identity_import()` 추가
  - `foms.services.channel_identity.is_action_allowed_for_manager`를 monkeypatch해서 `process_foms_command()`가 legacy shim이 아닌 canonical lazy import를 사용하는지 검증

## 5. 감리 결과 요약
### 5.1 사전 감리
- `channel_identity`는 Channel 보조 축 중 가장 작은 안전 단위로 판정됐다.
- 직접 caller가 적고 side effect가 작아 thin shim + caller import 정리 패턴이 잘 맞는 모듈로 평가됐다.

### 5.2 사후 감리
- high/medium 수준의 신규 회귀는 식별되지 않았다.
- low 수준으로 아래 기존 설계 부채가 다시 확인됐다:
  - `get_user_by_manager_id()`의 광범위 `except Exception`
  - `is_action_allowed_for_manager()`에서 `action_type` 미사용
  - `ChannelManagerLink.is_active == True` 스타일
- 모두 기존 의미론 유지 범위로 판단해 이번 structure-only 배치에서는 유지했다.

## 6. 의도적으로 건드리지 않은 것
- `services/channel_security.py`
- `services/channel_quick_actions.py`의 비즈니스 로직/권한 의미론
- `ChannelManagerLink` 스키마/권한 정책 세분화
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py tests/test_channel_quick_actions.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py tests/test_channel_wam_templates.py`
- 결과:
  - `68 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_identity as legacy; import foms.services.channel_identity as ns; assert legacy.get_user_by_manager_id is ns.get_user_by_manager_id; assert legacy.is_action_allowed_for_manager is ns.is_action_allowed_for_manager; print('CHANNEL_IDENTITY_NS_OK')"`
- 결과: `CHANNEL_IDENTITY_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `278 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_identity`는 스물네 번째 실제 `foms/services` source of truth가 되었고, WAM/Channel 보조 축 중 가장 안전한 identity slice 정리가 완료됐다.
- 이제 남은 주요 후보는 `channel_security`와 `channel_quick_actions`인데, 전자는 보안/토큰 영향 범위가 넓고 후자는 ERP display/private helper + storage + identity 결합이 있어 구조 리스크가 더 크다.
- 따라서 다음 Step 3 자동 후보는 `channel_security`, 그 다음이 `channel_quick_actions`로 유지하는 것이 합리적이다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_security`
2. `channel_security` 완료 후에만 `channel_quick_actions`를 다시 평가한다
3. 별도 품질 배치에서 `channel_identity`의 예외 처리 의미론과 `action_type` 세분화를 검토한다
