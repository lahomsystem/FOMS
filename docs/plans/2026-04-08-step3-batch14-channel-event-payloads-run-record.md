# Step 3 Batch 14 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch13-erp-sync-columns-caller-cleanup-run-record.md`

- 일시: 2026-04-08 10:07:00
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_event_payloads`를 열두 번째 실제 `foms/services` source of truth로 이동하고 production caller를 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 14 executed, `channel_event_payloads` canonical migration completed without business logic changes**

이유:
- `foms/services/channel_event_payloads.py`를 새 canonical source로 추가하고, 기존 `services/channel_event_payloads.py`는 공개 빌더 4개만 재수출하는 thin shim으로 전환했다.
- production caller 3곳과 functional test 1곳을 canonical import로 정리했고, legacy 경로는 thin shim 자체와 namespace 계약 테스트만 남겼다.
- `services.erp_policy.STAGE_LABELS` / `constants.STATUS` 의존은 의도적으로 유지해 로직 분해를 섞지 않았다.
- `CHANNEL_EVENT_PAYLOADS_NS_OK`/focused tests/`APP_OK`/`verify_result.py --json`/전체 `pytest -q`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `channel_event_payloads`
2. `as_content_safety`
3. 구조 배치 대신 별도 품질 배치

선정 이유:
- 읽기 전용 감리 결과가 갈렸지만, 이번 Step 3 흐름을 유지하려면 “작은 구조 slice를 하나 더 닫는 선택”이 가장 일관적이었다.
- `channel_event_payloads`는 `erp_policy` 의존이 남아 있으나 호출 fan-out이 작고, worker/queue 직접 caller가 보이지 않아 구조-only 배치로 통제 가능했다.
- `as_content_safety`도 저위험 후보였지만 `orders.py`/AS 페이지 등 최근 hot file과 겹쳤고, 품질 배치 전환은 Step 3 구조 축을 잠시 끊는 선택이어서 이번 턴에는 보류했다.
- 전면 `erp_policy` 이동이나 `channel_quick_actions`는 여전히 고위험이라 제외했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_event_payloads.py`
  - 기존 payload builder 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `build_structured_update_payload`
    - `build_field_change_payload`
    - `build_shipment_update_payload`
    - `build_payment_confirmation_payload`

### 3.2 legacy shim 전환
- `services/channel_event_payloads.py`
  - 위 4개 공개 함수만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/erp_measurement.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_shipment_settings.py`
- `tests/test_channel_push_messages.py`

각 파일에서:
- `from services.channel_event_payloads import ...`
- → `from foms.services.channel_event_payloads import ...`

### 3.4 shim 계약 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_event_payloads` / `namespaced_channel_event_payloads` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외했다.
- 감리 결과는 “품질 배치 전환”과 “`channel_event_payloads` 구조 slice 진행”으로 갈렸고, GDM 판단으로 Step 3 구조 거버넌스 리듬을 유지하는 쪽을 선택했다.
- 이때 `erp_policy`는 건드리지 않고 `STAGE_LABELS` import만 유지하는 staged 원칙을 명시했다.

### 4.2 사후 감리
- 후감리에서 이번 배치는 structure-only 자격을 유지한다는 판정을 받았다.
- low 수준 residual risk로 `foms/services/channel_event_payloads.py`의 긴 함수/공개 함수 docstring 부족, canonical 모듈의 root `constants`/`services.erp_policy` 의존이 재확인됐다.
- 위 항목은 이번 배치에서 새로 만든 로직 문제가 아니라 기존 구현을 그대로 옮긴 구조 부채로 분리했다.

## 5. 의도적으로 건드리지 않은 것
- `services/erp_policy.py`
- `services/channel_quick_actions.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/jobs/*`
- `app.py`
- `run.py`
- `templates/`
- `static/`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.channel_event_payloads import|import services\.channel_event_payloads`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.channel_event_payloads as legacy; import foms.services.channel_event_payloads as ns; assert legacy.build_structured_update_payload is ns.build_structured_update_payload; assert legacy.build_field_change_payload is ns.build_field_change_payload; assert legacy.build_shipment_update_payload is ns.build_shipment_update_payload; assert legacy.build_payment_confirmation_payload is ns.build_payment_confirmation_payload; print('CHANNEL_EVENT_PAYLOADS_NS_OK')"`
- 결과: `CHANNEL_EVENT_PAYLOADS_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_channel_push_messages.py tests/test_foms_namespace_imports.py`
- 결과: `21 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `225 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: import 변경과 무관한 기존 basedpyright 진단이 `apps/api/erp_orders_structured.py`, `apps/api/erp_shipment_settings.py` 등에서 재보고됨
- 해석: 이번 배치에서 새로 추가된 lint는 확인되지 않았고, 기존 타입 진단은 별도 품질 배치로 유지

## 7. 해석
- `channel_event_payloads`는 열두 번째 실제 `foms/services` source of truth가 되었고, 채널 메시지 payload builder도 Step 3 canonical namespace 안으로 들어왔다.
- 이번 배치는 `erp_policy`를 분해하지 않은 staged 구조 정렬이라는 점이 핵심이며, 구조-only 원칙을 지키기 위해 상수/정책 의존은 그대로 두었다.
- 다음 단계는 다시 “저위험 구조 slice 1개 더 진행”과 “품질 배치 전환” 사이를 재비교하는 국면이다.

## 8. 다음 단계
1. 다음 low-risk 구조 후보(`as_content_safety` 등)와 품질 배치 후보를 다시 비교
2. `channel_quick_actions` / 전면 `erp_policy` 이동은 고위험 후보로 계속 감리 보류
3. 별도 품질 배치로 `channel_event_payloads` 긴 함수/docstring, `erp_sync_columns` 타입 힌트/parse fallback, `services/app_init.py` print logging, `erp_shipment_settings` 예외 처리 등을 우선순위화
