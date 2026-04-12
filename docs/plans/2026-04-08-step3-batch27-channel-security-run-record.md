# Step 3 Batch 27 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch26-channel-identity-run-record.md`

- 일시: 2026-04-08 17:22:36
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_security`를 스물다섯 번째 실제 `foms/services` source of truth로 이동하고 WAM/webhook/function/security caller가 canonical path를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 27 executed, `channel_security` canonical migration completed without changing ChannelTalk signature or WAM token semantics**

이유:
- `foms/services/channel_security.py`를 새 canonical source로 추가하고, 기존 `services/channel_security.py`는 공개 helper를 재수출하는 thin shim으로 전환했다.
- `apps/api/channel_wam.py`, `apps/api/channel_functions.py`, `apps/api/channel_webhooks.py`가 security helper를 canonical path에서 직접 import하도록 정리했다.
- `services/channel_policy.py`와 `services/channel_client.py`의 WAM short-link lazy import도 canonical path로 전환했다.
- shim/직접 caller/lazy import 회귀를 잡기 위해 namespace 계약 테스트, security 전용 테스트, push message monkeypatch target, `channel_client` lazy import 테스트를 함께 보강했다.
- `CHANNEL_SECURITY_NS_OK`/`verify_result.py --json`/최종 전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 26 완료 후 자동 전감리 결과:
1. `channel_security`
2. `channel_quick_actions`
3. `channel_policy`

선정 이유:
- `channel_security`는 보안 helper 축이지만 실제 구조 변경 범위는 비교적 선명했다. WAM/webhook/function caller와 short-link lazy import 두 곳만 직접 canonical로 정리하면 되고, 비즈니스 정책/DB 의미론은 건드릴 필요가 없었다.
- identity가 먼저 canonical로 정리된 상태라 WAM/Channel 보조 축을 안전하게 이어붙일 수 있었다.
- `channel_quick_actions`보다 함수 surface가 더 명확하고, storage/ERP display/private helper 결합이 없어 구조-only 배치로 마감하기 쉬웠다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_security.py`
  - 기존 ChannelTalk inbound signature / WAM token helper 구현을 canonical 위치로 이동
  - module docstring 추가
  - `__all__` 명시:
    - `verify_channel_signature`
    - `require_channel_signature`
    - `generate_wam_launch_token`
    - `generate_wam_entry_token`
    - `generate_wam_short_link_token`
    - `generate_wam_session_token`
    - `verify_wam_launch_token`
    - `verify_wam_entry_token`
    - `verify_wam_short_link_token`
    - `verify_wam_session_token`
  - 공개 함수 docstring 추가
  - nonce/serializer/signature/window 처리 의미론은 structure-only 원칙에 따라 유지

### 3.2 legacy shim 전환
- `services/channel_security.py`
  - 공개 helper 10종을 canonical에서 재수출하는 thin shim으로 전환
  - 후감리 low 호환성 메모를 반영해 legacy module object에서 읽히던 주요 상수/serializer(`CHANNEL_SIGNING_KEY`, `SECRET_KEY`, `WAM_DEFAULT_*`, `wam_*_serializer`)를 함께 노출해 module-level read 호환성을 유지

### 3.3 caller canonical import 정리
- `apps/api/channel_wam.py`
  - WAM session/entry/short-link verification helper import를 canonical path로 전환
- `apps/api/channel_functions.py`
  - `require_channel_signature` import를 canonical path로 전환
- `apps/api/channel_webhooks.py`
  - `require_channel_signature` import를 canonical path로 전환
- `services/channel_policy.py`
  - `_build_order_detail_link()` 내부 lazy import를 canonical path로 전환
- `services/channel_client.py`
  - `format_order_message()` 내부 lazy import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace contract
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_security` / `namespaced_channel_security` import 추가
  - `test_legacy_channel_security_shim_preserves_canonical_contract()` 추가
  - `test_channel_wam_api_uses_canonical_security_imports()` 추가
  - `test_channel_functions_api_uses_canonical_security_import()` 추가
  - `test_channel_webhooks_api_uses_canonical_security_import()` 추가

### 4.2 security/lazy import verification
- `tests/test_channel_security.py`
  - canonical import 기준으로 정리
  - `CHANNEL_SIGNING_KEY` monkeypatch target을 canonical module object로 교체
- `tests/test_channel_push_messages.py`
  - `channel_policy`가 legacy shim이 아닌 canonical `generate_wam_short_link_token`을 따라가도록 monkeypatch target을 canonical module object로 교체
- `tests/test_channel_client.py`
  - `test_format_order_message_uses_canonical_short_link_import()` 신규 추가
  - `channel_client` lazy import가 canonical security helper를 실제 사용하는지 검증
- `tests/test_channel_quick_actions.py`
  - security helper import를 canonical path로 전환
- `tests/test_channel_wam_backend.py`
  - WAM token helper import를 canonical path로 전환
- `tests/test_channel_wam_routes.py`
  - WAM token helper import를 canonical path로 전환

## 5. 감리 결과 요약
### 5.1 사전 감리
- `channel_security`는 WAM/webhook/function 보안 축을 닫는 작은 slice로 판정됐다.
- 직접 caller와 lazy import caller가 모두 식별 가능했고, signature/token helper surface가 명확해 thin shim + canonical caller 정리 패턴에 적합했다.

### 5.2 사후 감리
- high/medium 수준의 신규 회귀는 식별되지 않았다.
- 초기 후감리에서 low 수준으로 "legacy shim이 module-level config를 읽는 외부 스크립트에 불리할 수 있다"는 호환성 메모가 나왔고, 이를 반영해 shim에 주요 상수/serializer를 재노출했다.
- 최종 상태 기준으로 신규 lint는 없고, 기존 SQLAlchemy `Query.get()` warning 3건만 지속됐다.

## 6. 의도적으로 건드리지 않은 것
- `channel_security` 내부 nonce 저장 전략(Redis fallback / memory store)
- `SECRET_KEY` fallback 정책 자체
- ChannelTalk replay window 의미론
- `channel_quick_actions` 비즈니스 로직/ERP display private helper 의존
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_channel_security.py tests/test_channel_client.py tests/test_channel_push_messages.py tests/test_channel_quick_actions.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `94 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_security as legacy; import foms.services.channel_security as ns; assert legacy.generate_wam_entry_token is ns.generate_wam_entry_token; assert legacy.CHANNEL_SIGNING_KEY == ns.CHANNEL_SIGNING_KEY; print('CHANNEL_SECURITY_NS_OK')"`
- 결과: `CHANNEL_SECURITY_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `283 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_security`는 스물다섯 번째 실제 `foms/services` source of truth가 되었고, WAM/security 축의 핵심 import 정리가 완료됐다.
- 이제 Channel vertical에서 남은 큰 후보는 `channel_quick_actions`지만, 전감리 결과 DB + storage + `erp_display` private helper 결합 때문에 가장 안전한 다음 배치로는 재선정되지 않았다.
- 동일 기준의 자동 전감리에서는 `order_storage_cleanup`이 caller 1곳의 더 작은 structure-only slice로 평가돼 다음 안전 후보가 됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `order_storage_cleanup`
2. `channel_quick_actions`는 `order_storage_cleanup` 이후에 다시 비교한다
3. 별도 품질 배치에서 `channel_security`의 `SECRET_KEY` fallback 정책, nonce store 예외 처리, `channel_quick_actions`의 private helper 결합을 검토한다
