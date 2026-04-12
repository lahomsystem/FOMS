# WDCalculator Scripts Decomposition Plan
> 작성일: 2026-04-12 | 상태: product-catalog legacy UI batch 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
`templates/wdcalculator/partials/wdcalculator_scripts.html`의 실제 runtime contract를 고정하고, inline giant script를 안전하게 static JS 쪽으로 분리하기 위한 첫 실행 계획을 확정한다.

### 1.2 기능 요구사항
1. `/wdcalculator` 페이지가 서버에서 주입하는 Jinja → JS config contract를 문서화한다.
2. `wdcalculator_scripts.html`의 public/runtime surface를 contract freeze 대상으로 고정한다.
3. 첫 실행 배치는 **행동 변경 없이** script order와 config 경계를 분리하는 범위로 제한한다.
4. 이후 static JS extraction 배치가 따를 target module 이름과 QA baseline을 함께 정의한다.

### 1.3 예외/제약 조건
- 계산 로직 변경, WDCalculator pricing rule 변경, API payload 변경을 섞지 않는다.
- 첫 배치에서는 hardcoded `/api/wdcalculator/*` URL을 수정하지 않는다.
- inline giant script의 `DOMContentLoaded` 단일 bootstrap 구조는 contract freeze 전에는 해체하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `templates/wdcalculator/calculator.html` | include chain 유지, script order contract 기준점 |
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | giant inline JS의 current runtime contract freeze 대상 |
| `templates/wdcalculator/partials/wdcalculator_body.html` | DOM id/class/data-* contract 확인 대상 |
| `static/js/wdcalculator/shared.js` | 이미 존재하는 전역 helper/runtime load order contract |
| `static/js/wdcalculator/product-catalog-ui.js` | product fetch/select/info/base-components sync를 옮긴 static UI module |
| `apps/api/wdcalculator.py` | `/wdcalculator` render + `/api/wdcalculator/*` fetch endpoint coupling 확인 |
| `tests/test_wdcalculator_product_settings.py` | 기존 WDCalculator test baseline 참고 |
| `tests/` 신규 contract tests | `/wdcalculator` render contract와 핵심 API smoke 고정 |

### 2.2 Runtime contract to freeze first
- Jinja global config:
  - `wdCalculatorCategories`
  - `wdNotesCategories`
  - `notesCategories`
- script order:
  1. config inline script
  2. `static/js/wdcalculator/shared.js`
  3. `static/js/wdcalculator/sidebar-estimates.js`
  4. `static/js/wdcalculator/estimate-totals.js`
  5. `static/js/wdcalculator/current-estimate-math.js`
  6. `static/js/wdcalculator/notes-ui.js`
  7. `static/js/wdcalculator/base-components-ui.js`
  8. `static/js/wdcalculator/coupon-display-helpers.js`
  9. `static/js/wdcalculator/additional-options-ui.js`
  10. `static/js/wdcalculator/product-catalog-ui.js`
  11. giant `DOMContentLoaded` inline app script
- 주요 fetch endpoint:
  - `GET /api/wdcalculator/products`
  - `GET /api/wdcalculator/search-estimates`
  - `GET /api/wdcalculator/search-orders`
  - `POST /api/wdcalculator/match-order`
  - `POST /api/wdcalculator/save-estimate`
  - `GET /api/wdcalculator/estimate/<id>`
  - `DELETE /api/wdcalculator/estimate/<id>`
- query param contract:
  - `estimate_id`
  - `order_id`
  - order 복귀 link ``/edit/${orderId}``
- 대표 DOM contract:
  - `#baseComponentsContainer`
  - `#productSelect`
  - `#additionalOptionsContainer`
  - `#productInfoContent`
  - `#notesContainer`
  - `#savedEstimatesList`
  - `#savedEstimatesLoading`
  - `#savedEstimatesListContainer`
  - `.base-component-row`
  - `.additional-option-item`
- `.saved-estimate-row`
- `.saved-estimate-customer-name`
  - `.load-estimate-btn`
  - `.delete-estimate-btn`

### 2.3 First safe batch
- 목표: giant script를 바로 static JS로 옮기지 않고, **config/order boundary**만 먼저 분리한다.
- 제안:
  - `calculator.html` include chain에서 config prelude를 `wdcalculator_scripts_config.html`로 분리한다.
  - 기존 `wdcalculator_scripts.html`는 giant app script boundary로 유지한다.
  - giant app script 본문은 verbatim 유지
  - `shared.js` load order는 동일 유지
- 이 배치는 file boundary만 바꾸고 runtime behavior는 유지하는 structure-only batch로 본다.

### 2.3.1 Batch 1 결과
- `tests/test_wdcalculator_product_settings.py`에 `/wdcalculator` render contract와 calculate → save-estimate → estimate/<id> roundtrip smoke를 추가했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`를 신설해 Jinja config script + `shared.js` prelude를 분리했다.
- `templates/wdcalculator/calculator.html`는 body → config partial → giant app script include 순서를 유지하도록 갱신했다.
- `templates/wdcalculator/partials/wdcalculator_scripts.html`에서는 giant `DOMContentLoaded` app bootstrap만 남겼다.
- 검증 결과: focused pytest `5 passed`, `APP_OK`, 신규 lint 없음.

### 2.4 Future static JS target modules
- `static/js/wdcalculator/sidebar-estimates.js`
  - 사이드바 검색/새로고침/삭제/모바일 more
- `static/js/wdcalculator/estimate-totals.js`
  - aggregate totals/coupon/shipping 순수 계산 helper
- `static/js/wdcalculator/calculator-core.js`
  - `calculateEstimate`, `collectCurrentEstimate`, estimate local state
- `static/js/wdcalculator/base-components-ui.js`
  - base component row render/event
- `static/js/wdcalculator/notes-ui.js`
  - notes category / note row render
- `static/js/wdcalculator/coupon-display-helpers.js`
  - global coupon input read + final price / coupon text style helper

### 2.4.1 Sidebar batch preaudit 메모
- 최소 안전 경계는 `// === 사이드바 견적 목록 기능 ===` 블록 중 DOM lookup, `loadSidebarEstimates(searchQuery)`, `deleteEstimate(id)`, sidebar search/refresh handler, 초기 `loadSidebarEstimates()` 호출까지다.
- `refreshAfterSave`는 저장 후 highlight timing과 `.then()` 체인을 위해 host giant script에 남기고, extracted module의 `loadSidebarEstimates` Promise를 주입받아 사용한다.
- extracted sidebar module이 host에서 주입받아야 할 핵심 coupling은 `loadEstimateToForm(estimate)` callback, `formatNumber`, sidebar DOM ids, `GET /api/wdcalculator/search-estimates`, `DELETE /api/wdcalculator/estimate/<id>`다.
- URL `estimate_id`/`order_id` auto-load block은 `products` readiness, `backToOrderBtn`, `loadEstimateToForm`, sidebar refresh를 함께 오케스트레이션하므로 이번 batch에서는 giant script에 남기고 후속 bootstrap batch로 미룬다.

### 2.4.2 Batch 2 결과
- `static/js/wdcalculator/sidebar-estimates.js`를 신설해 sidebar estimate search/refresh/delete/mobile more logic을 giant inline script에서 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `sidebar-estimates.js`를 `shared.js` 뒤, giant app script 앞에 로드하도록 갱신했다.
- host giant script는 `window.initWdCalculatorSidebarEstimates(...)` bridge와 `refreshAfterSave` orchestration만 유지하고, 저장 직후 highlight는 `.saved-estimate-row`/`.saved-estimate-customer-name` contract 기준으로 row-level target을 고정했다.
- sidebar row 렌더링은 `innerHTML` 기반 사용자 문자열 삽입을 제거하고 `textContent`/`setAttribute` 기반 DOM-safe 렌더링으로 교체했다.
- `tests/test_wdcalculator_product_settings.py`에는 sidebar search/delete focused smoke를 추가했고, 최종 검증 결과는 focused pytest `6 passed`, `APP_OK`, 신규 lint 없음이다.

### 2.4.3 Estimate totals batch preaudit 메모
- 다음 최소 안전 경계는 `calculateTotalEstimates()` 안의 aggregate totals/coupon/shipping 정책만 순수 helper로 먼저 분리하는 것이다.
- host giant script에 남겨야 하는 coupling은 `editingEstimateId` guard, DOM write target(`#totalBasePrice`, `#totalAllFinalPrice`, `#couponInfo`, `#totalAllCouponInfo` 등), `collectNotes()`, `formatNumber`, `applyFinalPriceStyle`, `applyCouponDiscountStyle`다.
- 후속 helper module은 `static/js/wdcalculator/estimate-totals.js` 형태로 두고 `estimates`, `couponValue`, `shippingCost`, `shippingIncluded`를 받아 raw numeric summary를 반환하도록 제한한다.
- 이번 단계에서는 `calculateEstimate`, `collectCurrentEstimate`, `renderEstimatesList`, save/load bootstrap, URL `estimate_id`/`order_id` flow는 giant host script에 그대로 둔다.
- 회귀 포인트는 `editingEstimateId`일 때 single-form summary 보존, 쿠폰 1회 적용 계약, 배송비 포함 여부(`shippingIncluded`) 처리, `estimates.length === 0` reset path다.

### 2.4.4 Batch 3 결과
- `static/js/wdcalculator/estimate-totals.js`를 신설해 aggregate totals/coupon/shipping 순수 계산 정책을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `estimate-totals.js`를 `sidebar-estimates.js` 뒤, giant app script 앞에 로드하도록 갱신했다.
- host giant script에는 `resolveWdcAggregateTotals()`를 추가해 helper 미로드 시 명시적 오류를 내도록 했고, `calculateTotalEstimates()`와 저장 payload totals 계산이 모두 같은 helper 경로를 사용하도록 단일화했다.
- helper는 `finiteOrZero()`로 비정상 입력을 0으로 정규화하며, focused Node regression(`tests/test_wdcalculator_estimate_totals_node.py` + `tests/support/wdcalculator_estimate_totals_node_checks.js`)으로 일반 합계, 쿠폰 clamp, 배송비 제외, 누락 필드 NaN 방지를 고정했다.
- 최종 검증 결과는 focused pytest `7 passed`, `APP_OK`, 신규 lint 없음이다.

### 2.4.5 Current estimate math batch preaudit 메모
- 다음 최소 안전 경계는 `calculateEstimate()`와 `collectCurrentEstimate()`에 중복된 건별 가격 계산 코어를 순수 helper로 먼저 분리하는 것이다.
- 가장 먼저 분리할 핵심은 `baseComponents` + `products` + `additionalFees` → `basePrice`, `normalizedComponents`, `displayParts/detail lines`를 계산하는 공통 루프이며, 후속으로 options 수집/합산을 묶을 수 있다.
- host giant script에 남겨야 하는 coupling은 `editingEstimateId`, `estimates`, `currentDatabaseEstimateId`, `getCouponValue()`, `collectNotes()`, `formatNumber`, `applyFinalPriceStyle`, `applyCouponDiscountStyle`, 버튼 DOM(`addEstimateBtn`, `saveEstimateBtn`), `refreshAfterSave`, `loadEstimateToInputForm`, `loadEstimateToForm`, `renderEstimatesList`다.
- 가장 조심해야 할 회귀 포인트는 `editingEstimateId`가 켜진 수정 모드에서 single-form summary와 aggregate panel이 서로 덮어쓰지 않는 계약, add/edit 버튼 상태 전이, `cloneNode` 기반 save 버튼 단일 바인딩, `refreshAfterSave` 타이밍이다.
- 추천 모듈 형태는 `static/js/wdcalculator/current-estimate-math.js`이며, `baseComponents`/`products`를 받아 건별 가격 계산 결과와 normalized snapshot payload를 반환하는 순수 helper로 제한한다.
- 이번 다음 배치 전에는 `calculateEstimate()`가 그리는 합계와 `collectCurrentEstimate()`가 반환하는 `basePrice`/`additionalPrice`/`totalPrice`가 동일 입력에서 항상 일치한다는 contract freeze가 먼저 필요하다.

### 2.4.6 Current estimate contract freeze 결과
- `tests/support/wdcalculator_current_estimate_contract_node_checks.js` + `tests/test_wdcalculator_current_estimate_contract_node.py`를 추가해 `calculateEstimate()`와 `collectCurrentEstimate()`를 Node VM에서 같은 입력으로 실행하는 focused contract를 고정했다.
- 제품 선택, manual 30cm, width 0 fee-only, width > 0 unresolved fee-only, manual fee-only, 직접입력 option, notes snapshot까지 DOM 표시값과 collected snapshot의 정합성을 시나리오로 묶었다.
- 최종 검증 결과는 focused pytest `8 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.7 Batch 4 결과
- `static/js/wdcalculator/current-estimate-math.js`를 신설해 `baseComponents` + `products` + `additionalFees/options` → `basePrice`, `normalizedComponents`, option summary를 계산하는 공통 코어를 giant inline script 밖으로 분리했다.
- host giant script에는 `readAdditionalOptionRowsFromUI()`와 `resolveWdcCurrentEstimateMath()`만 남기고, `calculateEstimate()` / `collectCurrentEstimate()`는 helper 결과를 받아 DOM/state orchestration만 수행하도록 정리했다.
- 추가로 `widthMm > 0`인데 기본 단가가 없고 추가금만 있는 row가 화면 합계와 저장 스냅샷에서 어긋나던 잠재 결함을 helper와 contract test 양쪽에서 함께 수정해 drift를 제거했다.
- 최종 검증 결과는 focused pytest `8 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.8 Notes UI batch preaudit 메모
- current-estimate-math 이후 가장 작은 안전 경계는 notes cluster(`loadNotesCategories`, `renderNoteItem`, `collectNotes`, `loadNotes`, formatter/helper`)였다.
- notes는 pricing rule과 직접 순환하지 않고, host와의 계약도 `collectNotes()` / `loadNotes(savedString)` / `wdNotesCategories`로 비교적 얇아서 structure-only 분리 대상으로 적합했다.
- 회귀 포인트는 `wdNotesCategories` 준비 전 렌더, `loadNotes`의 line split/filter 규칙, `collectCurrentEstimate` / `resetInputFormKeepCustomerName` / `loadEstimateToInputForm`와의 연결 누락이었다.

### 2.4.9 Notes contract freeze 결과
- `tests/support/wdcalculator_notes_contract_node_checks.js` + `tests/test_wdcalculator_notes_contract_node.py`를 추가해 `loadNotes()` / `collectNotes()` roundtrip, `wdNotesCategories` alias contract, 숫자 formatting helper, blank-line normalization을 Node VM에서 고정했다.
- plain/select/mixed multiline/blank input과 `formatNumbersInText`, `formatNotesText`의 현재 동작을 대표 시나리오로 묶었다.
- 최종 검증 결과는 focused pytest `9 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.10 Batch 5 결과
- `static/js/wdcalculator/notes-ui.js`를 신설해 notes state/render/event cluster를 giant inline script 밖으로 분리하고, host giant script에는 `WdCalculatorNotesUI.initNotesUi()` bootstrap과 reset/load/collect bridge만 남겼다.
- render contract test에는 `notes-ui.js` load-order를 추가했고, current-estimate Node contract에는 `collectCurrentEstimate().notes` snapshot 검증을 보강했다.
- 후속 감리에서 지적된 `notesCategories` 전역 초기화 타이밍, `<option value>` escaping, reset catch 중복 호출까지 같은 배치 안에서 정리해 notes cluster의 구조 분리를 닫았다.
- 최종 검증 결과는 focused pytest `9 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.11 Base components batch preaudit 메모
- notes-ui 이후 다음 최소 안전 경계는 파일 상단의 복합 기본견적 행 UI cluster(`renderBaseComponentRow`, `ensureBaseComponentsUI`, `bindAdditionalFeeEvents`, 필요 시 `readBaseComponentsFromUI`)다.
- 이 덩어리는 입력 폼 하위 DOM과 `products` / `calculateEstimate()` 재계산 hook에 주로 묶여 있고, `renderEstimatesList`/save/load/orchestration보다 상태 공유가 적어 다음 structure-only batch 후보로 적합하다.
- 가장 큰 회귀 포인트는 `calculateEstimate()` 미호출 또는 이중 호출, `loadProducts` 후 드롭다운 동기화, `data-bound` 기반 이벤트 중복 바인딩이다.
- 다음 배치 전 contract freeze는 `#baseComponentsContainer`와 row selector/class contract, products → base row → `calculateEstimate()` hook 연결을 focused tests로 먼저 고정하는 쪽이 안전하다.

### 2.4.12 Base components contract freeze 결과
- `tests/support/wdcalculator_base_components_contract_node_checks.js` + `tests/test_wdcalculator_base_components_contract_node.py`를 추가해 `renderBaseComponentRow`, `ensureBaseComponentsUI`, `readBaseComponentsFromUI`의 DOM/selectors/snapshot contract와 base row input → `calculateEstimate()` delegated hook을 Node VM + DOM stub으로 고정했다.
- select/manual 30cm/manual 1m/additional fee row 시나리오와 기존 선택값 유지, auto 1cm 업데이트까지 representative contract로 묶었다.
- 최종 검증 결과는 focused pytest `10 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.13 Batch 6 결과
- `static/js/wdcalculator/base-components-ui.js`를 신설해 base component row render/ensure/read/update helper를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `base-components-ui.js`를 `notes-ui.js` 뒤, giant app script 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorBaseComponentsUI.configure(...)` + thin destructuring bridge만 남겼다.
- 후속 감리에서 발견된 host의 `updateBaseProductSelectOptions` 중복 선언(syntax-risk)과 추가금 입력의 `calculateEstimate()` 이중 호출 경로를 같은 배치 안에서 정리해 base-components 재계산 경로를 단일화했다.
- 최종 검증 결과는 focused pytest `10 passed`, inline script syntax parse `WD_SCRIPTS_PARSE_OK`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.14 Coupon helper batch preaudit 메모
- base-components 이후 남은 giant script에서 가장 작은 안전 경계는 `getCouponValue`, `applyFinalPriceStyle`, `applyCouponDiscountStyle` 세 helper였다.
- 이 클러스터는 `calculateEstimate`, `calculateTotalEstimates`, 저장 payload 직전의 coupon/shipping read에서 공통으로 쓰이지만 `estimates` 배열 조작이나 save/load/bootstrap과 직접 결합되지 않아 structure-only 분리 경계가 얇다.
- 주요 회귀 포인트는 `#globalCouponValue` 파싱 규칙(기본 11000, empty/invalid fallback, `0` 허용), final price/coupon info style/class contract, script load order였다.

### 2.4.15 Coupon helper contract freeze 결과
- `tests/support/wdcalculator_coupon_display_contract_node_checks.js` + `tests/test_wdcalculator_coupon_display_contract_node.py`를 추가해 `getCouponValue()`의 missing/empty/0/negative/non-numeric/`parseInt` parsing contract와 final price/coupon style helper 출력을 Node로 고정했다.
- `tests/support/wdcalculator_current_estimate_contract_node_checks.js`도 coupon helper module을 VM에 함께 로드하도록 갱신해 current-estimate contract가 새 helper 경로를 계속 검증하도록 보강했다.
- 최종 검증 결과는 focused pytest `11 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.16 Batch 7 결과
- `static/js/wdcalculator/coupon-display-helpers.js`를 신설해 coupon input read와 final price/coupon text style helper를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `coupon-display-helpers.js`를 `base-components-ui.js` 뒤, giant app script 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorCouponDisplayHelpers.configure({ defaultCouponValue: DEFAULT_COUPON_VALUE })` + thin destructuring bridge만 남겼다.
- `/wdcalculator` render contract는 새 helper load-order를 고정했고, inline script 전체는 Node parse smoke로 syntax regression까지 확인했다.
- 최종 검증 결과는 focused pytest `11 passed`, inline script syntax parse `WD_SCRIPTS_PARSE_OK`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.17 Additional-options rows batch preaudit 메모
- coupon helper 이후 다음 구조-only 후보는 additional-options rows UI cluster(`setOptionMode`, add/remove row, `readAdditionalOptionRowsFromUI`)다.
- 다만 실제 안전 경계는 152–318행의 “행 추가/토글/삭제/읽기”만이 아니라, `loadEstimateToInputForm()` 내부 1544–1724행의 옵션 row 복원/바인딩 경로까지 함께 고려해야 한다. 두 경로가 이미 유사 마크업과 이벤트를 이중 구현하고 있어 한쪽만 분리하면 drift 리스크가 크다.
- 다음 batch의 핵심은 `setOptionMode`, option `<option>` HTML 생성, `readAdditionalOptionRowsFromUI`, 그리고 추가 버튼/로드 경로가 공통으로 쓰는 `wireAdditionalOptionRow` 같은 단일 바인딩 진입점을 먼저 설계하는 것이다.
- 주요 회귀 포인트는 `.additional-option-item` DOM schema, select `value` 형식(`category|option|price`), mode toggle 시 표시/숨김 규칙, remove/calculateEstimate 훅의 이중 호출, load 경로와 add 경로의 selector/price formatting drift다.
- 따라서 다음 단계는 additional-options rows DOM/selectors와 mode toggle → `calculateEstimate()` hook contract를 focused tests로 먼저 고정한 뒤, row UI module batch로 넘어가는 것이 가장 안전하다.

### 2.4.18 Additional-options contract freeze 결과
- `tests/support/wdcalculator_additional_options_contract_node_checks.js` + `tests/test_wdcalculator_additional_options_contract_node.py`를 추가해 추가 옵션 row DOM/schema, mode toggle, direct-input/select read contract, remove 시 단일 `calculateEstimate()` 호출을 Node VM + DOM stub으로 고정했다.
- contract freeze 과정에서 새로 추가한 row의 remove 버튼이 direct listener와 delegated listener를 동시에 타면서 재계산이 이중 호출될 수 있는 결함을 발견했고, host add path에서는 direct remove listener를 제거해 단일 경로로 정리했다.
- 최종 검증 결과는 focused pytest `12 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.19 Batch 8 결과
- `static/js/wdcalculator/additional-options-ui.js`를 신설해 추가 옵션 row add/toggle/remove/read helper와 `loadEstimateToInputForm()`의 row restore/wiring 경로를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `additional-options-ui.js`를 `coupon-display-helpers.js` 뒤, giant app script 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorAdditionalOptionsUI.configure(...)` + thin destructuring bridge만 남겼다.
- `tests/support/wdcalculator_current_estimate_contract_node_checks.js`는 `readAdditionalOptionRowsFromUI()`를 template가 아니라 새 module 경로에서 읽도록 갱신했고, `/wdcalculator` render contract에는 새 helper load-order를 추가했다.
- add path와 load path의 price input formatting 차이는 현재 runtime behavior를 보존하기 위해 module 내부 `formatPriceOnInput` 옵션으로 유지했다.
- 최종 검증 결과는 focused pytest `12 passed`, inline script syntax parse `WD_SCRIPTS_PARSE_OK`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.20 Product catalog legacy UI batch preaudit 메모
- additional-options 이후 가장 작은 안전 경계는 `loadProducts`, `updateProductSelect`, `showProductInfo`, 그리고 `#productSelect` change handler가 구성하는 product catalog legacy UI cluster다.
- 이 묶음은 `GET /api/wdcalculator/products` → `products` 배열 갱신 → dropdown/UI 반영 → base-components select option sync → `calculateEstimate()` 호출이라는 비교적 단방향 흐름이라, 저장/사이드바/검색/모달 cluster보다 경계가 얇다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `products` 배열 단일 source, `updateBaseProductSelectOptions()`, `ensureBaseComponentsUI()`, `calculateEstimate()`, `additionalOptionsContainer` reset, `productInfo`/`productInfoContent`/`baseEstimateSection` DOM ids다.
- 주요 회귀 포인트는 products fetch shape drift, load 직후 base-components sync 순서 누락, `#productSelect` 변경 시 추가 옵션 미초기화, 제품 해제 시 `baseEstimateSection`/`productInfo` 숨김 누락이다.

### 2.4.21 Product catalog legacy UI contract freeze 결과
- `tests/support/wdcalculator_product_catalog_contract_node_checks.js` + `tests/test_wdcalculator_product_catalog_contract_node.py`를 추가/정리해 `loadProducts`, `updateProductSelect`, `showProductInfo`, `#productSelect` change 경로의 fetch shape, base-components sync 순서, recalculation side effect contract를 Node VM + DOM stub으로 고정했다.
- freeze 과정에서 Node DOM stub이 `textContent` setter 없이 동작해 `shared.js`의 `escapeHtml()`가 빈 문자열을 돌려주는 drift를 발견했고, stub을 브라우저 동작과 맞추고 helper shim도 고정해 `showProductInfo()` escaping contract를 안정화했다.
- `/api/wdcalculator/products`의 legacy `{success, products}` payload shape와 script load order는 `tests/test_wdcalculator_product_settings.py`로 함께 묶어 고정했다.

### 2.4.22 Batch 9 결과
- `static/js/wdcalculator/product-catalog-ui.js`를 신설해 `loadProducts`, `updateProductSelect`, `showProductInfo`, `handleProductSelectChange`, `bindProductSelect`를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `product-catalog-ui.js`를 `additional-options-ui.js` 뒤, giant app script 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorProductCatalogUI.configure(...)` + thin destructuring bridge + `bindProductSelect()`만 남겼다.
- focused regression은 product catalog Node contract + `/wdcalculator` render contract + `/api/wdcalculator/products` API shape smoke까지 묶어 `3 passed`로 검증했다.

## 3. Steps — 실행 단계
- [x] Step 1: `/wdcalculator` render contract와 injected config/script order를 focused tests로 freeze한다.
- [x] Step 2: WDCalculator giant script가 의존하는 핵심 `/api/wdcalculator/*` 성공 shape를 최소 smoke tests로 freeze한다.
- [x] Step 3: `wdcalculator_scripts.html`를 config/app include 경계로만 structure-only 분리한다.
- [x] Step 4: sidebar estimate block의 extracted module API(`loadSidebarEstimates`, `deleteEstimate`, wiring`)를 고정하고 `static/js/wdcalculator/sidebar-estimates.js` batch를 완료한다.
- [x] Step 5: aggregate totals/coupon/shipping 순수 helper API를 고정하고 `static/js/wdcalculator/estimate-totals.js` batch를 완료한다.
- [x] Step 6: `calculateEstimate()` / `collectCurrentEstimate()` shared math contract를 focused tests로 freeze한다.
- [x] Step 7: `static/js/wdcalculator/current-estimate-math.js` batch를 완료한다.
- [x] Step 8: notes UI(`collectNotes`, `loadNotes`, `wdNotesCategories`) contract를 focused tests로 freeze한다.
- [x] Step 9: `static/js/wdcalculator/notes-ui.js` batch를 완료한다.
- [x] Step 10: base-components row DOM/selectors와 products → `calculateEstimate()` 재계산 hook contract를 focused tests로 freeze한다.
- [x] Step 11: `static/js/wdcalculator/base-components-ui.js` batch를 완료한다.
- [x] Step 12: `getCouponValue()` + final price/coupon style helper contract를 focused tests로 freeze한다.
- [x] Step 13: `static/js/wdcalculator/coupon-display-helpers.js` batch를 완료한다.
- [x] Step 14: additional-options rows UI(`setOptionMode`, add/remove row, `readAdditionalOptionRowsFromUI`) extraction boundary를 전감리한다.
- [x] Step 15: additional-options rows DOM/selectors와 mode toggle → `calculateEstimate()` hook contract를 focused tests로 freeze한다.
- [x] Step 16: additional-options rows UI를 static JS module로 분리하고 host script에는 save/load/bootstrap orchestration만 남긴다.
- [x] Step 17: product catalog legacy UI(`loadProducts`, `updateProductSelect`, `showProductInfo`, `#productSelect` change) contract를 focused tests로 freeze한다.
- [x] Step 18: product catalog legacy UI를 static JS module로 분리하고 host script에는 products state/bootstrap orchestration만 남긴다.

## 4. 검증 기준
- [x] `GET /wdcalculator` render contract test 통과
- [x] `POST /api/wdcalculator/save-estimate` 최소 smoke 통과
- [x] `POST /api/wdcalculator/calculate` + load estimate roundtrip smoke 통과
- [x] `GET /api/wdcalculator/search-estimates` + `DELETE /api/wdcalculator/estimate/<id>` smoke 통과
- [x] giant script include order가 유지됨을 확인
- [x] `estimate-totals.js` helper contract(Node) 통과
- [x] `current-estimate-math.js` contract(Node) 통과
- [x] `notes-ui.js` roundtrip contract(Node) 통과
- [x] `base-components-ui.js` contract(Node) 통과
- [x] `coupon-display-helpers.js` contract(Node) 통과
- [x] `additional-options-ui.js` contract(Node) 통과
- [x] `product-catalog-ui.js` contract(Node) 통과
- [x] `wdcalculator_scripts.html` syntax parse smoke 통과
- [x] 신규 lint 없음
- [x] `python -c "import app; print('APP_OK')"` 통과

## 5. QA baseline
- `/wdcalculator` 첫 로드 시 console error 없음
- categories / notes categories UI 표시 정상
- product dropdown 로드 정상
- estimate add/save/load smoke 정상
- sidebar estimate search/refresh/delete smoke 정상
- 저장 직후 sidebar row highlight가 버튼이 아닌 row container 기준으로 동작
- aggregate totals/save payload totals가 같은 helper 경로를 사용
- current estimate DOM summary와 collect snapshot이 같은 helper 경로를 사용
- notes load/collect roundtrip과 currentEstimate.notes snapshot이 유지됨
- base-components row render/read/update와 delegated recalculation hook이 module 경로로 유지됨
- coupon input parse와 final price/coupon text style helper가 module 경로로 유지됨
- additional-options row add/toggle/remove/read와 loadEstimate restore wiring이 module 경로로 유지됨
- `?estimate_id=` / `?order_id=` query param flow 정상

## 6. 참고 자료
- 관련 inventory: `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
- 관련 spec: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
- 관련 상태 문서: `docs/AI_STATUS.md`
