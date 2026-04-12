# Step 3 Batch 37 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch36-order-date-sync-run-record.md`

- 일시: 2026-04-10 12:22:20
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_policy`를 서른다섯 번째 실제 `foms/services` source of truth로 이동하고 routing/template caller import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 37 executed, `channel_policy` canonical migration completed without changing ChannelTalk routing/template behavior**

이유:
- `foms/services/channel_policy.py`를 새 canonical source로 추가하고, 기존 `services/channel_policy.py`는 thin shim으로 전환했다.
- `services/channel_dispatch.py`와 `services/channel_delivery.py`가 routing helper를 canonical path에서 바라보도록 정리했다.
- focused tests, namespace smoke, `APP_OK`, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 36 완료 후 자동 전감리 결과:
1. `channel_policy`
2. `erp_permissions`
3. `channel_delivery`

선정 이유:
- ChannelTalk stack 안에서 routing/template 정책을 담당하는 좁은 leaf module이라 source of truth 이동 범위를 고정하기 쉬웠다.
- import 시 DB/session/storage singleton을 만들지 않고, WAM short-link token import도 함수 내부 lazy import라 구조-only 이동 리스크가 낮았다.
- `channel_client`가 이미 canonicalized된 상태라 `channel_policy`를 이어서 정리하면 channel stack의 얇은 정책층을 먼저 고립할 수 있었다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_policy.py`
  - `DEDUPE_WINDOWS`, message block/template builder, routing group resolution, attachment cap, push/resend/inbound policy helper를 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - 기존 의미론 유지:
    - `_build_order_detail_link()`의 WAM short-link lazy import + fallback URL
    - event type별 rich block/plain text template 구성
    - `CHANNEL_GROUP_MEASUREMENT` / `CHANNEL_GROUP_AS` 기반 routing
    - attachment cap 10개, resend/inbound policy 기본 규칙

### 3.2 legacy shim 전환
- `services/channel_policy.py`
  - 공개 helper와 `DEDUPE_WINDOWS`만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `services/channel_dispatch.py`
  - policy helper import를 canonical path로 전환
- `services/channel_delivery.py`
  - routing helper lazy import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_policy` / `namespaced_channel_policy` import 추가
  - `test_legacy_channel_policy_shim_preserves_canonical_contract()` 추가
  - `test_channel_dispatch_uses_canonical_channel_client_imports()`에서 policy binding 검증 보강
  - `test_channel_delivery_uses_canonical_channel_policy_lazy_import()` 추가

### 4.2 focused behavior verification
- `tests/test_channel_policy.py`
  - `test_apply_attachment_policy_caps_to_ten_items()` 추가
  - `test_resolve_push_policy_uses_as_urgent_group_and_zero_dedupe()` 추가
  - `test_resolve_inbound_policy_honors_allowed_groups()` 추가
- `tests/test_channel_push_messages.py`
  - 기존 push/template 회귀 테스트가 canonical `channel_policy`를 직접 바라보도록 import 정렬

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `channel_policy` 내부 broad `except` 기반 short-link fallback은 기존 동작 그대로 유지했다.
  - `channel_dispatch`/`channel_delivery`는 아직 legacy module 위치에 남아 있고 이번 배치에서는 caller import path만 정리했다.
  - 자동 전감리 broad inventory는 `erp_permissions`를 낮은 결합 후보로 보았지만, post-batch risk review 기준 다음 small-slice 후보는 `channel_dispatch`가 더 자연스럽다고 정리됐다.

### 5.2 residual gap
- `channel_policy`의 WAM short-link failure 분기 자체를 직접 검증하는 별도 단위 테스트는 이번 배치에 추가하지 않았다.
- ChannelTalk stack 전체(`channel_dispatch`, `channel_delivery`, `channel_quick_actions`)를 한 번에 묶지 않고 policy leaf만 구조 정리했다.

## 6. 의도적으로 건드리지 않은 것
- ChannelTalk 메시지 문구/라우팅 정책 자체
- `channel_dispatch`의 전송/DB/outbox 동작
- `channel_delivery`의 pending/outbox 영속화 semantics
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `pytest tests/test_channel_policy.py tests/test_channel_push_messages.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `73 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_policy as legacy; import foms.services.channel_policy as ns; assert legacy.DEDUPE_WINDOWS == ns.DEDUPE_WINDOWS; assert legacy.build_message_blocks is ns.build_message_blocks; assert legacy.get_routing_group_id is ns.get_routing_group_id; assert legacy.build_message_template is ns.build_message_template; assert legacy.apply_attachment_policy is ns.apply_attachment_policy; assert legacy.get_policy_version is ns.get_policy_version; assert legacy.resolve_push_policy is ns.resolve_push_policy; assert legacy.resolve_resend_policy is ns.resolve_resend_policy; assert legacy.resolve_inbound_policy is ns.resolve_inbound_policy; print('CHANNEL_POLICY_NS_OK')"`
- 결과: `CHANNEL_POLICY_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `pytest`
- 결과: `345 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_policy`는 서른다섯 번째 실제 `foms/services` source of truth가 되었고 ChannelTalk routing/template 정책 로직이 canonical 모듈 한 곳으로 모였다.
- `channel_dispatch`/`channel_delivery`는 policy helper를 canonical import로 참조하게 되어 다음 channel stack 구조 배치를 위한 정렬이 선행됐다.
- 자동 다음 구조 후보는 `channel_dispatch`로 정리했고, 비교 후보는 `erp_permissions`, `channel_delivery` 순으로 유지한다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `channel_dispatch`
2. 그 다음 비교 후보는 `erp_permissions`
3. `channel_delivery`는 outbox/DB 결합이 더 넓어 한 단계 뒤로 유지
