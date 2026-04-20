# Step 3 Batch 15 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch14-channel-event-payloads-run-record.md`

- 일시: 2026-04-08 10:16:00
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `as_content_safety`를 열세 번째 실제 `foms/services` source of truth로 이동하고 AS/주문/출고 caller를 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 15 executed, `as_content_safety` canonical migration completed without business logic changes**

이유:
- `foms/services/as_content_safety.py`를 새 canonical source로 추가하고, 기존 `services/as_content_safety.py`는 공개 helper 3개만 재수출하는 thin shim으로 전환했다.
- production caller 4곳을 canonical import로 정리했고, legacy 경로는 thin shim 자체와 namespace 계약 테스트만 남겼다.
- helper 전용 테스트가 없던 위험을 줄이기 위해 `tests/test_as_content_safety.py`를 추가해 sanitize/plain-text/load helper의 현재 계약을 고정했다.
- 후감리에서 나온 low 이슈 중 이번 범위 안에서 무해한 두 건(최소 타입 힌트, invalid JSON negative test)을 같은 배치 안에서 정리했다.
- `AS_CONTENT_SAFETY_NS_OK`/focused tests/`APP_OK`/`verify_result.py --json`/전체 `pytest -q`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `as_content_safety`
2. `order_display_utils`
3. 구조 배치 대신 별도 품질 배치

선정 이유:
- 전감리에서 `as_content_safety`는 `erp_policy`/DB/캘린더와 분리된 작은 helper slice로 판정됐고, Batch 14 시점부터 다음 구조 후보 1순위로 유지됐다.
- `order_display_utils`도 후보였지만, 이번 턴에서는 AS/주문/출고 공통 sanitize helper를 먼저 canonical namespace로 편입하는 편이 현재 열려 있는 Step 3 흐름과 더 잘 맞았다.
- `services/app_init.py`, `apps/api/erp_orders_structured.py` 중심 품질 배치는 영향 범위가 커서 별도 품질 턴으로 분리하는 것이 더 안전했다.
- `channel_quick_actions` / 전면 `erp_policy` 이동은 여전히 고위험이라 제외했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/as_content_safety.py`
  - 기존 sanitize/load helper 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `sanitize_as_content_html`
    - `as_content_html_to_text`
    - `load_structured_data_dict_or_raise`

### 3.2 legacy shim 전환
- `services/as_content_safety.py`
  - 위 3개 공개 함수만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/api/orders.py`
- `apps/api/erp_orders_as.py`
- `apps/erp_as_page.py`
- `apps/erp_shipment_page.py`

각 파일에서:
- `from services.as_content_safety import ...`
- → `from foms.services.as_content_safety import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_as_content_safety` / `namespaced_as_content_safety` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_as_content_safety.py`
  - sanitize 허용 태그/속성 정리
  - plain text 줄바꿈 정규화
  - deep copy load contract
  - non-object JSON / invalid JSON negative case 검증

### 3.5 후감리 low 항목 정리
- `foms/services/as_content_safety.py`
  - 공개/비공개 helper에 최소 타입 힌트 추가
- `tests/test_as_content_safety.py`
  - invalid JSON 문자열 예외 전파 테스트 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외했다.
- 전감리 두 갈래 모두 `as_content_safety`를 다음 구조 배치 1순위로 추천했고, 고위험 품질 파일(`app_init.py`, `erp_orders_structured.py`)은 별도 품질 턴으로 미루는 것이 맞다는 결론이 나왔다.
- 따라서 이번 배치는 `as_content_safety` canonical 이동 + shim + caller import 정리 + 계약 테스트 보강까지로 scope를 고정했다.

### 4.2 사후 감리
- 후감리에서 이번 배치는 structure-only 자격을 유지한다는 판정을 받았다.
- low 수준 residual risk로 “신규 canonical 함수 타입 힌트 부족”, “invalid JSON negative case 테스트 공백”이 식별됐고, 두 항목 모두 이번 범위 안에서 무해하게 정리했다.
- 그 외 남은 품질 이슈는 기존 hot path (`orders.py`, `erp_orders_structured.py`, `app_init.py`) 중심 separate quality batch로 유지했다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/order_display_utils.py`
- `services/erp_template_filters.py`
- `services/app_init.py`
- `apps/api/erp_orders_structured.py` 내부 로직
- `services/channel_quick_actions.py`
- `services/erp_policy.py`
- `app.py`
- `run.py`
- `templates/`
- `static/`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.as_content_safety import|import services\.as_content_safety`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.as_content_safety as legacy; import foms.services.as_content_safety as ns; assert legacy.sanitize_as_content_html is ns.sanitize_as_content_html; assert legacy.as_content_html_to_text is ns.as_content_html_to_text; assert legacy.load_structured_data_dict_or_raise is ns.load_structured_data_dict_or_raise; print('AS_CONTENT_SAFETY_NS_OK')"`
- 결과: `AS_CONTENT_SAFETY_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_as_content_safety.py tests/test_foms_namespace_imports.py`
- 결과: `20 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `231 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `as_content_safety`는 열세 번째 실제 `foms/services` source of truth가 되었고, AS rich text sanitize/load helper도 Step 3 canonical namespace 안으로 들어왔다.
- 이번 배치는 `orders.py`, `erp_orders_as.py`, `erp_as_page.py`, `erp_shipment_page.py`처럼 운영 민감 경로를 건드렸지만, 변경 범위를 import 정리와 계약 테스트 보강으로 통제했다.
- 다음 단계는 다시 “저위험 구조 slice 1개 더 진행”과 “별도 품질 배치 전환” 사이를 재비교하는 국면이다.

## 8. 다음 단계
1. 다음 low-risk 구조 후보(`order_display_utils`, `erp_template_filters` 등)와 품질 배치 후보를 다시 비교
2. `channel_quick_actions` / 전면 `erp_policy` 이동은 고위험 후보로 계속 감리 보류
3. 별도 품질 배치로 `channel_event_payloads` 긴 함수/docstring, `services/app_init.py` logging, `erp_orders_structured.py` 대형 경로, `erp_shipment_settings` 예외 처리 등을 우선순위화
