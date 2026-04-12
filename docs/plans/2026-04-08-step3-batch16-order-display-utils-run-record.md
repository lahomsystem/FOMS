# Step 3 Batch 16 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch15-as-content-safety-run-record.md`

- 일시: 2026-04-08 10:44:50
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `order_display_utils`를 열네 번째 실제 `foms/services` source of truth로 이동하고 주문 목록/휴지통/엑셀 caller를 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 16 executed, `order_display_utils` canonical migration completed without business logic changes**

이유:
- `foms/services/order_display_utils.py`를 새 canonical source로 추가하고, 기존 `services/order_display_utils.py`는 공개 helper 2개만 재수출하는 thin shim으로 전환했다.
- production caller 3곳을 canonical import로 정리했고, legacy 경로는 thin shim 자체와 namespace 계약 테스트만 남겼다.
- helper 전용 테스트가 없던 위험을 줄이기 위해 `tests/test_order_display_utils.py`를 추가해 `_ensure_dict`, direct/online 옵션 표시, 레거시 한글 키, invalid JSON fallback 계약을 고정했다.
- 후감리에서 나온 coverage gap은 같은 배치 안에서 테스트 2건을 추가해 줄였고, broad `except`/`_ensure_dict` 이원화는 별도 품질 리스크로 남겼다.
- `ORDER_DISPLAY_UTILS_NS_OK`/focused tests/`APP_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `order_display_utils`
2. `erp_template_filters`
3. 구조 배치 대신 별도 품질 배치

선정 이유:
- 전감리에서 `order_display_utils`는 caller 3곳, Jinja filter 등록 없음, DB/Flask 결합 없음으로 가장 작은 blast radius를 가진 구조 slice로 판정됐다.
- `erp_template_filters`는 실제 caller는 2곳뿐이지만 Blueprint filter 등록과 ERP 템플릿 계약이 넓어 이번 턴보다 리스크가 컸다.
- 별도 품질 배치 전감리에서는 `services/app_init.py` 기본 관리자 자격 증명 하드코딩, `apps/api/erp_orders_structured.py`의 Channel payload/mark gating 불일치 가능성이 고우선 후보로 식별됐지만, 이번 턴은 사용자 요청대로 Step 3 구조 흐름을 유지하기 위해 구조-only slice를 우선했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/order_display_utils.py`
  - 기존 표시 helper 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `format_options_for_display`
    - `_ensure_dict`

### 3.2 legacy shim 전환
- `services/order_display_utils.py`
  - 위 2개 공개 helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `apps/order_pages.py`
- `apps/order_trash.py`
- `apps/excel_import.py`

각 파일에서:
- `from services.order_display_utils import ...`
- → `from foms.services.order_display_utils import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_order_display_utils` / `namespaced_order_display_utils` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_order_display_utils.py`
  - `_ensure_dict` dict/string/invalid 입력 처리
  - direct 옵션 표시 문자열
  - online 요약 줄바꿈 `'<br>'` 유지 계약
  - 레거시 한글 키 매핑 계약
  - invalid JSON fallback 계약

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외했다.
- 구조 후보 비교에서는 `order_display_utils`가 1순위, `erp_template_filters`가 2순위로 정리됐다.
- 품질 후보 비교에서는 `services/app_init.py` 기본 관리자 자격 증명 하드코딩과 `apps/api/erp_orders_structured.py` Channel mark/update gating 불일치 가능성이 고우선으로 식별됐지만, 별도 품질 배치로 분리하는 방향을 유지했다.
- 따라서 이번 배치는 `order_display_utils` canonical 이동 + shim + caller import 정리 + 계약 테스트 보강까지로 scope를 고정했다.

### 4.2 사후 감리
- 후감리에서 치명적 회귀나 shim/canonical drift는 없다는 판정을 받았다.
- medium 수준 후감리 항목으로 “표시 helper 다수 분기 테스트 부족”, “broad `except Exception` 유지”, “`_ensure_dict`가 `erp_display`와 이원화되어 있음”이 식별됐다.
- 이 중 테스트 coverage gap은 이번 범위 안에서 레거시 한글 키/invalid JSON fallback 테스트를 추가해 줄였고, broad `except` 및 `_ensure_dict` 통합은 별도 품질/정리 후보로 남겼다.

## 5. 의도적으로 건드리지 않은 것
- `services/app_init.py`
- `apps/api/erp_orders_structured.py`
- `services/erp_template_filters.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `format_options_for_display`의 `online_options_summary -> <br>` 렌더링 의미
- `services/channel_quick_actions.py`
- `services/erp_policy.py`
- `app.py`
- `run.py`
- `templates/`
- `static/`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.order_display_utils import|import services\.order_display_utils`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.order_display_utils as legacy; import foms.services.order_display_utils as ns; assert legacy.format_options_for_display is ns.format_options_for_display; assert legacy._ensure_dict is ns._ensure_dict; print('ORDER_DISPLAY_UTILS_NS_OK')"`
- 결과: `ORDER_DISPLAY_UTILS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_order_display_utils.py tests/test_foms_namespace_imports.py`
- 결과: `21 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest`
- 결과: `237 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `order_display_utils`는 열네 번째 실제 `foms/services` source of truth가 되었고, 주문 표시 helper도 Step 3 canonical namespace 안으로 들어왔다.
- 이번 배치는 `apps/order_pages.py`, `apps/order_trash.py`, `apps/excel_import.py`처럼 운영에서 자주 쓰는 경로를 건드렸지만, 변경 범위를 import 정리와 helper 계약 테스트 보강으로 통제했다.
- 전감리에서 새로 포착된 `app_init.py`/`erp_orders_structured.py` 고우선 품질 리스크는 구조-only 범위를 벗어나므로 다음 별도 품질 배치 의제로 유지한다.

## 8. 다음 단계
1. 구조 후보는 `erp_template_filters`와 또 다른 low-risk helper slice를 다시 비교
2. 별도 품질 배치로 `services/app_init.py` 기본 관리자 자격 증명/로깅, `apps/api/erp_orders_structured.py` Channel gating 및 대형 handler 분해를 우선순위화
3. `order_display_utils` broad `except` 축소와 `_ensure_dict` 중복 정리는 위 품질 배치와 묶어 재감리
