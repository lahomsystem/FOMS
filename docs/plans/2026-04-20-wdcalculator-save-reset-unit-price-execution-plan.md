# WDCalculator 저장 상태 리셋 + 단가 표기 실행 계획

작성일: 2026-04-20  
계획서 보강일: 2026-04-20  
상태: Ready for execution  
방식: GDM 총괄 / Root Cause Fix Only

## 1. 목표

WDCalculator에서 아래 2개를 한 배치로 정리한다.

1. 견적 저장 후에도 수정 모드가 유지되어 다음 저장이 기존 견적 덮어쓰기로 이어지는 문제를 근본 수정한다.
2. 사용자가 실제 적용 단가를 즉시 볼 수 있도록 현재 견적 / 진행 중인 견적 / 저장된 견적에 단가 표기를 추가한다.

이번 배치는 단순 UI 문구 추가가 아니라, **상태 전이와 견적 표시 계약을 같이 정리하는 기능 배치**로 본다.

## 2. 현상과 근본 원인

### 2-1. 저장 후 신규 입력 상태로 돌아오지 않음

현재 코드 기준:

- [estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
  - `WdCalculatorLoadSavedEstimateToForm.loadEstimateToForm()`
    - `setCurrentDatabaseEstimateId(estimate.id)` 호출
    - 헤더를 `견적 수정: ... 수정모드`로 변경
  - `WdCalculatorSaveEstimate.handleSaveEstimate()`
    - `estimate_id: getCurrentDatabaseEstimateId()` 로 저장 요청 전송
  - `WdCalculatorRefreshAfterSave.refreshAfterSave()`
    - `resetInputFormKeepCustomerName()` 호출
  - `WdCalculatorResetInputFormKeepCustomer.resetInputFormKeepCustomerName()`
    - `setEditingEstimateId(null)`만 수행
    - `currentDatabaseEstimateId`는 초기화하지 않음
    - 수정모드 헤더/배지/새 견적 버튼 상태도 완전히 복구하지 않음

즉, **저장 이후 로컬 편집 상태 일부만 초기화되고 DB 대상 견적 ID는 남는 상태**라서, 사용자는 새 견적이라고 생각하고 저장해도 기존 DB 견적을 업데이트하게 된다.

### 2-2. 단가가 결과와 리스트에 보이지 않음

현재 단가는 데이터상 이미 계산 가능하다.

- [primary-form.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/primary-form.js)
  - `baseComponents`
  - `manualPricing`
  - `productId`
- [pricing-core.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/pricing-core.js)
  - `manualPricing.pricing_type`
  - `price_30cm`, `price_1cm`, `price_1m`
  - 제품 선택 시 `product.pricing_type`, `product.price_30cm`, `product.price_1cm`, `product.price_1m`
- [estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
  - 진행 중 견적 카드 렌더
  - 저장된 견적 사이드바 렌더

즉, 문제는 데이터 부재가 아니라 **적용 단가를 공통 방식으로 요약해 표시하는 헬퍼와 UI 슬롯이 없다**는 점이다.

### 2-3. 서버/API 계약 (방어 심층, 스키마 변경 없음)

클라이언트에서 `currentDatabaseEstimateId`를 null로 맞추는 것과 별개로, **저장 요청이 신규 row인지 갱신인지는 서버 규칙이 최종이다.** 구현 착수 시 아래를 코드로 확인하고, 본 문서 또는 구현 메모에 **한 줄로 기록**한다.

- 저장 라우트(또는 `handleSaveEstimate`가 호출하는 엔드포인트)에서 `estimate_id`(또는 동등 필드) **유무**가 insert vs update를 어떻게 가르는지
- 클라이언트가 의도적으로 `estimate_id`를 보내지 않거나 null인 경우 **항상 신규 생성**인지, 검증 오류인지

이번 배치는 **저장 API 스키마 대수술 없음**(§3 미포함)이므로, 불일치가 발견되면 **최소 확인·주석·프론트 상태 정합**만으로 해결 가능한지 먼저 판단한다. 서버 변경이 필요하면 별도 스코프로 분리한다.

## 3. 범위

### 이번 배치에 포함

1. 저장 후 완전한 신규 입력 상태 복귀
2. 진행 중 견적 수정 적용 후에도 완전한 신규 입력 상태 복귀
3. `기본 견적:` 우측 단가 표기
4. 진행 중 견적 카드 단가 표기
5. 저장된 견적 사이드바 단가 표기
6. `진행 중인 견적` 우측 단가 표기 on/off 버튼

### 이번 배치에 미포함

1. WDCalculator bootstrap 성능 리팩터 추가 변경
2. 저장 API 스키마 대수술
3. ERP/주문 성능 배치 재수정

## 4. 요구사항 해석

### 4-1. “완전한 신규 입력 상태”

이번 계획에서는 아래를 신규 입력 상태로 정의한다.

1. `editingEstimateId = null`
2. `currentDatabaseEstimateId = null`
3. 수정모드 헤더/배지 제거
4. `resetEstimateBtn` 제거 또는 숨김
5. 진행 중 견적 로컬 리스트 비움
6. 기본 구성/추가 옵션/비고/가격 표시 초기화
7. 고객명도 빈 값으로 초기화
8. 쿠폰/배송비는 화면 기본값으로 복귀

즉, 기존의 `resetInputFormKeepCustomerName()` 같은 “부분 초기화”가 아니라, **신규 견적 작성 기준으로 완전 리셋**이 되어야 한다.

### 4-2. 단가 표기 규칙

적용 단가는 저장 필드 추가보다 **기존 estimate/baseComponents/product 데이터에서 파생**하는 것을 우선한다.

표시 규칙:

1. 단일 기본 구성 1개면 단일 단가 문자열로 표시
2. 복합 기본 구성 2개 이상이면 component별 단가 요약 chip/list로 표시
3. 선택 모드:
   - `1m` 제품이면 `1m 330,000원` 형식
   - `30cm` 제품이면 `30cm 187,000원 / 1cm 623원` 형식
4. 직접입력 모드:
   - `manualPricing` 기준으로 동일 규칙
5. 레거시 저장 견적처럼 단가 원천이 부족하면 `단가 정보 없음`으로 숨기거나 muted fallback 처리

**표기 예시의 숫자**(예: 330,000원)는 **형식·자릿수 구분을 보여주는 예시**이며, 화면에 박는 하드코딩 금지 대상이 아니다. 실제 금액은 항상 카탈로그·`manualPricing`·저장된 estimate에서 파생한다.

### 4-3. 토글 규칙

`진행 중인 견적` 헤더 우측에 `단가 표시 ON/OFF` 토글 버튼을 둔다.

권장 동작:

1. 기본값은 `ON`
2. 토글은 진행 중 견적 카드 + 저장된 견적 사이드바의 단가 메타 표시를 함께 제어
3. 현재 “견적 결과” 박스의 `기본 견적:` 우측 단가 표시는 항상 노출
4. 토글 상태는 세션 중 유지, `localStorage` 권장
5. **저장 키 고정(충돌 방지)**: `foms.wdcalculator.unitPriceMetaVisible` (값: `"1"` / `"0"` 또는 `true`/`false` 문자열 중 하나로 일관). 다른 WD 설정 키와 네임스페이스를 맞춘다.

### 4-4. 저장 실패 시 불변 조건

저장 요청이 **실패**한 경우(네트워크 오류, 4xx/5xx, 검증 오류 등):

- `currentDatabaseEstimateId` / `editingEstimateId` 및 수정모드 UI는 **사용자가 재시도할 수 있도록 유지**한다.
- full reset은 **저장 성공 콜백 경로**에서만 호출한다.

즉, “덮어쓰기 방지”를 위해 성공 시에만 ID를 끊는다는 계약과 모순되지 않게 한다.

### 4-5. `resetInputFormKeepCustomerName` 호출부 전수

`resetInputFormKeepCustomerName`(및 유사 부분 리셋)의 **모든 참조를 검색**하고, 호출 컨텍스트별로 아래를 구분한다.

- **저장 성공 후 / 수정 적용 후** → 이번 배치의 full reset helper로 통일
- **취소·새 견적·기타** → 고객명 유지 등 기존 의도가 필요하면 부분 리셋 유지

표로 메모해 두면 회귀 시 “의도치 않은 고객명 삭제”를 막을 수 있다.

## 5. 구현 대상 파일

핵심 파일:

- [templates/wdcalculator/partials/wdcalculator_body.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_body.html)
- [static/js/wdcalculator/estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
- [static/js/wdcalculator/primary-form.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/primary-form.js)
- [static/js/wdcalculator/pricing-core.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/pricing-core.js)
- [templates/wdcalculator/partials/wdcalculator_styles.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_styles.html)
- [templates/wdcalculator/partials/wdcalculator_scripts.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_scripts.html)

테스트 후보:

- `tests/domains/test_wdcalculator_product_settings.py`
- 권장 새 파일: `tests/domains/test_wdcalculator_estimate_reset_contract.py`  
  - **최소 1개 이상** 의미 있는 assertion(예: 저장 API가 받는 필드명·신규 저장 시 `estimate_id` 미전달 정책이 문서화된 서버 동작과 모순 없음을 스냅샷/픽스처로 고정, 또는 템플릿에 추가한 data-attribute 존재). 순수 JS 상태만으로는 Python 테스트가 약해질 수 있으므로, **검증 가능한 경계**(API 계약, 렌더된 마커) 중 하나를 택한다.
- 필요 시 Node/contract 테스트 추가

## 6. 실행 단계

### Phase A — 상태 리셋 근본 수정

0. §4-5에 따라 `resetInputFormKeepCustomerName` 등 부분 리셋 **호출부 전수**를 정리하고, full reset으로 바꿔도 되는지 행별로 확정한다.
1. `resetInputFormKeepCustomerName()` 호출 경로와 역할을 분리한다.
2. 신규 helper 예:
   - `resetInputFormToNewEstimate()`
   - 또는 같은 모듈 내 full reset 함수
3. 이 helper는 아래까지 책임진다.
   - `setEditingEstimateId(null)`
   - `setCurrentDatabaseEstimateId(null)`
   - 고객명 초기화
   - 쿠폰/배송 기본값 복원
   - 배송 포함 체크 기본값 복원
   - 로컬 estimates 비우기
   - 수정모드 헤더/배지 제거
   - reset 버튼 제거/숨김
   - 버튼 라벨을 `견적 추가`로 복원
4. 저장 성공 후 `refreshAfterSave()`는 full reset을 사용하도록 바꾼다. §4-4에 따라 실패 경로에서는 호출하지 않는다.
5. 진행 중 견적 `수정 적용` 후에도 same full reset을 사용한다.

완료 기준:

- 저장 직후 다음 저장은 새 DB row 생성 경로를 탄다.
- 수정 적용 직후에도 편집 모드에 머물지 않는다.

### Phase B — 단가 표시 공통 헬퍼

1. `estimate-lifecycle.js` 또는 적절한 WD canonical chunk에 공용 helper를 만든다.
   - 예: `deriveEstimateUnitPriceSummary(estimate, products)`
   - 예: `renderEstimateUnitPriceHtml(summary)`
2. 이 helper는
   - `baseComponents`
   - 레거시 `productId/manualPricing`
   - 저장된 `estimate_data.estimates[*]`
   를 모두 처리해야 한다.
3. 제품 선택 모드면 products catalog를 참조하고, 직접입력이면 `manualPricing` 기준으로 문자열을 만든다.
4. **DOM 안전**: 요약 문자열을 HTML로 넣을 때는 신뢰할 수 있는 숫자·라벨만 조합하고, 사용자 입력이 섞일 수 있으면 **`textContent` 경로 또는 이스케이프**로 XSS를 방지한다. `innerHTML`에 raw 문자열을 붙이지 않는다.

완료 기준:

- 현재 견적, 진행 중 견적, 저장된 견적이 같은 규칙으로 단가를 보여준다.

### Phase C — UI 삽입

1. `wdcalculator_body.html`
   - `기본 견적:` 우측에 단가 슬롯 추가
   - `진행 중인 견적` 헤더 우측에 토글 버튼 추가
2. `estimate-lifecycle.js`
   - `renderEstimatesList()` 카드에 단가 표시 추가
   - `buildSidebarEstimateItem()`에 단가 표시 추가
   - **저장된 견적 검색 결과**가 위와 **동일 함수/동일 헬퍼**를 쓰면 토글·단가 규칙이 자동 정렬된다. 별도 렌더 경로가 있으면 그 경로에도 **동일 `deriveEstimateUnitPriceSummary`**를 호출해 단가 메타를 넣는다. 이번 배치의 사용자 대면 완료 기준은 **기본 견적 결과 + 진행 중 카드 + 저장된 견적 사이드바**이며, 검색 전용 목록은 동일 규칙 적용까지를 범위로 한다.
3. `wdcalculator_styles.html`
   - 단가 chip/badge/list 스타일 추가
   - 토글 ON/OFF 상태 스타일 추가

완료 기준:

- 현재 견적 / 진행 중 / 저장된 견적 모두 단가 메타가 보인다.
- 토글이 list-style 표시에 정상 반영된다.

### Phase D — 검증 + GDM 감리

필수 검증:

```powershell
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/contracts/wdcalculator/test_composition_contracts.py tests/domains/test_wdcalculator_product_settings.py -q
```

권장 추가:

```powershell
pytest tests/domains/test_wdcalculator_estimate_reset_contract.py -q
```

수동 스모크:

1. 저장된 견적 불러오기
2. 수정 후 저장
3. 저장 직후 화면이 완전 신규 입력 상태인지 확인
4. 같은 고객명으로 새 견적 저장 시 기존 견적 overwrite가 아닌 신규 저장인지 확인
5. 현재 결과 `기본 견적:` 우측 단가 표시 확인
6. 저장된 견적 사이드바 단가 표시 확인
7. 진행 중 견적 토글 ON/OFF 확인

## 7. 리스크와 방지책

### 리스크 1. 저장 후 고객명까지 지우면 UX가 바뀔 수 있음

방지:

- 이번 요구사항은 “완전한 신규 입력 상태”를 우선한다.
- 그래도 저장 완료 토스트/사이드바 highlight는 유지해 사용자가 성공을 알 수 있게 한다.

### 리스크 2. 단가 표기가 복합 기본 구성에서 어색할 수 있음

방지:

- 복수 기본 구성은 chip/list 요약으로 표기
- 한 줄 강제 대신 wrap 허용

### 리스크 3. 레거시 저장 견적에 단가 원천이 부족할 수 있음

방지:

- `단가 정보 없음` muted fallback 허용
- silent failure 금지, 콘솔 경고는 허용

### 리스크 4. 단가 요약을 HTML로 삽입할 때 XSS

방지:

- §Phase B의 DOM 안전 규칙 준수
- chip/list 구조는 정적 래퍼 + 데이터만 채움

## 8. 완료 기준

- 저장 후 편집 상태가 완전히 종료된다.
- 수정 적용 후에도 신규 입력 상태가 된다.
- `기본 견적:` 우측에 적용 단가가 보인다.
- 저장된 견적 / 진행 중 견적에도 단가가 보인다.
- `진행 중인 견적` 우측 토글로 단가 표기를 켜고 끌 수 있다.
- 검증과 GDM 감리에서 blocker가 없다.

## 9. 산출 보고 및 핸드오프

구현 완료 후 사용자 보고 형식은 [2026-04-20-wdcalculator-save-reset-unit-price-executor-prompt.md](2026-04-20-wdcalculator-save-reset-unit-price-executor-prompt.md) **§9. 최종 보고 형식**과 동일하게 정리한다. 실행 에이전트용 상세 프롬프트는 동 디렉터리의 executor 문서를 따른다.

