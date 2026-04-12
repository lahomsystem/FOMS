# Step 3 Batch 34 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch33-estimate-service-run-record.md`

- 일시: 2026-04-10 12:08:34
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_client`를 서른두 번째 실제 `foms/services` source of truth로 이동하고 ChannelTalk caller 3곳의 import를 canonical path로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 34 executed, `channel_client` canonical migration completed without changing ChannelTalk client behavior**

이유:
- `foms/services/channel_client.py`를 새 canonical source로 추가하고, 기존 `services/channel_client.py`는 thin shim으로 전환했다.
- `services/channel_dispatch.py`, `apps/api/channel_integration.py`, `services/jobs/tasks.py`의 direct/lazy import를 canonical path로 정리했다.
- 토큰 캐시/락이 모듈 전역 상태를 쓰는 구조라 구현 body를 한 곳에만 유지해 이중 캐시/이중 lock 리스크를 피했다.
- focused tests, namespace smoke, `verify_result.py --json`, 전체 `pytest`, lint를 모두 재통과했다.

## 2. 선정 근거
Batch 33 완료 후 자동 전감리 결과:
1. `channel_client`
2. `order_attachment_thumbnail`
3. `order_date_sync`

선정 이유:
- caller surface가 작고 (`channel_dispatch`, `channel_integration`, worker lazy import 1곳) 구조-only 이동 범위를 고정하기 쉬웠다.
- import 시 network call은 발생하지 않고 env read + lock/cache 초기화만 수행해 부팅 시 부수효과가 제한적이었다.
- 이미 `format_order_message()` 내부 lazy import가 `foms.services.channel_security`를 바라보고 있어 namespace 방향과 정합성이 있었다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_client.py`
  - ChannelTalk Native Functions client 구현을 canonical 위치로 이동
  - module docstring, `__future__`, 타입 힌트, `__all__` 추가
  - 기존 의미론 유지:
    - env 기반 설정 상수
    - `_token_cache` + `_token_lock` 기반 access token 캐시
    - `format_order_message()` short-link fallback
    - `send_group_message()` success / API error / exception fallback 경로

### 3.2 legacy shim 전환
- `services/channel_client.py`
  - 공개 설정 상수와 helper만 재수출하는 thin shim으로 전환
  - private helper (`_issue_token`, `_get_access_token`, `_token_cache` 등)는 canonical 모듈에만 남김

### 3.3 caller canonical import 정리
- `services/channel_dispatch.py`
  - `get_attachment_category_for_status`, `send_group_message` import를 canonical path로 전환
- `apps/api/channel_integration.py`
  - `is_configured` import를 canonical path로 전환
- `services/jobs/tasks.py`
  - `push_order_to_channeltalk()` 내부 lazy import를 canonical path로 전환

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_client` / `namespaced_channel_client` import 추가
  - `test_legacy_channel_client_shim_preserves_canonical_contract()` 추가
  - `test_channel_dispatch_uses_canonical_channel_client_imports()` 추가
  - `test_channel_integration_uses_canonical_channel_client_import()` 추가
  - `test_tasks_use_canonical_channel_client_lazy_import()` 추가

### 4.2 focused behavior verification
- `tests/test_channel_client.py`
  - canonical module을 직접 검증하도록 정렬
  - `test_format_order_message_uses_canonical_short_link_import()` 유지
  - `test_get_access_token_reuses_cached_token()` 추가
  - `test_send_group_message_skips_without_group_id()` 추가
  - `test_send_group_message_returns_message_id_on_success()` 추가
  - `test_send_group_message_raises_runtime_error_when_api_returns_error_and_flag_enabled()` 추가
  - `test_send_group_message_returns_failure_when_api_returns_error_without_raise()` 추가

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - legacy shim은 private helper를 재수출하지 않으므로 외부 스크립트가 `services.channel_client._get_access_token` 같은 비공개 심볼에 의존하면 깨질 수 있음
  - `send_group_message()` 길이가 프로젝트 가이드라인 50줄을 약간 넘음
  - `format_order_message()`의 broad `except Exception`은 기존 설계대로 유지됨
  - `tasks` lazy import 검증은 `inspect.getsource` 문자열 매칭이라 구조는 맞지만 테스트가 다소 취약함

### 5.2 residual gap
- 실제 ChannelTalk sandbox/실 API 호출 smoke는 이번 배치 범위에 포함하지 않았다.
- env snapshot이 import 시점에 고정되는 기존 특성은 그대로 유지했다.

## 6. 의도적으로 건드리지 않은 것
- ChannelTalk business routing policy 자체
- `FOMS_BASE_URL` fallback 정책
- private helper 공개 범위 확대
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_channel_client.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `61 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.channel_client as legacy; import foms.services.channel_client as ns; assert legacy.send_group_message is ns.send_group_message; assert legacy.is_configured is ns.is_configured; print('CHANNEL_CLIENT_NS_OK')"`
- 결과: `CHANNEL_CLIENT_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `328 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `channel_client`는 서른두 번째 실제 `foms/services` source of truth가 되었고 ChannelTalk client caller 정리가 완료됐다.
- `channel_client`의 env/cache 전역 상태는 canonical 모듈 한 곳에만 남겨 duplicate token cache 리스크를 피했다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `order_attachment_thumbnail`이다.
- 그 다음 비교 후보는 `order_date_sync`, `channel_dispatch` 순으로 재정렬됐다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `order_attachment_thumbnail`
2. 그 다음 비교 후보는 `order_date_sync`
3. `channel_dispatch`는 caller와 Channel outbox 경로가 더 넓어서 한 단계 뒤로 유지
