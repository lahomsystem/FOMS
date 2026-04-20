# WDCalculator Scripts Decomposition Plan
> 작성일: 2026-04-12 | 상태: 2026-04-13 modular-monolith rebaseline 반영 완료, 기존 micro batch 기록은 archive로 유지, 이후 실행은 meaningful-chunk merge 기준

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
`/wdcalculator`의 실제 runtime contract는 유지하되, 이미 누적된 micro extraction 자산과 남은 giant inline surface를 **더 큰 owner chunk**로 다시 묶는 실행 기준을 확정한다.

이 계획의 목표는 더 많은 helper 파일을 추가하는 것이 아니라 다음 네 가지를 동시에 달성하는 것이다.

- WDCalculator 구조 작업이 앞으로도 **큰 덩어리 기준**을 잃지 않게 한다.
- 이미 생긴 micro file / wrapper / contract pair를 **정리 대상 debt**로 재정의한다.
- 이후 배치가 file count / test count / wrapper count를 최소 동결, 가능하면 순감 방향으로만 움직이게 한다.
- 사람과 AI agent가 `WDCalculator`를 더 적은 탐색으로 이해할 수 있게 entrypoint와 canonical chunk를 고정한다.

### 1.2 기능 요구사항
1. `/wdcalculator` 페이지가 서버에서 주입하는 Jinja → JS config contract를 문서화한다.
2. `wdcalculator_scripts.html`의 public/runtime surface를 contract freeze 대상으로 고정한다.
3. 앞으로의 WDCalculator 구조 작업은 **새 micro extraction**이 아니라, 이미 생긴 자산을 `composition`, `primary form`, `estimate lifecycle`, `pricing core`의 큰 chunk로 다시 수렴시키는 방향이어야 한다.
4. 기존에 생성된 small helper / bootstrap / host-bootstrap / state shard / contract pair는 future precedent가 아니라 merge/remove 대상 debt로 본다.
5. 새 batch의 기본 순서는 **delete -> merge -> extend existing chunk -> add new file** 이어야 한다.
6. 새 `*-host-bootstrap.js`, wrapper-only batch, configure/init forwarding pair 증식은 더 이상 허용하지 않는다.
7. 테스트 전략은 tiny helper pair 추가가 아니라 **chunk-level contract**로 재정리하는 방향이어야 한다.
8. `static/js/wdcalculator/README.md` 또는 동등한 local entrypoint 문서를 두고 chunk map, 읽기 순서, removal target을 유지해야 한다.
9. 모든 새 batch는 최소한 `product/wrapper/test delta`, `canonical target`, `removal target`, `retirement wave`를 기록해야 한다.

### 1.3 예외/제약 조건
- 계산 로직 변경, WDCalculator pricing rule 변경, API payload 변경을 섞지 않는다.
- root runtime contract, template/static root path, packaging 관련 변경을 섞지 않는다.
- 새로운 standalone helper file을 추가할 때는 같은 batch 안에 왜 기존 chunk가 흡수할 수 없는지와 어떤 파일을 제거할지 적어야 한다.
- 아래 `2.4.*` micro batch 기록은 historical archive이며, 앞으로 같은 패턴을 반복하는 근거가 될 수 없다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `templates/wdcalculator/calculator.html` | include chain root contract 유지 |
| `templates/wdcalculator/partials/wdcalculator_scripts_config.html` | Jinja config contract + chunk script registration 기준점 |
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | giant inline app shell 최소화/최종 composition shell target |
| `templates/wdcalculator/partials/wdcalculator_body.html` | DOM id/class/data-* contract 확인 대상 |
| `static/js/wdcalculator/README.md` | chunk map, 읽기 순서, merge/remove target, AI/human entrypoint |
| `static/js/wdcalculator/composition.js` | startup/bootstrap/order/load orchestration canonical target |
| `static/js/wdcalculator/primary-form.js` | base components/notes/coupon/additional options/product catalog canonical target |
| `static/js/wdcalculator/estimate-lifecycle.js` | list/search/load/edit/save/refresh/sidebar/url canonical target |
| `static/js/wdcalculator/pricing-core.js` | current estimate math/totals/resolvers canonical target |
| 기존 `static/js/wdcalculator/*` micro modules | historical debt + merge/remove target |
| `apps/api/wdcalculator.py` | `/wdcalculator` render + `/api/wdcalculator/*` fetch endpoint coupling 확인 |
| `tests/test_wdcalculator_product_settings.py` | render/API smoke baseline 유지 |
| `tests/` WDCalculator contract suites | micro pair rationalization + chunk contract consolidation 대상 |

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

### 2.3 Meaningful-chunk rebaseline
- 2026-04-13 rebaseline 이후 이 문서의 미래 실행 기준은 "안전한 micro extraction 계속"이 아니라, **이미 생긴 micro estate를 더 큰 canonical chunk로 다시 합치기**다.
- 아래 `2.4.*`는 현재 runtime contract와 debt 지형을 보여주는 archive다.
- 앞으로의 WDCalculator 구조 배치는 helper를 더 잘게 늘리는 것이 아니라, load order 단순화, merge-back, test pair 합치기, obsolete file 제거를 성과로 본다.

### 2.3.1 Canonical chunk targets
- `composition`
  - preferred target: `static/js/wdcalculator/composition.js`
  - 범위: config handoff, startup/terminal/early/late/init/bootstrap ordering, host/bootstrap bridge, top-level orchestration
  - 1차 merge/remove target: `startup-init.js`, `terminal-init.js`, `early-bootstrap.js`, `late-bootstrap.js`, `sidebar-bootstrap.js`, `primary-ui-bootstrap.js`, `catalog-buttons-bootstrap.js`, `catalog-buttons-host-bootstrap.js`, `coupon-search-render-bootstrap.js`, `coupon-search-render-host-bootstrap.js`, `loading-database-bootstrap.js`, `loading-database-host-bootstrap.js`, `notes-ui-bootstrap.js`, `notes-ui-host-bootstrap.js`, `post-mutation-ui-bootstrap.js`, `post-mutation-ui-host-bootstrap.js`, `products-editing-bootstrap.js`, `products-editing-host-bootstrap.js`, `estimates-early-bootstrap.js`, `estimates-early-host-bootstrap.js`, `totals-startup-terminal-bootstrap.js`, `totals-startup-terminal-host-bootstrap.js`
- `primary form`
  - preferred target: `static/js/wdcalculator/primary-form.js`
  - 범위: base components, notes, coupon input/display, additional options, product catalog, direct user input rows
  - 1차 merge/remove target: `base-components-ui.js`, `notes-ui.js`, `coupon-display-helpers.js`, `additional-options-ui.js`, `product-catalog-ui.js`, `add-option-button.js`, `calculate-button.js`
- `estimate lifecycle`
  - preferred target: `static/js/wdcalculator/estimate-lifecycle.js`
  - 범위: list/search/load/edit/save/refresh/sidebar/url/local state/order match
  - 1차 merge/remove target: `sidebar-estimates.js`, `search-results-load.js`, `render-estimates-list.js`, `order-match-ui.js`, `refresh-after-save.js`, `reset-input-form-keep-customer.js`, `load-estimate-to-input-form.js`, `load-saved-estimate-to-form.js`, `save-estimate.js`, `add-estimate.js`, `estimate-list-events.js`, `estimate-mutation-bridge.js`, `loading-state.js`, `current-database-estimate-id.js`, `products-state.js`, `editing-estimate-id.js`, `estimates-state.js`, `url-bootstrap.js`
- `pricing core`
  - preferred target: `static/js/wdcalculator/pricing-core.js`
  - 범위: current estimate math, aggregate totals, calculation resolvers, total display, coupon/shipping related 계산/오케스트레이션
  - 1차 merge/remove target: `current-estimate-math.js`, `estimate-totals.js`, `calculation-resolvers.js`, `total-estimates-display.js`, `current-estimate-orchestration.js`, `coupon-shipping-wiring.js`
- file 이름보다 더 중요한 것은 총 file count다. 같은 책임을 더 적은 파일로 유지할 수 있다면 새 target file을 만들기보다 기존 file로 흡수한다.

### 2.3.2 Next execution order
1. `composition`
   - 가장 먼저 bootstrap/host inflation을 줄이고 include order를 단순화한다.
2. `primary form`
   - 입력 폼 아래쪽 UI cluster를 큰 덩어리로 다시 묶는다.
3. `estimate lifecycle`
   - save/load/list/sidebar/url/state shard를 큰 흐름 단위로 다시 묶는다.
4. `pricing core`
   - 수학/합계/해석기/orchestration 경계를 하나의 pricing cluster로 다시 묶는다.
5. chunk contract consolidation
   - 위 4개 chunk 정리 이후 obsolete micro module과 micro contract pair를 제거/통합한다.

### 2.3.3 Batch approval gate
- 새 batch는 반드시 `product/wrapper/test delta`, `canonical target`, `removal target`, `retirement wave`를 남긴다.
- 새 batch는 반드시 delete/merge 검토를 먼저 하고, 그 검토 결과를 남긴다.
- 새 `*-host-bootstrap.js`, wrapper-only file, thin configure/init forwarding pair는 허용하지 않는다.
- 새 `tests/support/*` + `test_*_contract_node.py` pair는 기본 금지이며, 기존 chunk contract로 흡수 불가한 이유가 없으면 만들지 않는다.
- 새 batch가 file/test/wrapper를 순증가시킨다면, 같은 batch 기록에 제거할 파일과 제거 시점을 같이 적지 않으면 승인하지 않는다.
- `static/js/wdcalculator/README.md` 또는 동등한 local entrypoint가 갱신되지 않으면 structure batch가 끝난 것으로 보지 않는다.

### 2.4 Historical micro-batch archive (future precedent 아님)
- Batch 1의 config/order boundary separation은 이미 완료된 historical step이며, 현재 runtime contract의 일부로 유지한다.
- 아래 `2.4.*` 기록은 현재 micro module 지형과 contract debt를 보여주는 archive다.
- 앞으로의 WDCalculator 구조 작업은 아래 패턴을 반복하지 않고, 아래 자산을 위 `2.3.1`의 큰 chunk로 다시 접는 방향으로만 진행한다.

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

### 2.4.23 Batch 10 preaudit 메모
- product-catalog 이후 남은 주요 giant inline cluster는 (1) reset/save refresh/list orchestration, (2) in-session estimates list/card delegation, (3) search results + load-to-form, (4) order matching modal + match API, (5) URL bootstrap/back-to-order, (6) shipping/coupon change listeners다.
- 이 중 다음 structure-only 배치의 최우선 후보는 order matching UI cluster(`.match-order-btn` delegated click, `showOrderSelectionModal`, `matchEstimateToOrder`)다. 이 묶음은 `products`, `editingEstimateId`, `estimates` 배열, save payload 구성과 직접 결합하지 않고 `search-orders` / `match-order` API와 modal DOM으로 경계가 비교적 얇다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `.match-order-btn`의 `data-estimate-id`/`data-customer-name`, `#orderSelectionModal`, `.select-order-btn`, `bootstrap.Modal`, 그리고 `GET /api/wdcalculator/search-orders`, `POST /api/wdcalculator/match-order` 호출 경로다.
- 주요 회귀 포인트는 modal HTML string 조립 시 escaping drift, Bootstrap modal lifecycle(show/hide/remove), delegated click의 단일 등록 유지, `parseInt` ID 변환 일관성이다.
- 반대로 `resetInputFormKeepCustomerName`, `refreshAfterSave`, `renderEstimatesList`, `loadEstimateToForm`, save 버튼 clone/replace cluster는 `editingEstimateId`, `currentDatabaseEstimateId`, `loadSidebarEstimates`, button state 전이와 얽혀 있어 지금 시점의 다음 안전 배치로는 더 위험하다.

### 2.4.24 Order-match contract freeze 결과
- Python smoke에 `/api/wdcalculator/search-orders`와 `/api/wdcalculator/match-order` shape를 추가해 `{success, orders, count}` / `{success, message, match_id}` legacy payload surface를 고정했다.
- 신규 Node regression `tests/test_wdcalculator_order_match_contract_node.py` + `tests/support/wdcalculator_order_match_contract_node_checks.js`를 추가해 `.match-order-btn` delegated click, 단일 주문 direct-match branch, 다중 주문 `#orderSelectionModal` 생성 + `.select-order-btn` selection branch, 빈 결과 alert branch를 VM DOM stub로 고정했다.
- 이 baseline으로 다음 extraction batch는 order matching UI를 static helper로 옮기되, host script에는 search-result bridge와 bootstrap wiring만 남기는 구조-only 변경만 허용한다.

### 2.4.25 Batch 11 결과
- `static/js/wdcalculator/order-match-ui.js`를 신설해 `.match-order-btn` delegated click, `showOrderSelectionModal`, `matchEstimateToOrder`, modal 내부 `.select-order-btn` wiring을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `order-match-ui.js`를 `product-catalog-ui.js` 뒤, giant app script 앞에 로드하도록 갱신했고, host giant script는 `bindOrderMatchButtons()` bootstrap만 남겼다.
- order-match Node contract는 template inline source 대신 새 helper 파일을 직접 로드하도록 바꿔 extraction 이후에도 direct-match / modal selection / empty-result alert뿐 아니라 `search-orders` 실패 메시지, `match-order` 실패 메시지 분기까지 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `order-match-ui.js` load-order를 추가했고, focused pytest `10 passed`로 extraction 이후 baseline을 재검증했다.

### 2.4.26 Coupon/shipping wiring batch preaudit 메모
- order-match 이후 남은 giant inline cluster를 다시 비교한 결과, 가장 얇은 다음 구조 경계는 파일 하단의 global coupon/shipping listener wiring(`shippingCost`, `shippingIncluded`, `globalCouponValue`)이다.
- 이 블록은 가격 정책 그 자체가 아니라 DOM 이벤트를 기존 `calculateEstimate()`, `calculateTotalEstimates()`, `getCouponValue()` helper 경로에 연결하는 얇은 wiring이므로, save/reset/list/url bootstrap cluster보다 state coupling이 작다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `DEFAULT_COUPON_VALUE`, `estimates.length` guard, `calculateEstimate()`, `calculateTotalEstimates()`, `getCouponValue()`, 그리고 `#shippingCost` / `#shippingIncluded` / `#globalCouponValue` DOM ids다.
- 주요 회귀 포인트는 (1) 이벤트 타입별 재계산 호출 수 drift, (2) 빈/0 쿠폰 입력의 초기값 보정, (3) estimates가 비어 있을 때 aggregate recalc skip 규칙, (4) coupon input의 delayed input path(`setTimeout 100ms`)와 initial load path(`setTimeout 500ms`) 보존이다.

### 2.4.27 Coupon/shipping wiring contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_coupon_shipping_wiring_contract_node.py` + `tests/support/wdcalculator_coupon_shipping_wiring_contract_node_checks.js`를 추가해 template 하단 listener source를 직접 VM에 올리고 shipping/coupon DOM event wiring contract를 고정했다.
- freeze 범위는 `shippingCost` input/change, `shippingIncluded` change, `globalCouponValue` input/change/blur, empty/0 coupon 초기값 보정, initial load recalc, missing coupon input error branch까지 포함한다.
- 관련 helper baseline(`coupon-display-helpers`, `estimate-totals`)과 함께 focused pytest `3 passed`로 재검증했다.

### 2.4.28 Batch 12 결과
- `static/js/wdcalculator/coupon-shipping-wiring.js`를 신설해 하단 global input listener(`shippingCost`, `shippingIncluded`, `globalCouponValue`) wiring을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `coupon-shipping-wiring.js`를 `order-match-ui.js` 뒤, giant app script 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorCouponShippingWiring.configure(...)` + `initCouponShippingWiring()` bootstrap만 남겼다.
- wiring Node contract는 template source 추출이 아니라 새 helper 파일을 직접 로드하도록 바꿔 extraction 이후에도 shipping/coupon event surface와 delayed initial/input recalc path를 계속 고정하게 유지했다.
- `/wdcalculator` render contract에는 `coupon-shipping-wiring.js` load-order를 추가했고, 관련 helper baseline과 함께 focused pytest `12 passed`로 extraction 이후 baseline을 재검증했다.

### 2.4.29 Search results + load-to-form batch preaudit 메모
- coupon/shipping wiring 이후 남은 giant inline cluster를 다시 비교한 결과, 다음 얇은 구조 경계는 customer-name search panel과 search results row의 load bridge(`searchEstimateBtn`, `displaySearchResults`, `.load-estimate-btn` re-fetch)다.
- 이 묶음은 `loadEstimateToForm()` 자체를 host에 남긴 채 검색 fetch/render/button delegation만 분리할 수 있어, `editingEstimateId`/`currentDatabaseEstimateId`/sidebar refresh와 직접 결합된 저장 오케스트레이션보다 안전하다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `loadEstimateToForm`, `formatNumber`, `#searchEstimateBtn`, `#searchCustomerName`, `#searchResults`, `#searchResultsList`, 그리고 `GET /api/wdcalculator/search-estimates` 호출 경로다.
- 주요 회귀 포인트는 (1) blank customer alert, (2) empty-result message, (3) rendered `.load-estimate-btn` / `.match-order-btn`의 `data-estimate-id`/`data-customer-name` surface, (4) load button click 시 같은 customer_name으로 다시 검색한 뒤 `loadEstimateToForm(estimate)`로 bridge하는 흐름이다.

### 2.4.30 Search results + load-to-form contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_search_load_contract_node.py` + `tests/support/wdcalculator_search_load_contract_node_checks.js`를 추가해 current search panel의 blank-input alert, search-estimates URL, empty-result message, rendered button dataset, `.load-estimate-btn` re-fetch/load bridge, missing-estimate alert 분기를 먼저 고정했다.
- `tests/test_wdcalculator_product_settings.py`의 search/delete smoke도 search-estimates payload에서 `customer_name`, `estimate_data`, `created_at` surface를 직접 확인하도록 보강해 DOM helper가 기대하는 최소 API shape를 함께 묶었다.
- 이 baseline으로 다음 extraction batch는 search panel helper만 static JS로 옮기고 `loadEstimateToForm()` 본체와 DB/edit-mode 상태 전이는 그대로 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.31 Batch 13 결과
- `static/js/wdcalculator/search-results-load.js`를 신설해 customer-name search fetch, `displaySearchResults()`, `.load-estimate-btn` delegated bridge를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `search-results-load.js`를 `product-catalog-ui.js` 뒤, `order-match-ui.js` 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorSearchResultsLoad.configure({ loadEstimateToForm, formatNumber })` + `initSearchResultsLoadBridge()` bootstrap만 남겼다.
- search/load Node contract는 template source 추출 대신 새 helper 파일을 직접 로드하도록 바꿔 extraction 이후에도 blank-input alert, rendered `data-*` surface, search-estimates URL, `loadEstimateToForm` bridge, missing-estimate alert 분기를 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `search-results-load.js` load-order를 추가했고, order-match/coupon-shipping adjacent regressions까지 묶어 focused pytest `12 passed`로 extraction 이후 baseline을 재검증했다.

### 2.4.32 Remaining giant inline next preaudit 메모
- search/load까지 빠진 뒤 남은 주요 inline cluster를 재감리한 결과, 다음 안전 후보는 `renderEstimatesList` + summary card + post-render style pass(`setTimeout(..., 10)` styling)다.
- 이 영역은 `estimates` 배열을 read-mostly로 소비해 `#estimatesListContainer`, `#totalEstimatesSummary`, `saveEstimateBtn`를 렌더하는 view 성격이 강하고, save/API/URL bootstrap cluster보다 state mutation이 적다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `estimates`, `calculateTotalEstimates`, `formatNumber`, `escapeHtml`, `formatNotesText`, 그리고 `.edit-estimate-btn` / `.delete-estimate-btn` / `.edit-estimate-name-btn` / `.card[data-estimate-id]` delegation surface다.
- 주요 회귀 포인트는 (1) 1건 vs 2건 이상일 때 다른 `#totalEstimatesSummary` markup, (2) post-render `setProperty` timing, (3) `saveEstimateBtn.style.display`, (4) render 후 `calculateTotalEstimates()` 호출 순서다.

### 2.4.33 Render list contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_render_list_contract_node.py` + `tests/support/wdcalculator_render_list_contract_node_checks.js`를 추가해 current inline `renderEstimatesList()`의 empty state, `data-estimate-id` / `.estimate-display-name` surface, escaped option/notes text, 1건 vs 2건 summary layout, post-render style pass, save button 노출, render 후 aggregate callback contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 list view HTML/string render와 post-render style pass만 static helper로 옮기고, list delegation/edit/save/API/URL state는 그대로 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.34 Batch 14 결과
- `static/js/wdcalculator/render-estimates-list.js`를 신설해 `renderEstimatesList()`의 card render, `#totalEstimatesSummary` layout, post-render forced style pass, save button 노출, render-complete callback을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `render-estimates-list.js`를 `search-results-load.js` 뒤, `order-match-ui.js` 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorRenderEstimatesList.configure({ getEstimates, formatNumber, escapeHtml, formatNotesText, onRenderComplete })` bridge만 남겼다.
- render-list Node contract는 template source 추출 대신 새 helper 파일을 직접 로드하도록 바꿔 extraction 이후에도 empty state, card markup, escaped details, summary layout, post-render style pass, aggregate callback 분기를 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `render-estimates-list.js` load-order를 추가했고, search-load/order-match/coupon-shipping adjacent regressions까지 묶어 focused pytest `13 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.35 Post-render-list next preaudit 메모
- render list view까지 빠진 뒤 남은 inline cluster를 재감리한 결과, 다음 안전 후보는 `baseComponentsContainer` live interactions(add row button + click/input/change delegation)이다.
- 이 묶음은 `estimates`, `editingEstimateId`, save/API/URL orchestration과 직접 결합하지 않고 `renderBaseComponentRow`, `calculateEstimate`, `computeAutoPrice1cmFrom30cm`, `#baseComponentsContainer` DOM에 국소적으로 묶여 있어 다음 structure-only batch로 가장 얇다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `calculateEstimate` 본체와 비-base-container orchestration이며, helper/module 쪽에는 `renderBaseComponentRow`, `computeAutoPrice1cmFrom30cm`, add/remove fee/mode/input/change listener wiring만 이동시키는 것이 안전하다.
- 주요 회귀 포인트는 (1) listener 중복 등록, (2) `.base-add-fee-btn` / `.base-remove-fee-btn` / `.base-mode-btn` / `.base-remove-btn` delegated click surface, (3) input/change마다 `calculateEstimate()` 호출 횟수, (4) 30cm 수동가 변경 시 `base-manual-price1` auto-sync 규칙이다.

### 2.4.36 Base live interactions contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_base_live_events_contract_node.py` + `tests/support/wdcalculator_base_live_events_contract_node_checks.js`를 추가해 current inline `addBaseComponentBtn` 및 `#baseComponentsContainer` click/input/change delegation의 add row, fee add/remove, mode toggle, 최소 1행 guard, 30cm→1cm auto-sync, pricing-type change contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 live listener 4개만 기존 `base-components-ui.js` module 안으로 흡수하고, `calculateEstimate` 본체와 상위 state orchestration은 계속 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.37 Batch 15 결과
- `static/js/wdcalculator/base-components-ui.js`를 확장해 `initBaseComponentsLiveInteractions()`와 add/click/input/change delegated handler를 포함시키고, host giant script에서는 해당 listener 4개를 제거한 뒤 bootstrap만 남겼다.
- extraction 이후 Node contract는 template source 추출 대신 확장된 helper 파일을 직접 로드하도록 바꿔 add row, fee add/remove, mode toggle, 30cm auto-sync, pricing-type column toggle surface를 module 기준으로 계속 검증하게 유지했다.
- base-components 기존 row render/read contract와 `/wdcalculator` render smoke를 함께 묶어 focused pytest `11 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.38 Post-base-live next preaudit 메모
- base row live interactions까지 빠진 뒤 남은 inline cluster를 재감리한 결과, 다음 안전 후보는 URL/deep-link bootstrap(`order_id` back link, `estimate_id` URL load, product-ready polling/timeout)이다.
- 이 묶음은 `loadEstimateToForm`, `loadSidebarEstimates`, `products.length` readiness, `URLSearchParams`, `setInterval`/`setTimeout` retry 흐름에 주로 묶여 있어 save/add/reset/list mutation cluster보다 상태 결합이 얇다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `calculateEstimate`, `collectCurrentEstimate`, `calculateTotalEstimates`, `refreshAfterSave`, `loadEstimateToInputForm`, `editingEstimateId` semantics이며, helper 쪽에는 URL param 해석과 async bootstrap orchestration만 이동시키는 것이 안전하다.
- 주요 회귀 포인트는 (1) product catalog readiness race, (2) `estimate_id` timeout/clearInterval 정리, (3) `order_id` back link 주입, (4) URL load 실패 시 console/error branch drift다.

### 2.4.39 URL bootstrap contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_url_bootstrap_contract_node.py` + `tests/support/wdcalculator_url_bootstrap_contract_node_checks.js`를 추가해 current inline URL bootstrap의 `order_id` back button, `estimate_id` fetch URL, products-ready 즉시 load, 100ms poll + 5s timeout, products-empty 1s retry alert, failed response alert contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 URL param 해석과 async bootstrap만 static helper로 옮기고, `loadEstimateToForm`/`loadSidebarEstimates` 본체와 state orchestration은 그대로 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.40 Batch 16 결과
- `static/js/wdcalculator/url-bootstrap.js`를 신설해 `order_id` back link 주입, `estimate_id` deep-link fetch, product-ready polling/timeout, post-load sidebar refresh를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `url-bootstrap.js`를 `render-estimates-list.js` 뒤, `order-match-ui.js` 앞에 로드하도록 갱신했고, host giant script는 `WdCalculatorUrlBootstrap.configure({ getProducts, loadEstimateToForm, loadSidebarEstimates })` + `initUrlBootstrap()` bootstrap만 남겼다.
- URL bootstrap Node contract는 template snippet 추출 대신 새 helper 파일을 직접 로드하도록 바꿔 extraction 이후에도 back button href, estimate fetch URL, poll/timeout, 1s retry alert, failure alert 분기를 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `url-bootstrap.js` load-order를 추가했고, adjacent search-load regression까지 묶어 focused pytest `11 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.41 Post-url next preaudit 메모
- URL bootstrap까지 빠진 뒤 남은 inline cluster를 재감리한 결과, 다음 안전 후보는 `refreshAfterSave` post-save refresh/highlight cluster다.
- 이 묶음은 `resetInputFormKeepCustomerName`, `renderEstimatesList`, `loadSidebarEstimates`, saved-row highlight DOM, nested `setTimeout` 흐름에 주로 묶여 있어 add/save/list main mutation cluster보다는 독립도가 높다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `calculateEstimate`, `collectCurrentEstimate`, `calculateTotalEstimates`, `editingEstimateId`, save payload assembly, `addEstimateBtn` main handler이며, helper 쪽에는 post-save clear/render/refresh/highlight orchestration만 이동시키는 것이 안전하다.
- 주요 회귀 포인트는 (1) `estimates = []` clear 타이밍, (2) `resetInputFormKeepCustomerName()` 호출 순서, (3) saved row highlight/badge DOM contract, (4) nested `setTimeout` delay drift다.

### 2.4.42 Refresh-after-save contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_refresh_after_save_contract_node.py` + `tests/support/wdcalculator_refresh_after_save_contract_node_checks.js`를 추가해 `refreshAfterSave(savedId)`의 `estimates` clear → `resetInputFormKeepCustomerName()` 순서, 50ms render delay, 추가 200ms sidebar refresh delay, saved row green highlight + `저장 완료` badge + 3초 cleanup, missing `.saved-estimate-customer-name` fallback, sidebar reload retry-once, outer catch 300ms fallback refresh contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 post-save clear/render/refresh/highlight orchestration만 static helper로 옮기고, `resetInputFormKeepCustomerName`, save payload assembly, `currentDatabaseEstimateId` update, `loadEstimateToForm` 본체는 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.43 Batch 17 결과
- `static/js/wdcalculator/refresh-after-save.js`를 신설해 저장 성공 뒤 local `estimates` clear, form reset, delayed `renderEstimatesList()`, delayed sidebar reload, saved row highlight/badge cleanup 흐름을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `refresh-after-save.js`를 `render-estimates-list.js` 뒤, `url-bootstrap.js` 앞에 로드하도록 갱신했고, host giant script는 상단 destructuring + 하단 `WdCalculatorRefreshAfterSave.configure({ setEstimates, resetInputFormKeepCustomerName, renderEstimatesList, loadSidebarEstimates })` bridge만 남겼다.
- refresh-after-save Node contract는 helper 파일을 직접 로드하도록 구성해 extraction 이후에도 clear→reset 순서, nested timeout delay, saved row badge cleanup, retry-once, 300ms fallback refresh 분기를 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `refresh-after-save.js` load-order를 추가했고, related WDCalculator regressions까지 묶어 focused pytest `12 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.44 Post-refresh next preaudit 메모
- `refreshAfterSave`까지 빠진 뒤 남은 inline cluster를 재감리한 결과, 다음 안전 후보는 `resetInputFormKeepCustomerName` reset cluster다.
- 이 묶음은 `editingEstimateId = null`, `ensureBaseComponentsUI(null)`, additional-options DOM clear, `WdCalculatorNotesUI.resetNotesToEmpty()`, result panel hide, totals/detail text reset, button visibility reset, customer-name restore, `calculateEstimate()`/`calculateTotalEstimates()` 재실행에 주로 묶여 있어 save handler나 `loadEstimateToForm` 본체보다 구조 경계가 상대적으로 얇다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `products`, `loadEstimateToForm`, `currentDatabaseEstimateId`, save button clone/replace, `editingEstimateId` 이후 add/save orchestration이며, helper 쪽에는 reset DOM/state orchestration만 이동시키는 것이 안전하다.
- 주요 회귀 포인트는 (1) `currentDatabaseEstimateId` 유지 계약, (2) `estimates.length === 0` 기반 save button hide 조건, (3) notes/base-components reset 실패 시 나머지 reset 계속 수행하는 fail-soft branch, (4) customer name restore와 reset 후 재계산 순서다.

### 2.4.45 Reset-input-form contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_reset_input_form_keep_customer_contract_node.py` + `tests/support/wdcalculator_reset_input_form_keep_customer_contract_node_checks.js`를 추가해 trimmed customer restore, `editingEstimateId = null`, `currentDatabaseEstimateId` 유지, `ensureBaseComponentsUI(null)`, additional-options clear, `WdCalculatorNotesUI.resetNotesToEmpty()` fail-soft branch, result sections/totals/detail/button reset, drafts 존재 시 save button 유지, outer catch의 customer 재복원 contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 reset DOM/state orchestration만 static helper로 옮기고, `currentDatabaseEstimateId`, DB load/save main orchestration, `loadEstimateToForm`/`loadEstimateToInputForm` 본체는 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.46 Batch 18 결과
- `static/js/wdcalculator/reset-input-form-keep-customer.js`를 신설해 고객명 보존 reset path(`editingEstimateId` reset, base-components/notes/additional-options reset, result section hide, totals/button reset, recalculate`)를 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `reset-input-form-keep-customer.js`를 `render-estimates-list.js` 뒤, `refresh-after-save.js` 앞에 로드하도록 갱신했고, host giant script는 상단 destructuring + 하단 `WdCalculatorResetInputFormKeepCustomer.configure({ setEditingEstimateId, getEstimatesLength, ensureBaseComponentsUI, resetNotesToEmpty, recalculate })` bridge만 남겼다.
- reset-input-form Node contract는 helper 파일을 직접 로드하도록 구성해 extraction 이후에도 customer restore, `currentDatabaseEstimateId` untouched semantics, inner fail-soft logging, outer catch recovery를 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `reset-input-form-keep-customer.js` load-order를 추가했고, related WDCalculator regressions까지 묶어 focused pytest `12 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.47 Post-reset next preaudit 메모
- `resetInputFormKeepCustomerName`까지 빠진 뒤 남은 inline cluster를 재감리한 결과, 다음 안전 후보는 `loadEstimateToInputForm` local edit-load cluster다.
- 이 묶음은 local `estimates[]`에서 한 항목을 찾아 base-components/option/notes UI로 복원하고, `editingEstimateId` 설정, add-button 수정모드 전환, scroll, `calculateEstimate()` 재실행, `isLoadingEstimate` finally 해제에 주로 묶여 있어 DB load/save, header/reset button, save payload assembly cluster보다 경계가 얇다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 `estimates` 배열 source, `isLoadingEstimate` guard를 사용하는 delegated click handler 본체, DB save/load orchestration, `currentDatabaseEstimateId`, 그리고 sidebar/main save 흐름이다. helper 쪽에는 local estimate → form restore orchestration만 이동시키는 것이 안전하다.
- 주요 회귀 포인트는 (1) invalid/missing estimate alert branch, (2) legacy single-product → base-components row fallback, (3) `loadAdditionalOptionRows`와 `loadNotes` restore 순서, (4) `editingEstimateId` 설정 후 add button text/display, (5) `finally { isLoadingEstimate = false; }` 보장이다.

### 2.4.48 Load-estimate-to-input contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_load_estimate_to_input_form_contract_node.py` + `tests/support/wdcalculator_load_estimate_to_input_form_contract_node_checks.js`를 추가해 confirm cancel 분기, invalid/missing id alert, base-components direct restore, legacy manual fallback, `loadAdditionalOptionRows(..., { formatPriceOnInput: true })`, `loadNotes(estimate.notes)`, add-button 수정모드 전환, scroll target 우선순위, caught error 이후 `isLoadingEstimate` finally 해제 contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 local estimate → form restore orchestration과 loading flag setter만 static helper로 옮기고, document-level click delegation의 나머지 edit-name/delete/card logic과 DB save/load orchestration은 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.49 Batch 19 결과
- `static/js/wdcalculator/load-estimate-to-input-form.js`를 신설해 local `estimates[]` 항목을 base-components/additional-options/notes UI로 복원하고, `editingEstimateId`, add-button edit mode, scroll, `calculateEstimate()`, `isLoadingEstimate` finally 해제를 담당하는 local edit-load 흐름을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `load-estimate-to-input-form.js`를 `reset-input-form-keep-customer.js` 뒤, `refresh-after-save.js` 앞에 로드하도록 갱신했고, host giant script는 상단 destructuring + 하단 `WdCalculatorLoadEstimateToInputForm.configure({ setLoadingState, getEditingEstimateId, getEstimates, normalizeId, isSameId, ensureBaseComponentsUI, resetNotesToEmpty, loadAdditionalOptionRows, loadNotes, setEditingEstimateId, calculateEstimate })` bridge만 남겼다.
- document click delegation에서는 `.edit-estimate-btn`와 card click이 더 이상 host에서 중복 `isLoadingEstimate = true`/`normalizeId(...)`를 처리하지 않고 raw dataset id만 helper에 넘기도록 얇아졌다.
- `/wdcalculator` render contract에는 `load-estimate-to-input-form.js` load-order를 추가했고, related WDCalculator regressions까지 묶어 focused pytest `11 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.50 Post-load-to-input next preaudit 메모
- `loadEstimateToInputForm`까지 빠진 뒤 남은 inline cluster를 재감리한 결과, 다음 안전 후보는 `loadEstimateToForm` saved-estimate hydrate cluster다.
- 이 묶음은 DB에서 읽어 온 `estimate` 객체를 받아 `currentDatabaseEstimateId`, header/reset button, customer/coupon/shipping inputs, notes reset, `estimates = []` 후 저장된 line-item hydrate, `renderEstimatesList`, save button visible, form reset, `calculateEstimate()`를 수행하는 하나의 진입점으로 caller(`WdCalculatorSearchResultsLoad`, sidebar estimates, URL bootstrap)가 공통 contract를 공유한다.
- extraction 시 host에 남겨야 하는 핵심 coupling은 save payload assembly/fetch/update main flow, `refreshAfterSave`, `currentDatabaseEstimateId` 이후 save handler 본체, 그리고 search/sidebar/url bootstrap bootstrap wiring이다. helper 쪽에는 saved-estimate hydrate orchestration만 이동시키는 것이 안전하다.
- 주요 회귀 포인트는 (1) `estimate_data.estimates` empty path가 render/calculate 없이 끝나는 현재 동작, (2) `generateEstimateId()` + `displayName` fallback mapping, (3) `notes: est.notes || globalNotes` fallback, (4) reset button 생성 vs 재사용, (5) unsanitized `headerTitle.innerHTML` 업데이트다.

### 2.4.51 Load-saved-estimate-to-form contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_load_saved_estimate_to_form_contract_node.py` + `tests/support/wdcalculator_load_saved_estimate_to_form_contract_node_checks.js`를 추가해 saved-estimate hydrate baseline을 먼저 고정했고, extraction 이후에는 같은 contract를 helper 파일 직접 로드 방식으로 계속 유지한다.
- 이 contract는 `currentDatabaseEstimateId` set → header/update + reset button create/reuse → customer/coupon/shipping hydrate → `WdCalculatorNotesUI.resetNotesToEmpty()` → `estimates = []` → saved line-item mapping (`String(id)`/`generateEstimateId()`, `displayName` fallback, `notes` global fallback) → `renderEstimatesList()` → save button visible → `ensureBaseComponentsUI()` → form reset → `calculateEstimate()` 순서와, `estimate_data.estimates = []`일 때 여기서 멈추는 empty path를 먼저 고정한다.
- 이 baseline 위에서 다음 extraction batch는 saved-estimate hydrate 전체를 하나의 helper로 옮기되, callers가 넘기는 `estimate` input contract와 empty-path semantics를 그대로 유지해야 한다.

### 2.4.52 Batch 20 결과
- `static/js/wdcalculator/load-saved-estimate-to-form.js`를 신설해 DB estimate hydrate path(`currentDatabaseEstimateId`, header/update, reset button create-or-reuse, customer/coupon/shipping hydrate, notes reset, saved line-item mapping, `renderEstimatesList`, save button visible, form reset, `calculateEstimate`)를 giant inline script 밖으로 분리했다.
- host giant script는 상단 `const { loadEstimateToForm: loadSavedEstimateToForm } = WdCalculatorLoadSavedEstimateToForm;` alias와 hoisted thin wrapper `function loadEstimateToForm(estimate) { loadSavedEstimateToForm(estimate); }`만 남기고, 하단 `WdCalculatorLoadSavedEstimateToForm.configure({ setCurrentDatabaseEstimateId, setEstimates, generateEstimateId, formatNumber, renderEstimatesList, ensureBaseComponentsUI, calculateEstimate, resetNotesToEmpty, confirmImpl, reloadImpl })` bridge로 의존성을 주입한다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `load-saved-estimate-to-form.js`를 `load-estimate-to-input-form.js` 뒤, `refresh-after-save.js` 앞에 로드하도록 갱신했다.
- saved-estimate hydrate Node contract는 helper 파일을 직접 로드하도록 바꿔 extraction 이후에도 reset button create/reuse, empty-estimates path, line-item `displayName`/`notes` fallback baseline을 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `load-saved-estimate-to-form.js` load-order를 추가했고, related WDCalculator regressions까지 묶어 focused pytest `11 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.53 Post-load-saved next preaudit 메모
- `loadEstimateToForm`까지 빠진 뒤 남은 inline main mutation cluster를 비교 감리한 결과, 다음 안전 후보는 `saveEstimateBtn` clone/replace + save fetch orchestration이다.
- `addEstimateBtn` local add/update path는 두 개의 click listener(`main add/update orchestration` + `originalAddEstimate` follow-up save-button show`)와 전체 reset stack이 얽혀 있어, 현재 단계에서는 저장 버튼 쪽이 구조-only extraction 경계가 더 선명하다.
- 다음 contract freeze에서 먼저 고정해야 할 포인트는 (1) `cloneNode(true)` + `replaceChild` 1회 바인딩 계약, (2) `estimates.length === 0`일 때 `collectCurrentEstimate()` + `generateEstimateId()`로 synthesized save path, (3) `estimate_data` payload shape + `resolveWdcAggregateTotals(...)` totals contract, (4) fetch 중 버튼 disable/spinner와 success/error 공통 복원, (5) success 시 `currentDatabaseEstimateId`/header update 뒤 `refreshAfterSave(...)` 호출 순서다.

### 2.4.54 Save-estimate contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_save_estimate_contract_node.py` + `tests/support/wdcalculator_save_estimate_contract_node_checks.js`를 추가해 `saveEstimateBtn` clone/replace 1회 바인딩, customer name 필수 입력, `estimates.length === 0`일 때 `collectCurrentEstimate()` + `generateEstimateId()` synthesized save path, `resolveWdcAggregateTotals(...)` payload shape, fetch 중 button disable/spinner, success/failed response/fetch error에서의 button restore와 alert/refresh ordering contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 save button clone/replace + fetch orchestration만 static helper로 옮기고, `addEstimateBtn` local mutation/reset stack과 save-button show follow-up listener는 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.55 Batch 21 결과
- `static/js/wdcalculator/save-estimate.js`를 신설해 save button clone/replace, 빈 local estimates일 때 `collectCurrentEstimate()` fallback, coupon/shipping/notes 수집, aggregate totals payload 조립, `/api/wdcalculator/save-estimate` fetch, button spinner/restore, success 시 `currentDatabaseEstimateId`/header update + `refreshAfterSave(...)` 호출 흐름을 giant inline script 밖으로 분리했다.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`는 `save-estimate.js`를 `load-saved-estimate-to-form.js` 뒤, `refresh-after-save.js` 앞에 로드하도록 갱신했고, host giant script는 상단 destructuring + 하단 `WdCalculatorSaveEstimate.configure({ getCurrentDatabaseEstimateId, setCurrentDatabaseEstimateId, getEstimates, collectCurrentEstimate, generateEstimateId, collectNotes, getCouponValue, resolveAggregateTotals, refreshAfterSave, fetchImpl, alertImpl, consoleRef })` bridge와 `initSaveEstimateButton()`만 남겼다.
- save-estimate Node contract는 helper 파일을 직접 로드하도록 구성해 extraction 이후에도 clone/replace 1회 바인딩, synthesized estimate save path, aggregate/fetch error branch, success refresh ordering baseline을 계속 검증하게 유지했다.
- `/wdcalculator` render contract에는 `save-estimate.js` load-order를 추가했고, related WDCalculator regressions까지 묶어 focused pytest `11 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.56 Post-save-estimate next preaudit 메모
- `saveEstimateBtn`까지 빠진 뒤 남은 inline main mutation cluster를 비교 감리한 결과, 다음 안전 후보는 `addEstimateBtn` local add/update orchestration이다.
- 이 묶음은 main click handler에서 `collectCurrentEstimate()` → add vs update 분기 → `displayName`/`productName` 유지 규칙 → `renderEstimatesList()` → full reset pipeline을 수행하고, 별도의 두 번째 click listener가 `originalAddEstimate`와 save-button show follow-up을 담당한다. 따라서 다음 contract freeze는 두 listener를 함께 고려해야 한다.
- 먼저 고정해야 할 포인트는 (1) `editingEstimateId` 존재 시 original ID 유지, (2) product/width change 여부에 따라 `displayName` 유지 vs 최신값 갱신, (3) missing editing target alert branch, (4) add/update 후 reset pipeline과 customer name restore, (5) secondary listener의 `estimates.length > 0` 기반 save button show semantics다.

### 2.4.57 Add-estimate contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_add_estimate_contract_node.py` + `tests/support/wdcalculator_add_estimate_contract_node_checks.js`를 추가해 `addEstimateBtn` primary/follow-up 2개 click listener binding, add mode `generateEstimateId()` append path, update mode의 original ID 유지, product/width match 시 `displayName` preserve, width change 시 최신 `displayName`/`productName` refresh, missing editing target alert/log branch, original `onclick` replay + save button visibility contract를 먼저 고정했다.
- 이 baseline으로 다음 extraction batch는 add/update local mutation과 follow-up save-button listener만 helper로 옮기고, reset 세부 구현은 이미 분리된 `reset-input-form-keep-customer.js`를 재사용하는 구조-only 변경만 허용한다.

### 2.4.58 Batch 22 결과
- `static/js/wdcalculator/add-estimate.js`를 신설해 add/update listener의 local estimate mutation, `normalizeId(editingEstimateId)` 분기, original ID 유지, `displayName` preserve vs refresh 규칙, follow-up save-button show listener를 giant inline script 밖으로 분리했다.
- host giant script에서는 두 개의 inline addEstimate listeners와 중복 reset stack을 제거하고, `WdCalculatorAddEstimate.configure({ getEditingEstimateId, setEditingEstimateId, getEstimates, collectCurrentEstimate, normalizeId, isSameId, generateEstimateId, renderEstimatesList, resetInputFormKeepCustomerName, alertImpl, consoleRef })` bridge + `initAddEstimateButton()`만 남겼다.
- reset path는 기존에 분리된 `resetInputFormKeepCustomerName()` helper를 재사용하도록 정리해, add/update 이후 reset/customer-name/save-button/recalc semantics는 이미 고정된 helper contract에 계속 위임되도록 만들었다.
- `/wdcalculator` render contract에는 `add-estimate.js` load-order를 추가했고, related WDCalculator regressions까지 묶어 focused pytest `12 passed`와 `APP_OK`로 extraction 이후 baseline을 재검증했다.

### 2.4.59 Post-add-estimate next preaudit 메모
- `addEstimateBtn`까지 빠진 뒤 남은 inline cluster를 비교 감리한 결과, 다음 안전 후보는 `#estimatesListContainer` 이벤트 위임 클러스터다.
- 범위는 `.edit-estimate-btn`, `.edit-estimate-name-btn` 인라인 이름 편집, `.delete-estimate-btn`, `.card[data-estimate-id]` 카드 클릭, `isLoadingEstimate` 가드까지 포함한 **목록 UI 상호작용 전용 경계**다.
- 대안이던 `calculateEstimate` / `calculateTotalEstimates` / `collectCurrentEstimate`는 여전히 가격 정책·DOM 갱신·`editingEstimateId` 분기와 결합이 넓어 회귀면이 크다. 반면 목록 이벤트 위임은 가격 계산과 직접 결합이 적고 selector/runtime contract가 더 뚜렷해 다음 구조-only batch로 더 안전하다.
- 먼저 고정해야 할 포인트는 (1) `#estimatesListContainer` 내부 위임 범위, (2) `.edit-estimate-name-btn` 인라인 편집 UI selector와 저장/취소/blur 200ms 지연 커밋, (3) `.delete-estimate-btn` confirm/삭제 후 `setEstimates(...)` + active edit 해제 + `renderEstimatesList()`, (4) `.card[data-estimate-id]` 클릭의 button 제외 규칙, (5) `isLoadingEstimate` 가드와 `loadEstimateToInputForm()` 호출 차단 semantics다.

### 2.4.60 Estimate-list-events contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_estimate_list_events_contract_node.py` + `tests/support/wdcalculator_estimate_list_events_contract_node_checks.js`를 추가해 delegated list interactions baseline을 먼저 고정했고, extraction 이후에도 helper 파일을 직접 로드해 같은 contract를 계속 검증한다.
- 이 contract는 (1) `initEstimateListEvents()`의 document click binding, (2) `.edit-estimate-btn` delegated load 진입, (3) `isLoadingEstimate`가 true일 때 delegated action 전체 차단, (4) `.edit-estimate-name-btn` 인라인 편집 UI 생성과 focus/select timer(0ms), save click 뒤 cleanup 선행 + rerender timer(10ms), (5) blur auto-save의 200ms 지연 커밋, (6) `.delete-estimate-btn` confirm message + `setEstimates(...)` + active edit 해제 + add button label reset, (7) `.card[data-estimate-id]` 클릭의 button 제외 규칙을 helper 기준으로 먼저 묶는다.
- 이 baseline 위에서 다음 extraction batch는 click delegation 전체를 하나의 helper로 옮기되, `estimates` direct mutation(displayName edit) vs `setEstimates(...)`(delete) 경계를 그대로 유지하는 구조-only 변경만 허용한다.

### 2.4.61 Batch 23 결과
- `static/js/wdcalculator/estimate-list-events.js`를 신설해 `#estimatesListContainer` delegated interaction 전체(수정 버튼, 이름 인라인 편집, 삭제, 카드 클릭, `isLoadingEstimate` 가드)를 giant inline script 밖으로 분리했다.
- host giant script에서는 raw document click handler를 제거하고, `let isLoadingEstimate = false` shared state만 유지한 채 `WdCalculatorEstimateListEvents.configure({ getLoadingState, getEstimates, setEstimates, getEditingEstimateId, setEditingEstimateId, loadEstimateToInputForm, renderEstimatesList, formatNumber, normalizeId, isSameId, confirmImpl, setTimeoutImpl, consoleRef })` bridge + `initEstimateListEvents()`만 남겼다.
- 이름 인라인 편집은 기존과 동일하게 `displayName`을 local `estimates[]` 배열에 직접 mutate한 뒤 cleanup 선행 + 10ms rerender timer를 유지했고, 삭제 path는 기존 reassignment semantics에 맞춰 `setEstimates(...)` bridge만 사용하도록 정리했다.
- `/wdcalculator` render contract에는 `estimate-list-events.js` load-order를 추가했고, 관련 WDCalculator regressions(`estimate-list-events`, `load-estimate-to-input-form`, `render-estimates-list`, `add-estimate`, render/order smoke)과 `APP_OK`를 다시 통과시켜 extraction 이후 baseline을 재검증했다.

### 2.4.62 Post-estimate-list-events next preaudit 메모
- `#estimatesListContainer` delegated interaction까지 빠진 뒤 남은 inline cluster를 비교 감리한 결과, 다음 안전 후보는 `calculateTotalEstimates()` aggregate summary display cluster다.
- 이 묶음은 이미 분리된 `estimate-totals.js` 정책 helper 위에서 `coupon/shipping` DOM read, aggregate totals helper 호출, current summary/detail DOM write(`editingEstimateId` guard 포함), overall summary panel DOM write, notes display toggle만 담당하는 **aggregate display orchestration 전용 경계**다.
- 반면 `calculateEstimate()` / `collectCurrentEstimate()`는 여전히 current estimate math, 버튼 표시 전이, `saveEstimateBtn` visibility, per-form detail hydrate까지 넓게 결합되어 있어 회귀면이 더 크다. aggregate display 쪽이 현재 단계의 다음 structure-only batch로 더 안전하다.
- 다음 contract freeze에서 먼저 고정해야 할 포인트는 (1) `estimates.length === 0` zero-state reset path, (2) coupon/shipping DOM read + `resolveWdcAggregateTotals(...)` 호출 shape, (3) `editingEstimateId`가 있을 때 current summary panel overwrite를 막는 guard, (4) option aggregation/grouping detail text, (5) `notesDisplaySection` show/hide, (6) `totalAllPrice` optional element 부재 허용 semantics다.

### 2.4.63 CalculateTotalEstimates contract freeze 결과
- 신규 Node regression `tests/test_wdcalculator_calculate_total_estimates_contract_node.py` + `tests/support/wdcalculator_calculate_total_estimates_contract_node_checks.js`를 추가해 inline `calculateTotalEstimates()` orchestration baseline을 helper 추출 전에 먼저 고정했다.
- 이 contract는 (1) `estimates.length === 0`일 때 current summary/detail zero-state reset, (2) `getCouponValue()` + shipping DOM read(`shippingCost`, `shippingIncluded`) 뒤 `resolveWdcAggregateTotals(...)` 호출 shape, (3) non-editing path에서 current summary/detail + overall summary panel DOM write, (4) option aggregation detail의 이름별 quantity/amount group, (5) `notesDisplaySection` show/hide, (6) `totalAllPrice` optional element 부재 허용, (7) `editingEstimateId`가 있을 때 current summary panel overwrite 차단, (8) aggregate helper throw 시 alert/log 후 downstream DOM write 중단을 현재 inline 함수 기준으로 먼저 묶는다.
- 이 baseline 위에서 다음 extraction batch는 aggregate display orchestration만 static helper로 옮기고, 가격 계산 정책(`estimate-totals.js`)과 current estimate math(`calculateEstimate` / `collectCurrentEstimate`)는 그대로 host giant script에 남기는 구조-only 변경만 허용한다.

### 2.4.64 CalculateTotalEstimates UI batch 결과
- `static/js/wdcalculator/total-estimates-display.js`를 신설해 `calculateTotalEstimates()`의 zero-state reset, coupon/shipping DOM read, option aggregation detail text, `editingEstimateId` guard, notes summary toggle, overall summary DOM write를 giant inline script 밖으로 분리했다.
- host giant script는 `WdCalculatorTotalEstimatesDisplay.configure({ getEstimates, getEditingEstimateId, getCouponValue, resolveAggregateTotals, collectNotes, formatNumber, applyFinalPriceStyle, applyCouponDiscountStyle, documentRef, alertImpl, consoleRef })` bridge와 alias만 유지하고, 기존 inline `calculateTotalEstimates()` 본체는 제거했다.
- `tests/support/wdcalculator_calculate_total_estimates_contract_node_checks.js`는 helper 파일을 직접 로드하는 형태로 전환해 extraction 이후에도 동일 contract(zero-state, helper 호출 shape, editing guard, notes/summary DOM write, optional `totalAllPrice`, helper error stop)를 계속 고정한다.
- focused pytest `13 passed`, `APP_OK`, 신규 lint 없음으로 UI batch를 닫았다.

### 2.4.65 Post-total-estimates next preaudit 메모
- aggregate display orchestration까지 빠진 뒤 남은 inline cluster를 비교 감리한 결과, 다음 최소 안전 후보는 helper-load guard pair(`resolveWdcCurrentEstimateMath`, `resolveWdcAggregateTotals`)다.
- 이 두 함수는 DOM/state(`estimates`, `editingEstimateId`, button visibility, notes UI)를 직접 건드리지 않고, `window.wdcComputeCurrentEstimateMath` / `window.wdcComputeAggregateTotals` 존재 여부를 검사한 뒤 동일 인자를 pass-through 하는 가장 얇은 경계다.
- 반면 `beforeunload` guard는 user-visible browser prompt contract가 있고, `addOptionBtn`/layout sync wiring은 더 작지만 giant script 축소 효과가 작다. `calculateEstimate()`/`collectCurrentEstimate()`는 여전히 DOM/button/state 결합면이 크므로 resolver pair가 더 안전하다.
- 다음 contract freeze 포인트는 (1) current/aggregate helper의 exact call signature, (2) helper 미로드 시 현재 오류 문자열 보존, (3) return value pass-through semantics다.

### 2.4.66 Calculation resolver pair batch 결과
- `static/js/wdcalculator/calculation-resolvers.js`를 신설해 `resolveWdcCurrentEstimateMath()`와 `resolveWdcAggregateTotals()`를 giant inline script 밖으로 분리했다.
- host giant script는 `WdCalculatorCalculationResolvers` alias만 남기고 두 inline guard 함수를 제거했다. 이로써 current estimate 경로(`calculateEstimate`, `collectCurrentEstimate`)와 aggregate display/save payload 경로가 모두 같은 thin resolver module을 경유하게 됐다.
- 신규 Node regression `tests/test_wdcalculator_calculation_resolvers_contract_node.py` + `tests/support/wdcalculator_calculation_resolvers_contract_node_checks.js`를 추가해 current/aggregate helper pass-through signature와 helper 미로드 시의 명시적 오류 문자열을 helper 기준으로 고정했다.
- 기존 `tests/support/wdcalculator_current_estimate_contract_node_checks.js`도 새 resolver helper를 쓰도록 갱신해 current estimate DOM summary vs collected snapshot contract가 extraction 이후에도 유지되도록 맞췄다.
- focused pytest `13 passed`, `APP_OK`, 신규 lint 없음으로 resolver batch를 닫았다.

### 2.4.67 Post-calculation-resolvers next preaudit 메모
- resolver pair까지 빠진 뒤 남은 giant inline cluster를 다시 비교 감리한 결과, 다음 안전 후보는 `beforeunload` unsaved-exit guard다.
- 이 listener는 `estimates.length > 0`일 때만 `preventDefault()`와 `returnValue`를 설정하는 단일 브라우저 contract로 경계가 얇고, current estimate/save/list/sidebar 로직과 직접 결합하지 않는다.
- runner-up은 `addOptionBtn` click wiring과 layout sync wiring(`requestWdCalculatorLayoutSync`)이다. 둘 다 얇지만 giant script 정리 효과는 `beforeunload` guard와 비슷하거나 더 작다.
- 다음 단계에서는 `beforeunload` guard의 문구/이벤트 부작용 contract를 먼저 freeze하고, tiny helper 또는 thin guard module로 옮길지 결정한다.

### 2.4.68 Beforeunload guard batch 결과
- `static/js/wdcalculator/unsaved-exit-guard.js`를 신설해 미저장 견적 이탈 경고 listener를 giant inline script 밖으로 분리했다.
- host giant script에서는 inline `window.addEventListener('beforeunload', ...)`를 제거하고 `WdCalculatorUnsavedExitGuard.configure({ getEstimates, windowRef })` + `initUnsavedExitGuard()`만 남겼다.
- 신규 Node regression `tests/test_wdcalculator_unsaved_exit_guard_contract_node.py` + `tests/support/wdcalculator_unsaved_exit_guard_contract_node_checks.js`를 추가해 (1) beforeunload listener 등록, (2) `estimates.length === 0`일 때 no-op, (3) `estimates.length > 0`일 때 exact warning message + `preventDefault`/`returnValue` side effect를 helper 기준으로 고정했다.
- focused pytest `12 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.69 Post-beforeunload next preaudit 메모
- `beforeunload` guard까지 빠진 뒤 남은 giant inline cluster를 재감리한 결과, 다음 안전 후보는 `addOptionBtn` click wiring이다.
- 이 블록은 `#addOptionBtn` null-check와 `appendAdditionalOptionRow(container, { forceMode: 'select', formatPriceOnInput: false })` 호출만 담당하는 순수 DOM wiring이어서 `calculateEstimate`/save/list/sidebar state와 직접 결합하지 않는다.
- layout sync wiring과 `calculateBtn` click wiring도 얇지만, add-option 쪽은 이미 분리된 `additional-options-ui.js` row helper를 재사용하는 명확한 extraction 경계가 있다.
- 다음 contract freeze 포인트는 (1) button 존재 시 click listener binding, (2) `#additionalOptionsContainer` lookup, (3) append call option shape 유지, (4) missing button/container branch다.

### 2.4.70 Add-option button batch 결과
- `static/js/wdcalculator/add-option-button.js`를 신설해 `#addOptionBtn` click wiring을 giant inline script 밖으로 분리했다.
- host giant script에서는 raw button lookup/click binding을 제거하고 `WdCalculatorAddOptionButton.configure({ documentRef, appendAdditionalOptionRow })` bridge + `initAddOptionButton()`만 남겼다.
- 신규 Node regression `tests/test_wdcalculator_add_option_button_contract_node.py` + `tests/support/wdcalculator_add_option_button_contract_node_checks.js`를 추가해 (1) button 존재 시 단일 click binding, (2) `#additionalOptionsContainer` lookup, (3) `appendAdditionalOptionRow(container, { forceMode: 'select', formatPriceOnInput: false })` option shape 유지, (4) missing button/container branch를 helper 기준으로 고정했다.
- 관련 인접 회귀(`additional-options-ui`, product settings load-order, current estimate contract)를 함께 재검증했고 focused pytest `13 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.71 Post-add-option next preaudit 메모
- add-option wiring까지 빠진 뒤 남은 giant inline cluster를 다시 비교 감리한 결과, 다음 최소 안전 후보는 `calculateBtn` click wiring이다.
- 이 블록은 `#calculateBtn` null-check와 `calculateEstimate()` 단일 호출만 담당하므로, `loadEstimateToForm` wrapper나 layout sync wiring보다 테스트/회귀면이 가장 작다.
- runner-up은 layout sync wiring(`resize`/`load` → `requestWdCalculatorLayoutSync`)과 sidebar bootstrap(`window.initWdCalculatorSidebarEstimates(...)`)이다.
- 다음 단계에서는 `calculateBtn` click binding의 null-guard + single-call contract를 먼저 freeze하고, tiny helper 또는 bootstrap wiring module로 분리한다.

### 2.4.72 Calculate button batch 결과
- `static/js/wdcalculator/calculate-button.js`를 신설해 `#calculateBtn` null-check + `calculateEstimate()` 단일 click bridge를 giant inline script 밖으로 분리했다.
- host giant script에서는 raw button lookup/click binding을 제거하고 `WdCalculatorCalculateButton.configure({ documentRef, calculateEstimate })` + `initCalculateButton()`만 남겼다.
- 신규 Node regression `tests/test_wdcalculator_calculate_button_contract_node.py` + `tests/support/wdcalculator_calculate_button_contract_node_checks.js`를 추가해 (1) button 존재 시 단일 click binding, (2) click/direct handler의 `calculateEstimate()` 단일 호출, (3) missing button branch를 helper 기준으로 고정했다.
- 관련 인접 회귀(`add-option-button`, `unsaved-exit-guard`, product settings load-order 포함)를 함께 재검증했고 focused pytest `13 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.73 Post-calculate-button next preaudit 메모
- calculate button까지 빠진 뒤 남은 inline cluster를 다시 비교 감리한 결과, 다음 실익 기준 후보는 layout sync wiring(`resize`/`load` → `requestWdCalculatorLayoutSync`)이다.
- `loadEstimateToForm` wrapper alias가 더 얇지만 helper/file 하나를 추가할 만큼 독립적인 surface가 작고, giant script 감소 효과도 제한적이다.
- 다음 contract freeze 포인트는 (1) resize/load listener 등록, (2) 동일 sync handler 재사용, (3) immediate sync 1회, (4) missing `windowRef` no-op branch다.

### 2.4.74 Layout sync wiring batch 결과
- `static/js/wdcalculator/layout-sync-wiring.js`를 신설해 `resize`/`load` listener와 초기 `requestWdCalculatorLayoutSync()` 호출을 giant inline script 밖으로 분리했다.
- host giant script에서는 raw `window.addEventListener(...)` 2개와 immediate sync 호출을 제거하고 `WdCalculatorLayoutSyncWiring.configure({ windowRef, requestLayoutSync })` + `initLayoutSyncWiring()`만 남겼다.
- 신규 Node regression `tests/test_wdcalculator_layout_sync_wiring_contract_node.py` + `tests/support/wdcalculator_layout_sync_wiring_contract_node_checks.js`를 추가해 (1) resize/load listener 등록, (2) shared handler 유지, (3) immediate sync 1회, (4) missing `windowRef` no-op branch를 helper 기준으로 고정했다.
- 관련 인접 회귀(`calculate-button`, `add-option-button`, `unsaved-exit-guard`, product settings load-order 포함)를 함께 재검증했고 focused pytest `13 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.75 Post-layout-sync next preaudit 메모
- layout sync wiring까지 빠진 뒤 남은 저위험 후보를 다시 비교 감리한 결과, 다음 실익 기준 후보는 sidebar bootstrap(`window.initWdCalculatorSidebarEstimates(...)` + `loadSidebarEstimates` pass-through)이다.
- `loadEstimateToForm` wrapper alias, `loadProducts()` 초기 호출, `ensureBaseComponentsUI()` terminal init call도 더 얇지만, 구조 분해 체감 효과와 runtime bridge surface는 sidebar bootstrap 쪽이 더 크다.
- 다음 단계에서는 bootstrap call shape `{ loadEstimateToForm, formatNumber: window.formatNumber }`와 returned API에서 `loadSidebarEstimates`를 host에 그대로 bridge하는 contract를 먼저 고정한 뒤, existing `sidebar-estimates.js` 흡수 또는 thin bootstrap helper 분리 중 더 얇은 경로를 확정한다.

### 2.4.76 Sidebar bootstrap batch 결과
- `static/js/wdcalculator/sidebar-bootstrap.js`를 신설해 raw `window.initWdCalculatorSidebarEstimates(...)` 호출과 returned sidebar API bridge를 giant inline script 밖으로 분리했다.
- host giant script에서는 inline global init block을 제거하고 `WdCalculatorSidebarBootstrap.configure({ initSidebarEstimates, loadEstimateToForm, formatNumber: window.formatNumber })` + `initSidebarBootstrap()`만 남겼다.
- 신규 Node regression `tests/test_wdcalculator_sidebar_bootstrap_contract_node.py` + `tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js`를 추가해 (1) bootstrap option shape에서 `loadEstimateToForm`/`formatNumber` reference 보존, (2) returned API의 `loadSidebarEstimates`/`deleteEstimate` ref pass-through를 helper 기준으로 고정했다.
- 관련 인접 회귀(`calculate-button`, `layout-sync-wiring`, product settings load-order 포함)를 함께 재검증했고 focused pytest `12 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.77 Post-sidebar-bootstrap next preaudit 메모
- sidebar bootstrap까지 빠진 뒤 남은 저위험 후보를 다시 비교 감리한 결과, 다음 최소 안전 후보는 `loadEstimateToForm` wrapper alias다.
- 이 블록은 `loadSavedEstimateToForm(estimate)` call-through만 담당하므로 contract 면적이 매우 작고, helper 신설보다 wrapper 제거/alias 치환이 더 얇은 경로일 가능성이 높다.
- runner-up은 `loadProducts()` 초기 호출, `ensureBaseComponentsUI()` terminal init call, empty-category warning이며, 다음 단계에서는 wrapper alias의 call-through contract를 먼저 고정한 뒤 더 적은 파일 churn 경로를 선택한다.

### 2.4.78 LoadEstimate wrapper alias batch 결과
- inline `function loadEstimateToForm(estimate) { loadSavedEstimateToForm(estimate); }` wrapper를 제거하고 `loadSavedEstimateToForm` reference를 `WdCalculatorSearchResultsLoad.configure`, `WdCalculatorSidebarBootstrap.configure`, `WdCalculatorUrlBootstrap.configure`에 직접 주입하도록 정리했다.
- host render regression은 wrapper function 부재, direct wiring 3곳, `calculateTotalEstimates` alias가 `WdCalculatorCouponShippingWiring.configure(...)`보다 먼저 선언되는 TDZ-safe ordering을 함께 고정했다.
- 관련 인접 회귀(`product_settings`, `search-load`, `sidebar-bootstrap`, `url-bootstrap`, `load-saved-estimate-to-form`)를 함께 재검증했고 focused pytest `14 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.79 Post-loadEstimate-wrapper next preaudit 메모
- wrapper alias 제거 뒤 남은 저위험 후보를 다시 비교 감리한 결과, 다음 최소 안전 후보는 early startup init calls 7개와 empty-category warning branch였다.
- 이 블록은 이미 분리된 helper들을 같은 순서로 호출하고 마지막에 `console.warn` 1회만 수행하므로 구조-only shell helper로 빼기 적합하다.
- `loadProducts()` 초기 호출과 `ensureBaseComponentsUI()` terminal init call은 더 얇지만, template-level ordering contract를 별도로 고정해야 해서 startup shell보다 한 단계 뒤로 미뤘다.

### 2.4.80 Startup init shell batch 결과
- `static/js/wdcalculator/startup-init.js`를 신설해 raw early startup calls(`bindProductSelect`, `initBaseComponentsLiveInteractions`, `initAddOptionButton`, `initCalculateButton`, `initSearchResultsLoadBridge`, `bindOrderMatchButtons`, `initCouponShippingWiring`)와 empty-category `console.warn`를 giant inline script 밖으로 분리했다.
- host giant script에서는 raw init block을 제거하고 `WdCalculatorStartupInit.configure({ categories, consoleRef, ... })` + `initStartupInteractions()`만 남겼다.
- 신규 Node regression `tests/test_wdcalculator_startup_init_contract_node.py` + `tests/support/wdcalculator_startup_init_contract_node_checks.js`를 추가해 (1) startup call order 7개 보존, (2) empty-category warning exact string/no-warning branch를 helper 기준으로 고정했다.
- render contract에는 `startup-init.js` load order와 host shell 치환(기존 raw init calls/inline warning 부재)을 함께 추가했고, 관련 인접 회귀까지 포함해 focused pytest `16 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.81 Post-startup-init next preaudit 메모
- startup shell까지 빠진 뒤 남은 저위험 후보를 다시 비교 감리한 결과, 다음 최소 안전 후보는 `loadProducts()` 초기 호출과 `ensureBaseComponentsUI()` terminal init call이다.
- 두 호출 모두 이미 분리된 module API의 direct call이므로 shell/helper로 빼는 것은 가능하지만, `loadProducts()`는 sidebar bootstrap 전, `ensureBaseComponentsUI()`는 URL bootstrap 후라는 template-level ordering contract를 먼저 고정해야 안전하다.
- 큰 리스크 영역인 `calculateEstimate()`/`collectCurrentEstimate()`는 current-estimate contract가 이미 유지되고 있으므로, 다음 단계에서도 terminal init shell 같은 더 얇은 경계부터 계속 줄이는 편이 낫다.

### 2.4.82 Terminal init shell batch 결과
- `static/js/wdcalculator/terminal-init.js`를 신설해 raw terminal bootstrap call인 `loadProducts()`와 `ensureBaseComponentsUI()`를 giant inline script 밖으로 분리했다.
- host giant script에서는 `WdCalculatorTerminalInit.configure({ loadProducts, ensureBaseComponentsUI })` 후 기존 위치에 `loadInitialProducts()`와 `renderInitialBaseComponentsUi()`만 남겨, 초기 product load는 sidebar bootstrap 전, base-components 기본 1행 보장은 URL bootstrap 후라는 상대 순서를 그대로 유지했다.
- 신규 Node regression `tests/test_wdcalculator_terminal_init_contract_node.py` + `tests/support/wdcalculator_terminal_init_contract_node_checks.js`를 추가해 (1) `loadInitialProducts()` → `loadProducts()` exact target/result pass-through, (2) `renderInitialBaseComponentsUi()` → `ensureBaseComponentsUI()` exact target/result pass-through를 helper 기준으로 고정했다.
- render contract에는 `terminal-init.js` load order와 host ordering(`loadInitialProducts()`는 `WdCalculatorSidebarBootstrap.configure(...)` 전, `renderInitialBaseComponentsUi()`는 `initUrlBootstrap()` 후)을 함께 추가했고, 관련 인접 회귀까지 포함해 focused pytest `18 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.83 Post-terminal-init next preaudit 메모
- terminal shell까지 빠진 뒤 remaining inline cluster를 다시 감리한 결과, 더 이상 의미 있는 저위험 structure-only 후보는 사실상 남지 않았다.
- 남은 실질적 큰 inline 코어는 `calculateEstimate()`와 `collectCurrentEstimate()`이며, 특히 `calculateEstimate()`는 DOM refs, coupon/readout, `editingEstimateId`/`estimates`, style helpers, resolver guard를 함께 다루는 가장 큰 결합 지점이라 다음 batch의 자연스러운 우선순위다.
- 다음 단계는 thin shell extraction이 아니라, `calculateEstimate()`를 먼저 대상으로 injected dependency boundary를 다시 설계하고 existing current-estimate contract를 기준으로 contract-first 고위험 분해를 시작하는 쪽이 맞다.

### 2.4.84 Current-estimate orchestration batch 결과
- `static/js/wdcalculator/current-estimate-orchestration.js`를 신설해 `calculateEstimate()`와 `collectCurrentEstimate()`의 DOM/state orchestration을 giant inline script 밖으로 분리했다. 기존 `current-estimate-math.js`는 순수 가격 계산을 유지하고, 새 helper는 `readBaseComponentsFromUI`, `readAdditionalOptionRowsFromUI`, `resolveCurrentEstimateMath`, `getCouponValue`, `collectNotes`, `editingEstimateId`/`estimates` 상태를 주입받아 render/snapshot만 담당한다.
- host giant script에서는 inline `function calculateEstimate()` / `function collectCurrentEstimate()`를 제거하고 `const { calculateEstimate, collectCurrentEstimate } = WdCalculatorCurrentEstimateOrchestration;` alias + `WdCalculatorCurrentEstimateOrchestration.configure({...})` wiring만 남겼다. 이 과정에서 host에서 암묵적으로 남아 있던 `collectNotes` bare identifier도 `const { collectNotes } = WdCalculatorNotesUI;`로 명시해 notes/save/current-estimate contract를 동일한 module export 경로로 정렬했다.
- `tests/support/wdcalculator_current_estimate_contract_node_checks.js`는 template function extract 방식에서 새 helper 직접 실행 방식으로 전환했고, 기존 DOM-summary vs snapshot parity 외에 coupon render/final price DOM/edit-mode button visibility/empty-base reset contract까지 함께 고정했다.
- render contract에는 `current-estimate-orchestration.js` load order와 host direct wiring/inline body 제거를 추가했고, 인접 회귀(`calculate-button`, `coupon-shipping-wiring`, `product-catalog`, `load-estimate-to-input-form`, `load-saved-estimate-to-form`, `add-estimate`, `save-estimate`, `total-estimates`, resolver, render contract)를 함께 재검증했다. focused pytest `23 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.85 Post-current-estimate next preaudit 메모
- current-estimate orchestration까지 빠진 뒤 남은 giant host script는 사실상 mutable state registry + bootstrap ordering shell이다. 남은 핵심 결합점은 `products`, `estimates`, `editingEstimateId`, `currentDatabaseEstimateId`, `isLoadingEstimate`의 단일 source와 각 helper configure block에 흩어진 getter/setter lambda 반복이다.
- 다음 최소 안전 후보는 기능 helper 추가 분리가 아니라 host state store preaudit이다. 특히 `product-catalog-ui`, `load-saved-estimate-to-form`, `add-estimate`, `estimate-list-events`, `save-estimate`, `refresh-after-save`, `reset-input-form-keep-customer`, `load-estimate-to-input-form`가 같은 상태를 다른 방향으로 mutate하므로 stale closure 없이 중앙화 가능한지 먼저 감리해야 한다.
- 다음 단계에서는 (1) state mutation surface inventory, (2) bootstrap ordering(`initStartupInteractions()` → `initNotesUi()` → `loadInitialProducts()` → `initSidebarBootstrap()` → `initUrlBootstrap()` → `renderInitialBaseComponentsUi()`) freeze 필요 여부, (3) thin `wdcalculator-state-store.js` 또는 bootstrap shell helper로 안전하게 줄일 수 있는지 우선순위를 결정한다.

### 2.4.86 Host-state preaudit 결과
- state mutation surface를 다시 감리한 결과, `estimates`만 add/update/delete/rename/hydrate/refresh 경로에서 mutable array reference를 직접 공유하고 있었고, 나머지 host local state(`isLoadingEstimate`, `currentDatabaseEstimateId`, `products`, `editingEstimateId`)는 getter/setter helper로 먼저 걷어내도 runtime contract를 크게 건드리지 않는 저위험 경계로 정리됐다.
- bootstrap ordering도 함께 재검토했지만, 남은 `DOMContentLoaded` 오케스트레이션 전체를 한 번에 shell helper로 옮기는 것보다 scalar/단방향 state를 먼저 축소하는 편이 더 얇고 검증 가능성이 높았다. 특히 `products`는 single-writer, `currentDatabaseEstimateId`/`isLoadingEstimate`/`editingEstimateId`는 scalar setter 경로라 stale closure보다 wiring drift만 조심하면 됐다.
- 따라서 다음 실행 순서는 (1) loading-state helper, (2) current-database-estimate-id helper, (3) products-state helper, (4) editing-estimate-id helper, (5) 마지막으로 `estimates` array policy + bootstrap shell 재감리 순으로 고정했다.

### 2.4.87 Loading/current-db/products state batch 결과
- `static/js/wdcalculator/loading-state.js`, `static/js/wdcalculator/current-database-estimate-id.js`, `static/js/wdcalculator/products-state.js`를 신설해 host local state 중 `isLoadingEstimate`, `currentDatabaseEstimateId`, `products`를 giant inline script 밖으로 분리했다.
- host giant script는 각 helper의 getter/setter alias를 직접 주입하는 thin wiring만 남기도록 정리했고, `load-estimate-to-input-form`/`estimate-list-events`, `load-saved-estimate-to-form`/`save-estimate`, `base-components`/`current-estimate`/`product-catalog`/`url-bootstrap` consumer를 새 helper 경로 기준으로 재배선했다.
- 이 과정에서 `products` helper alias가 첫 consumer보다 뒤에 선언되어 TDZ 위험이 생기는 ordering regression을 render contract가 즉시 잡아냈고, alias/configure 위치를 앞으로 당겨 같은 batch 안에서 수정했다.
- 신규 Node regression(`loading-state`, `current-database-estimate-id`, `products-state`)과 인접 consumer-focused pytest를 묶어 최종 `17 passed`, `18 passed`, `21 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.88 Editing-estimate-id batch 결과
- `static/js/wdcalculator/editing-estimate-id.js`를 신설해 host local `editingEstimateId` scalar를 giant inline script 밖으로 분리했다.
- host giant script에서는 `WdCalculatorEditingEstimateId.configure({ initialValue: null })` 후 `getEditingEstimateId`/`setEditingEstimateId`를 `current-estimate-orchestration`, `total-estimates-display`, `reset-input-form-keep-customer`, `load-estimate-to-input-form`, `add-estimate`, `estimate-list-events`에 직접 주입하는 구조로 바꿨다.
- 신규 Node regression과 edit-mode consumer 회귀(`current-estimate`, `calculate-total-estimates`, reset/load/add/list-events, render contract`)를 함께 돌려 최종 focused pytest `24 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.

### 2.4.89 Post-scalar-state next preaudit 메모
- scalar/단방향 host state를 먼저 줄인 뒤 남은 실제 고위험 결합점은 `estimates` mutable array reference와 `DOMContentLoaded` bootstrap ordering shell 두 축으로 좁혀졌다.
- 다음 단계는 `estimates`를 (a) stable-reference mutable store로 유지할지, (b) immutable replacement + consumer refetch contract로 바꿀지 먼저 결정하는 preaudit이다. 특히 `add-estimate.js`, `estimate-list-events.js` inline rename/delete, `load-saved-estimate-to-form.js`, `refresh-after-save.js`가 같은 배열을 서로 다른 방식으로 다루고 있어 이 정책을 먼저 고정해야 한다.
- 그 다음에야 residual bootstrap ordering(`initStartupInteractions()` → `initNotesUi()` → `loadInitialProducts()` → `initSidebarBootstrap()` → `initUrlBootstrap()` → `renderInitialBaseComponentsUi()`)을 별도 shell helper로 옮길지, `estimates` state helper와 같이 묶을지 안전하게 선택할 수 있다.

### 2.4.90 Estimates-state batch 결과
- `static/js/wdcalculator/estimates-state.js`를 신설해 마지막으로 남아 있던 host local mutable array `estimates`를 giant inline script 밖으로 분리했다.
- helper는 immutable replacement가 아니라 stable-reference store로 설계해 `getEstimates()`가 같은 live array를 계속 돌려주고, `setEstimates(...)`는 내부 배열 내용을 교체하는 방식으로 add/update/rename/delete/hydrate/refresh의 기존 mutation semantics를 유지했다.
- host giant script에서는 raw `let estimates = []`를 제거하고 `getEstimates` / `getEstimatesLength` / `setEstimates`를 `unsaved-exit-guard`, `current-estimate-orchestration`, `coupon-shipping-wiring`, `render-estimates-list`, `total-estimates-display`, `reset-input-form-keep-customer`, `load-estimate-to-input-form`, `load-saved-estimate-to-form`, `add-estimate`, `estimate-list-events`, `save-estimate`, `refresh-after-save`에 직접 주입하는 구조로 정리했다.
- 신규 Node regression `tests/test_wdcalculator_estimates_state_contract_node.py`는 stable reference, configure 초기값, non-array clear semantics를 고정했고, consumer-focused regressions를 함께 묶어 최종 focused pytest `30 passed`, `APP_OK`, 신규 lint 없음으로 batch를 닫았다.
- 같은 배치에서 실제로 더 이상 사용되지 않던 dead local `additionalOptions` 선언도 제거해 host mutable registry를 완전히 비웠다.

### 2.4.91 Early-bootstrap shell batch 결과
- cross-audit 결과 다음으로 가장 얇은 bootstrap 경계는 host 초반의 `WdCalculatorUnsavedExitGuard` + `WdCalculatorLayoutSyncWiring` configure/init 4문장이었고, 이를 `static/js/wdcalculator/early-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `getEstimates`, `windowRef`, `requestLayoutSync`, 그리고 두 bootstrap namespace를 주입받아 exact call order(unsaved configure → unsaved init → layout configure → layout init)만 수행하도록 제한했다.
- host giant script에서는 direct `WdCalculatorUnsavedExitGuard.configure/init...`와 `WdCalculatorLayoutSyncWiring.configure/init...`를 제거하고 `WdCalculatorEarlyBootstrap.configure(...)` + `initEarlyBootstrap()`만 남겨 early shell을 더 얇게 만들었다.
- 신규 Node regression `tests/test_wdcalculator_early_bootstrap_contract_node.py`와 render contract 보강으로 early shell ordering을 고정했고, 최종 focused pytest `23 passed`, `APP_OK`, 신규 lint 없음이었다.

### 2.4.92 Late-bootstrap shell batch 결과
- cross-audit 결과 host 후반의 가장 얇은 residual ordering 경계는 `sidebar bootstrap → returned API capture → refresh-after-save configure → url-bootstrap configure/init` 순서였고, 이를 `static/js/wdcalculator/late-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `WdCalculatorSidebarBootstrap`, `WdCalculatorRefreshAfterSave`, `WdCalculatorUrlBootstrap` namespace와 `initSidebarEstimates`, `loadEstimateToForm`, `formatNumber`, `setEstimates`, `resetInputFormKeepCustomerName`, `renderEstimatesList`, `getProducts`를 주입받아 exact call order만 수행하도록 제한했다.
- host giant script에서는 direct `WdCalculatorSidebarBootstrap.configure/initSidebarBootstrap`, `const loadSidebarEstimates = ...`, `WdCalculatorRefreshAfterSave.configure`, `WdCalculatorUrlBootstrap.configure/initUrlBootstrap`를 제거하고 `WdCalculatorLateBootstrap.configure(...)` + `initLateBootstrap()`만 남겨 late-phase sequencing을 host 밖으로 더 줄였다.
- 신규 Node regression `tests/test_wdcalculator_late_bootstrap_contract_node.py`와 render contract 보강으로 sidebar API pass-through와 refresh/url bootstrap ordering을 고정했고, 최종 focused pytest `24 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.93 Estimate-mutation bridge shell batch 결과
- late bootstrap 이후 host에 남은 가장 큰 contiguous bridge slab은 `WdCalculatorResetInputFormKeepCustomer`, `WdCalculatorLoadEstimateToInputForm`, `WdCalculatorLoadSavedEstimateToForm`, `WdCalculatorAddEstimate`, `WdCalculatorEstimateListEvents`, `WdCalculatorSaveEstimate` configure/init 구간이었고, 이를 `static/js/wdcalculator/estimate-mutation-bridge.js` thin shell로 분리했다.
- 새 helper는 여섯 module namespace와 `loadSavedEstimateToForm` / `resetInputFormKeepCustomerName` / `refreshAfterSave` alias, 그리고 state/helper/document/fetch bindings를 주입받아 exact configure/init order만 수행하도록 제한했다.
- host giant script에서는 direct `configure(...)`/`init...()` 나열을 제거하고 `WdCalculatorEstimateMutationBridge.configure(...)` + `initEstimateMutationBridge()`만 남겨 중반 mutation/bootstrap boilerplate를 크게 줄였다.
- 신규 Node regression `tests/test_wdcalculator_estimate_mutation_bridge_contract_node.py`와 render contract 보강으로 reset/load/add/list/save bridge ordering을 고정했고, 최종 focused pytest `23 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.94 Post-estimate-mutation-bridge next preaudit 메모
- mutation bridge 이후 남은 host head 구간에서 가장 얇은 residual shell 후보는 `WdCalculatorEstimatesState.configure({ initialEstimates: [] })` 뒤에 이어지는 `WdCalculatorEarlyBootstrap.configure/init` 묶음이다.
- 이 구간은 `getEstimates` alias와 `requestWdCalculatorLayoutSync` global만 안정적으로 유지하면 되고, mutation/save/sidebar alias처럼 바깥 closure trap이 거의 없어 다음 structure-only preaudit 후보로 안전하다.
- 따라서 다음 단계는 `estimates-state seed + early-bootstrap host shell` 경계를 먼저 전감리하고, state seed configure와 early bootstrap configure/init을 하나의 더 얇은 host shell로 합칠 수 있는지 contract-first로 확정하는 것이다.

### 2.4.95 Estimates-early bootstrap shell batch 결과
- estimate-mutation bridge 이후 host head에서 남아 있던 `WdCalculatorEstimatesState.configure({ initialEstimates: [] })` + `WdCalculatorEarlyBootstrap.configure/init` 구간을 `static/js/wdcalculator/estimates-early-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `WdCalculatorEstimatesState`, `WdCalculatorEarlyBootstrap`, `WdCalculatorUnsavedExitGuard`, `WdCalculatorLayoutSyncWiring`, `initialEstimates`, `getEstimates`, `windowRef`, `requestLayoutSync`만 주입받아 exact order(state seed → early bootstrap configure → early bootstrap init)만 수행하도록 제한했다.
- host giant script에서는 direct `WdCalculatorEstimatesState.configure(...)`, `WdCalculatorEarlyBootstrap.configure(...)`, `WdCalculatorEarlyBootstrap.initEarlyBootstrap()`를 제거하고 `WdCalculatorEstimatesEarlyBootstrap.configure(...)` + `initEstimatesEarlyBootstrap()`만 남겨 head ordering boilerplate를 더 줄였다.
- 신규 Node regression `tests/test_wdcalculator_estimates_early_bootstrap_contract_node.py`와 render contract 보강으로 estimates seed + early bootstrap ordering을 고정했고, 최종 focused pytest `24 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.96 Products/editing bootstrap batch 결과
- estimates-early bootstrap 이후 다음으로 가장 얇은 host head seed pair는 `WdCalculatorProductsState.configure({ initialProducts: [] })` + `WdCalculatorEditingEstimateId.configure({ initialValue: null })`였고, 이를 `static/js/wdcalculator/products-editing-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `WdCalculatorProductsState`, `WdCalculatorEditingEstimateId`, `initialProducts`, `initialEditingEstimateId`만 주입받아 exact order(products seed → editing-id seed)만 수행하도록 제한했다.
- host giant script에서는 direct products/editing state configure pair를 제거하고 `WdCalculatorProductsEditingBootstrap.configure(...)` + `initProductsEditingBootstrap()`만 남겨 products/editing seed boilerplate를 head bootstrap shell로 옮겼다.
- 신규 Node regression `tests/test_wdcalculator_products_editing_bootstrap_contract_node.py`와 render contract 보강으로 products/editing seed ordering을 고정했고, 최종 focused pytest `27 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.97 Post-products-editing next preaudit 메모
- products/editing shell 이후 남은 가장 얇은 state seed pair는 `WdCalculatorLoadingState.configure({ initialValue: false })` + `WdCalculatorCurrentDatabaseEstimateId.configure({ initialValue: null })`다.
- 이 구간은 `getLoadingState` / `setLoadingState` / `getCurrentDatabaseEstimateId` / `setCurrentDatabaseEstimateId` alias를 host에 그대로 둔 채 direct configure pair만 shell로 옮기면 되고, mutation bridge consumer보다 앞선 초기화 순서만 유지하면 된다.
- 따라서 다음 단계는 `loading/database` host seed shell 경계를 contract-first로 닫고, 두 state module seed configure를 별도 thin shell helper로 이동하는 것이다.

### 2.4.98 Loading-database bootstrap batch 결과
- 남은 state seed pair였던 `WdCalculatorLoadingState.configure({ initialValue: false })` + `WdCalculatorCurrentDatabaseEstimateId.configure({ initialValue: null })`를 `static/js/wdcalculator/loading-database-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `WdCalculatorLoadingState`, `WdCalculatorCurrentDatabaseEstimateId`, `initialLoadingValue`, `initialCurrentDatabaseEstimateId`만 주입받아 exact order(loading seed → currentDatabaseEstimateId seed)만 수행하도록 제한했다.
- host giant script에서는 direct configure pair를 제거하고 `WdCalculatorLoadingDatabaseBootstrap.configure(...)` + `initLoadingDatabaseBootstrap()`만 남겨 state seed boilerplate를 한 덩어리 더 밖으로 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_loading_database_bootstrap_contract_node.py`와 render contract 보강으로 loading/database seed ordering을 고정했고, 최종 focused pytest `23 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.99 Post-loading-database next preaudit 메모
- loading/database shell 이후 남은 가장 얇은 host-only configure/destructure slab은 `WdCalculatorBaseComponentsUI.configure`, `WdCalculatorCouponDisplayHelpers.configure`, `WdCalculatorAdditionalOptionsUI.configure`와 바로 뒤의 destructuring bridge(`getProductsOptionsHtml`, `getCouponValue`, `appendAdditionalOptionRow` 등)다.
- 이 구간은 direct `init*()` side effect 없이 pure wiring + symbol export bridge만 수행하고, `WdCalculatorCurrentEstimateOrchestration.configure(...)`보다 앞에서 필요한 helper refs를 준비하는 phase라 다음 structure-only shell 후보로 가장 안전하다.
- 핵심 trap은 `getCalculateEstimate: () => calculateEstimate` lazy ref를 그대로 유지해야 한다는 점, `DEFAULT_COUPON_VALUE` / `wdCalculatorCategories` host scope를 보존해야 한다는 점, 그리고 downstream host가 기대하는 destructured binding names를 변형 없이 넘겨야 한다는 점이다.
- 따라서 다음 단계는 이 primary UI triad를 별도 thin shell helper(예: `primary-ui-bootstrap.js`)로 묶고, configure/destructure bridge의 exact order를 contract-first로 고정하는 것이다.

### 2.4.100 Primary-ui bootstrap batch 결과
- `WdCalculatorBaseComponentsUI.configure`, `WdCalculatorCouponDisplayHelpers.configure`, `WdCalculatorAdditionalOptionsUI.configure`와 바로 뒤 destructuring bridge를 `static/js/wdcalculator/primary-ui-bootstrap.js` thin shell로 분리했다.
- 새 helper는 세 UI namespace와 `getProducts`, `getCalculateEstimate`, `defaultCouponValue`, `getCategories`만 주입받아 exact configure order(base → coupon → additional)를 수행한 뒤, host가 그대로 쓰는 helper refs(`getProductsOptionsHtml`, `getCouponValue`, `appendAdditionalOptionRow` 등)를 flat object로 반환하도록 제한했다.
- host giant script에서는 direct configure 호출과 module별 destructuring을 제거하고 `WdCalculatorPrimaryUiBootstrap.configure(...)` + `initPrimaryUiBootstrap()`만 남겨 primary UI wiring boilerplate를 한 덩어리 더 밖으로 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_primary_ui_bootstrap_contract_node.py`와 render contract 보강으로 primary UI configure ordering과 returned API shape를 고정했고, 최종 focused pytest `25 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.101 Post-primary-ui next preaudit 메모
- primary-ui shell 이후 남은 가장 얇은 direct configure trio는 `WdCalculatorAddOptionButton.configure`, `WdCalculatorCalculateButton.configure`, `WdCalculatorProductCatalogUI.configure`다.
- 이 구간은 primary UI shell이 반환한 `appendAdditionalOptionRow` / `ensureBaseComponentsUI` / `updateBaseProductSelectOptions`와 orchestration의 `calculateEstimate`를 host에서 얇게 연결하는 pure wiring phase라, coupon/search/render/totals/startup cluster보다 구조-only shell로 분리하기 안전하다.
- 핵심 trap은 `getCalculateEstimate: () => calculateEstimate` lazy ref를 유지해야 한다는 점, `documentRef: document`를 explicit하게 보존해야 한다는 점, 그리고 `WdCalculatorStartupInit.configure(...)`가 사용하는 `bindProductSelect`보다 먼저 `WdCalculatorProductCatalogUI.configure(...)`가 끝나야 한다는 점이다.
- 따라서 다음 단계는 이 contiguous trio를 별도 thin shell helper(예: `catalog-buttons-bootstrap.js`)로 묶고, catalog/button wiring의 exact order를 contract-first로 고정하는 것이다.

### 2.4.102 Catalog-buttons bootstrap batch 결과
- `WdCalculatorAddOptionButton.configure`, `WdCalculatorCalculateButton.configure`, `WdCalculatorProductCatalogUI.configure` contiguous trio를 `static/js/wdcalculator/catalog-buttons-bootstrap.js` thin shell로 분리했다.
- 새 helper는 세 module namespace와 `documentRef`, `appendAdditionalOptionRow`, `calculateEstimate`, `getProducts`, `setProducts`, `getCalculateEstimate`, `updateBaseProductSelectOptions`, `ensureBaseComponentsUI`만 주입받아 exact configure order(add-option → calculate-button → product-catalog)를 수행하도록 제한했다.
- host giant script에서는 direct configure 호출을 제거하고 `WdCalculatorCatalogButtonsBootstrap.configure(...)` + `initCatalogButtonsBootstrap()`만 남겨 catalog/button wiring boilerplate를 giant inline script 밖으로 한 덩어리 더 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_catalog_buttons_bootstrap_contract_node.py`와 render contract 보강으로 configure ordering과 lazy `getCalculateEstimate` bridge를 고정했고, 최종 focused pytest `27 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.103 Post-catalog-buttons next preaudit 메모
- catalog-buttons shell 이후 남은 가장 얇은 pure host-only configure slab은 `WdCalculatorCouponShippingWiring.configure`, `WdCalculatorSearchResultsLoad.configure`, `WdCalculatorRenderEstimatesList.configure` contiguous trio다.
- 이 구간은 side effect 없는 configure phase이며, `DEFAULT_COUPON_VALUE`, `loadSavedEstimateToForm`, `WdCalculatorNotesUI.formatNotesText`, `calculateTotalEstimates` 같은 기존 host refs를 세 module에 얇게 주입하는 역할만 수행해 structure-only shell로 분리하기 안전하다.
- 핵심 trap은 `calculateTotalEstimates` ref가 `WdCalculatorTotalEstimatesDisplay.configure(...)` 전에 전달되더라도 실제 호출은 그 이후 순서를 유지해야 한다는 점, 그리고 `loadEstimateToForm: loadSavedEstimateToForm` alias/`escapeHtml`/`formatNotesText` host scope를 그대로 보존해야 한다는 점이다.
- 따라서 다음 단계는 이 configure trio를 별도 thin shell helper(예: `coupon-search-render-bootstrap.js`)로 묶고, post-catalog configure ordering을 contract-first로 고정하는 것이다.

### 2.4.104 Coupon-search-render bootstrap batch 결과
- `WdCalculatorCouponShippingWiring.configure`, `WdCalculatorSearchResultsLoad.configure`, `WdCalculatorRenderEstimatesList.configure` contiguous trio를 `static/js/wdcalculator/coupon-search-render-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `couponShippingWiring`, `searchResultsLoad`, `renderEstimatesList` namespace와 `defaultCouponValue`, `getEstimates`, `calculateEstimate`, `calculateTotalEstimates`, `getCouponValue`, `loadEstimateToForm`, `formatNumber`, `escapeHtml`, `formatNotesText`, `onRenderComplete`만 주입받아 exact configure order(coupon-shipping → search-results → render-list)를 수행하도록 제한했다.
- host giant script에서는 direct configure 호출을 제거하고 `WdCalculatorCouponSearchRenderBootstrap.configure(...)` + `initCouponSearchRenderBootstrap()`만 남겨 post-catalog configure boilerplate를 giant inline script 밖으로 더 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_coupon_search_render_bootstrap_contract_node.py`와 render contract 보강으로 configure ordering과 alias/global bridge를 고정했고, 최종 focused pytest `27 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.105 Post-coupon-search-render next preaudit 메모
- coupon-search-render shell 이후 다음 구조-only 후보는 tail phase의 `WdCalculatorLateBootstrap.configure(...)` + `WdCalculatorLateBootstrap.initLateBootstrap()` + `renderInitialBaseComponentsUi()` contiguous 구간이다.
- 이 구간은 이미 추출된 `late-bootstrap.js`, `estimate-mutation-bridge.js`, `terminal-init.js` 위에 얇게 놓인 host orchestration tail이라, middle-phase configure 흐름보다 fan-in이 적고 구조-only shell로 감싸기 가장 안전하다.
- 핵심 trap은 `EstimateMutationBridge.init...` 뒤에서만 late bootstrap이 실행되어야 한다는 점, `window.initWdCalculatorSidebarEstimates` global ref를 그대로 전달해야 한다는 점, 그리고 `loadInitialProducts()` 대비 `renderInitialBaseComponentsUi()`의 현재 상대 순서를 보존해야 한다는 점이다.
- 따라서 다음 단계는 이 tail phase를 별도 thin shell helper(예: `post-mutation-ui-bootstrap.js`)로 묶고, late/bootstrap/render tail ordering을 contract-first로 고정하는 것이다.

### 2.4.106 Post-mutation-ui bootstrap batch 결과
- `WdCalculatorLateBootstrap.configure`, `WdCalculatorLateBootstrap.initLateBootstrap`, `renderInitialBaseComponentsUi()` contiguous tail orchestration을 `static/js/wdcalculator/post-mutation-ui-bootstrap.js` thin shell로 분리했다.
- 새 helper는 `lateBootstrap`, `sidebarBootstrap`, `refreshAfterSave`, `urlBootstrap`, `initSidebarEstimates`, `loadEstimateToForm`, `formatNumber`, `setEstimates`, `resetInputFormKeepCustomerName`, `renderEstimatesList`, `getProducts`, `documentRef`, `consoleRef`, `setTimeoutImpl`, `renderInitialBaseComponentsUi`만 주입받아 exact ordering(late-bootstrap configure → late-bootstrap init → initial base UI render)을 수행하도록 제한했다.
- host giant script에서는 direct late-bootstrap/render 호출을 제거하고 `WdCalculatorPostMutationUiBootstrap.configure(...)` + `initPostMutationUiBootstrap()`만 남겨 post-mutation tail boilerplate를 giant inline script 밖으로 한 덩어리 더 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_post_mutation_ui_bootstrap_contract_node.py`와 render contract 보강으로 late/bootstrap/render ordering과 global alias bridge를 고정했고, 최종 focused pytest `36 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.107 Post-post-mutation-ui next preaudit 메모
- post-mutation UI shell 이후 남은 가장 얇은 pure host-only configure slab은 `WdCalculatorTotalEstimatesDisplay.configure`, `WdCalculatorStartupInit.configure`, `WdCalculatorTerminalInit.configure`, `initStartupInteractions()` contiguous block이다.
- 이 구간은 하나의 call site에서 그대로 `configure + init` shell로 감쌀 수 있고, 필요한 값도 모두 상단에서 이미 정의돼 있어 symbol churn 없이 structure-only extraction을 진행하기 좋다.
- 핵심 trap은 `WdCalculatorCouponSearchRenderBootstrap.init...` 뒤에 `WdCalculatorTotalEstimatesDisplay.configure(...)`가 유지돼야 한다는 점, `initStartupInteractions()`가 계속 `WdCalculatorNotesUI.initNotesUi()` 및 `loadInitialProducts()`보다 먼저 실행돼야 한다는 점, `WdCalculatorTerminalInit.configure(...)`가 `loadInitialProducts()`보다 먼저 유지돼야 한다는 점이다.
- 따라서 다음 단계는 이 contiguous block을 별도 thin shell helper(예: `totals-startup-terminal-bootstrap.js`)로 묶고, coupon/bootstrap/mutation 사이 startup/terminal ordering을 contract-first로 고정하는 것이다.

### 2.4.108 Totals-startup-terminal bootstrap batch 결과
- `WdCalculatorTotalEstimatesDisplay.configure`, `WdCalculatorStartupInit.configure`, `WdCalculatorTerminalInit.configure`, `initStartupInteractions()` contiguous block을 `static/js/wdcalculator/totals-startup-terminal-bootstrap.js` thin shell로 분리했다.
- host giant script에서는 direct total/startup/terminal configure 호출을 제거하고 `WdCalculatorTotalsStartupTerminalBootstrap.configure(...)` + `initTotalsStartupTerminalBootstrap()`만 남겨 coupon-search-render 이후 startup/terminal glue를 giant inline script 밖으로 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_totals_startup_terminal_bootstrap_contract_node.py`와 render contract 보강으로 configure payload/order + startup init 순서를 고정했고, 최종 focused pytest `28 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.109 Notes-ui bootstrap batch 결과
- host의 direct `WdCalculatorNotesUI.initNotesUi()` leaf call을 `static/js/wdcalculator/notes-ui-bootstrap.js` thin shell로 감쌌다.
- giant script에서는 direct notes init을 제거하고 `WdCalculatorNotesUiBootstrap.configure(...)` + `initNotesUiBootstrap()`만 남겨 startup/terminal bootstrap 다음의 notes leaf bootstrap도 host 밖으로 밀어냈다.
- 신규 Node regression `tests/test_wdcalculator_notes_ui_bootstrap_contract_node.py`와 render contract 보강으로 direct notes init call-through를 고정했고, 최종 focused pytest `30 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.110 Loading-database host bootstrap batch 결과
- host의 direct `WdCalculatorLoadingDatabaseBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/loading-database-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `loading-database-bootstrap.js` seed helper에 동일한 `loadingState`, `currentDatabaseEstimateIdState`, `initialLoadingValue`, `initialCurrentDatabaseEstimateId` payload를 forward하고 `initLoadingDatabaseBootstrap()` return value도 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_loading_database_host_bootstrap_contract_node.py`를 추가해 `coupon-search-render` 뒤/`totals-startup-terminal` 앞 host ordering을 고정했고, 최종 focused pytest `30 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.111 Products-editing host bootstrap batch 결과
- host의 direct `WdCalculatorProductsEditingBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/products-editing-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `products-editing-bootstrap.js` seed helper에 동일한 `productsState`, `editingEstimateIdState`, `initialProducts`, `initialEditingEstimateId` payload를 forward하고 `initProductsEditingBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_products_editing_host_bootstrap_contract_node.py`를 추가해 primary UI bootstrap 앞의 exact host ordering을 고정했고, 최종 focused pytest `33 passed`, 기존 Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.112 Estimates-early host bootstrap batch 결과
- host head의 direct `WdCalculatorEstimatesEarlyBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/estimates-early-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `estimates-early-bootstrap.js` helper에 동일한 `estimatesState`, `earlyBootstrap`, `unsavedExitGuard`, `layoutSyncWiring`, `initialEstimates`, `getEstimates`, `windowRef`, `requestLayoutSync` payload를 forward하고 `initEstimatesEarlyBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_estimates_early_host_bootstrap_contract_node.py`를 추가해 estimates alias 뒤/`current-estimate-orchestration` 앞 host ordering을 고정했고, 최종 focused pytest `35 passed`, 기존 Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.113 Post-estimates-early-host next preaudit 메모
- estimates-early host shell 이후 남은 가장 얇은 pure host-only configure slab은 `WdCalculatorEstimateMutationBridge.init...` 직후의 direct `WdCalculatorPostMutationUiBootstrap.configure/init` pair이다.
- 이 구간은 이미 `post-mutation-ui-bootstrap.js` 자체가 안정적으로 고정돼 있으므로, next step은 기존 helper를 다시 감싸는 `post-mutation-ui-host-bootstrap.js` thin host shell을 추가해 tail host glue만 옮기면 된다.
- 핵심 trap은 `EstimateMutationBridge.initEstimateMutationBridge()`가 계속 먼저 실행돼야 한다는 점, `window.initWdCalculatorSidebarEstimates` global ref를 그대로 전달해야 한다는 점, 그리고 `renderInitialBaseComponentsUi`/`setTimeout`/`document`/`console` binding을 그대로 유지해야 한다는 점이다.
- 따라서 다음 단계는 post-mutation tail의 direct configure/init pair를 별도 host shell helper로 감싸 late tail host glue를 한 단계 더 얇게 만드는 것이다.

### 2.4.114 Post-mutation-ui host bootstrap batch 결과
- host의 direct `WdCalculatorPostMutationUiBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/post-mutation-ui-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `post-mutation-ui-bootstrap.js` helper에 동일한 `lateBootstrap`, `sidebarBootstrap`, `refreshAfterSave`, `urlBootstrap`, `initSidebarEstimates`, `loadEstimateToForm`, `formatNumber`, `setEstimates`, `resetInputFormKeepCustomerName`, `renderEstimatesList`, `getProducts`, `documentRef`, `consoleRef`, `setTimeoutImpl`, `renderInitialBaseComponentsUi` payload를 forward하고 `initPostMutationUiBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_post_mutation_ui_host_bootstrap_contract_node.py`를 추가해 mutation bridge 뒤 exact late tail host ordering을 고정했고, 최종 focused pytest `28 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.115 Notes-ui host bootstrap batch 결과
- host의 direct `WdCalculatorNotesUiBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/notes-ui-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `notes-ui-bootstrap.js` helper에 동일한 `notesUi` payload를 forward하고 `initNotesUiBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_notes_ui_host_bootstrap_contract_node.py`를 추가해 totals-startup-terminal 뒤/loadInitialProducts 앞 exact notes host ordering을 고정했고, 최종 focused pytest `30 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.116 Catalog-buttons host bootstrap batch 결과
- host의 direct `WdCalculatorCatalogButtonsBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/catalog-buttons-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `catalog-buttons-bootstrap.js` helper에 동일한 `addOptionButton`, `calculateButton`, `productCatalogUi`, `documentRef`, `appendAdditionalOptionRow`, `calculateEstimate`, `getProducts`, `setProducts`, `getCalculateEstimate`, `updateBaseProductSelectOptions`, `ensureBaseComponentsUI` payload를 forward하고 `initCatalogButtonsBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_catalog_buttons_host_bootstrap_contract_node.py`를 추가해 current-estimate-orchestration 뒤/coupon-search-render 앞 exact catalog host ordering을 고정했고, 최종 focused pytest `32 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.117 Post-catalog-buttons-host next preaudit 메모
- catalog-buttons host shell 이후 남은 가장 얇은 pure host-only configure slab은 direct `WdCalculatorCouponSearchRenderBootstrap.configure/init` pair이다.
- 이 구간은 `coupon-search-render-bootstrap.js`가 이미 안정적으로 고정돼 있고 `initCouponSearchRenderBootstrap()` return value를 host가 소비하지 않으므로, next step은 기존 helper를 다시 감싸는 `coupon-search-render-host-bootstrap.js` thin host shell을 추가해 mid-tail render wiring host glue만 옮기면 된다.
- 핵심 trap은 `loadEstimateToForm: loadSavedEstimateToForm`, `onRenderComplete: calculateTotalEstimates`, `formatNotesText: WdCalculatorNotesUI.formatNotesText` binding을 그대로 전달해야 한다는 점, 그리고 new host shell이 계속 `catalog-buttons-host-bootstrap` 뒤/`totals-startup-terminal-bootstrap` 앞 순서를 유지해야 한다는 점이다.
- 반대로 `WdCalculatorPrimaryUiBootstrap`은 init return destructuring을 host가 바로 소비하므로 지금 시점의 structure-only 다음 후보로는 더 무겁다.

### 2.4.118 Coupon-search-render host bootstrap batch 결과
- host의 direct `WdCalculatorCouponSearchRenderBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/coupon-search-render-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `coupon-search-render-bootstrap.js` helper에 동일한 `couponShippingWiring`, `searchResultsLoad`, `renderEstimatesList`, `defaultCouponValue`, `getEstimates`, `calculateEstimate`, `calculateTotalEstimates`, `getCouponValue`, `loadEstimateToForm`, `formatNumber`, `escapeHtml`, `formatNotesText`, `onRenderComplete` payload를 forward하고 `initCouponSearchRenderBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_coupon_search_render_host_bootstrap_contract_node.py`를 추가해 catalog-buttons host 뒤/totals-startup-terminal 앞 exact coupon/search/render host ordering을 고정했고, 최종 focused pytest `28 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.119 Totals-startup-terminal host bootstrap batch 결과
- host의 direct `WdCalculatorTotalsStartupTerminalBootstrap.configure/init` invocation pair를 `static/js/wdcalculator/totals-startup-terminal-host-bootstrap.js` thin host shell로 감쌌다.
- 새 helper는 기존 `totals-startup-terminal-bootstrap.js` helper에 동일한 `totalEstimatesDisplay`, `startupInit`, `terminalInit`, `getEstimates`, `getEditingEstimateId`, `getCouponValue`, `resolveAggregateTotals`, `collectNotes`, `formatNumber`, `applyFinalPriceStyle`, `applyCouponDiscountStyle`, `documentRef`, `alertImpl`, `consoleRef`, `categories`, `bindProductSelect`, `initBaseComponentsLiveInteractions`, `initAddOptionButton`, `initCalculateButton`, `initSearchResultsLoadBridge`, `bindOrderMatchButtons`, `initCouponShippingWiring`, `loadProducts`, `ensureBaseComponentsUI` payload를 forward하고 `initTotalsStartupTerminalBootstrap()` result를 그대로 pass-through하도록 제한했다.
- render contract와 신규 Node regression `tests/test_wdcalculator_totals_startup_terminal_host_bootstrap_contract_node.py`를 추가해 coupon-search-render host 뒤/notes-ui host 앞 exact totals/startup/terminal host ordering을 고정했고, 최종 focused pytest `30 passed`, `APP_OK`, Jinja false-positive 외 신규 lint 없음으로 batch를 닫았다.

### 2.4.120 Post-totals-startup-terminal-host next preaudit 메모
- totals/startup/terminal host shell 이후 남은 가장 얇은 pure host-only configure slab은 direct `WdCalculatorEstimateMutationBridge.configure/init` pair이다.
- 이 구간은 `estimate-mutation-bridge.js`가 이미 안정적으로 고정돼 있고 `initEstimateMutationBridge()` return value를 host가 소비하지 않으므로, next step은 기존 helper를 다시 감싸는 `estimate-mutation-bridge-host-bootstrap.js` thin host shell을 추가해 `loadInitialProducts()` 뒤/post-mutation host 앞 mutation slab host glue만 옮기면 된다.
- 핵심 trap은 `loadInitialProducts()` 호출이 계속 먼저 유지돼야 한다는 점, add/list/save/reset/load input/load saved 모든 module option bag을 그대로 전달해야 한다는 점, 그리고 new host shell이 계속 `WdCalculatorNotesUiHostBootstrap.initNotesUiHostBootstrap()` 뒤 / `WdCalculatorPostMutationUiHostBootstrap.configure(...)` 앞 순서를 유지해야 한다는 점이다.

### 2.4.121 2026-04-13 chunking rebaseline note
- 최종 목표는 유지하되, 사용자 지침에 따라 WDCalculator 구조 작업은 더 이상 thin host shell 1-file micro batch 중심으로 이어가지 않는다.
- direct `WdCalculatorEstimateMutationBridge.configure/init` host wrapper 추가는 현재 시점에서 유지보수 이득보다 파일/테스트/인지부하 증가가 더 커 보여 우선 보류한다.
- 다음 세션 first action은 `wdcalculator_scripts.html` + `static/js/wdcalculator/` 기준으로 남은 작업을 3~5개의 의미 있는 유지보수 chunk로 재편하는 것이다.
- 이후 batch gate는 "ownership 명확화", "file count control", "behavior-neutral structure gain" 중 최소 1개를 만족해야 한다.

## 3. Historical step archive (completed micro-batch record)
- 아래 Step 1~109는 이미 수행된 micro batch 이력이다. 앞으로의 실행 지침이 아니라 current debt inventory로 읽는다.
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
- [x] Step 19: product-catalog 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 order matching UI로 확정한다.
- [x] Step 20: order matching UI(`.match-order-btn`, `showOrderSelectionModal`, `matchEstimateToOrder`) contract를 focused tests로 freeze한다.
- [x] Step 21: order matching UI를 static JS module로 분리하고 host script에는 search-result bridge와 bootstrap wiring만 남긴다.
- [x] Step 22: order-match 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 coupon/shipping listener wiring으로 확정한다.
- [x] Step 23: coupon/shipping global input listener의 DOM/event/recalc wiring contract를 focused tests로 freeze한다.
- [x] Step 24: coupon/shipping recalculation listener wiring을 static JS module로 분리하고 host script에는 thin bootstrap만 남긴다.
- [x] Step 25: coupon/shipping 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 search results + load-to-form bridge로 확정한다.
- [x] Step 26: search results + load-to-form bridge의 API/DOM/runtime contract를 focused tests로 freeze한다.
- [x] Step 27: search results + load-to-form bridge를 static JS module로 분리하고 host giant script에는 thin bootstrap만 남긴다.
- [x] Step 28: search/load 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 in-session estimates list view(`renderEstimatesList` + summary card + post-render style pass)로 확정한다.
- [x] Step 29: renderEstimatesList view의 DOM/selectors/render completion contract를 focused tests로 freeze한다.
- [x] Step 30: in-session estimates list view를 static JS module로 분리하고 host giant script에는 thin orchestration만 남긴다.
- [x] Step 31: render list 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 `baseComponentsContainer` live interactions로 확정한다.
- [x] Step 32: baseComponentsContainer live interactions의 DOM/selectors/recalc wiring contract를 focused tests로 freeze한다.
- [x] Step 33: baseComponentsContainer live interactions를 existing `base-components-ui.js` module로 흡수하고 host giant script에는 thin bootstrap만 남긴다.
- [x] Step 34: base live interactions 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 URL/deep-link bootstrap으로 확정한다.
- [x] Step 35: URL/deep-link bootstrap의 DOM/URL/async retry contract를 focused tests로 freeze한다.
- [x] Step 36: URL/deep-link bootstrap을 static JS module로 분리하고 host giant script에는 thin bootstrap만 남긴다.
- [x] Step 37: URL bootstrap 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 `refreshAfterSave` post-save cluster로 확정한다.
- [x] Step 38: `refreshAfterSave` post-save refresh/highlight의 DOM/timer/sidebar contract를 focused tests로 freeze한다.
- [x] Step 39: `refreshAfterSave` post-save refresh/highlight를 static JS module로 분리하고 host giant script에는 thin orchestration만 남긴다.
- [x] Step 40: refresh-after-save 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 `resetInputFormKeepCustomerName` reset cluster로 확정한다.
- [x] Step 41: `resetInputFormKeepCustomerName` reset path의 DOM/notes/button/currentDatabaseEstimateId contract를 focused tests로 freeze한다.
- [x] Step 42: `resetInputFormKeepCustomerName` reset path를 static JS module로 분리하고 host giant script에는 thin orchestration만 남긴다.
- [x] Step 43: reset-input-form 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 `loadEstimateToInputForm` local edit-load cluster로 확정한다.
- [x] Step 44: `loadEstimateToInputForm` local edit-load path의 DOM/helper/loading-flag contract를 focused tests로 freeze한다.
- [x] Step 45: `loadEstimateToInputForm` local edit-load path를 static JS module로 분리하고 host giant script에는 thin orchestration만 남긴다.
- [x] Step 46: load-estimate-to-input-form 이후 남은 giant inline cluster를 재감리해 다음 structure-only 배치를 `loadEstimateToForm` saved-estimate hydrate cluster로 확정한다.
- [x] Step 47: inline `loadEstimateToForm(estimate)` saved-estimate hydrate contract를 focused tests로 freeze한다.
- [x] Step 48: `loadEstimateToForm(estimate)` saved-estimate hydrate path를 static JS module로 분리하고 host giant script에는 thin orchestration만 남긴다.
- [x] Step 49: saved-estimate hydrate 이후 남은 inline main mutation cluster를 재감리해 다음 structure-only 배치를 `saveEstimateBtn` save orchestration으로 확정한다.
- [x] Step 50: `saveEstimateBtn` clone/replace + save fetch orchestration contract를 focused tests로 freeze한다.
- [x] Step 51: `saveEstimateBtn` clone/replace + save fetch orchestration을 static JS module로 분리하고 host giant script에는 thin bootstrap만 남긴다.
- [x] Step 52: save-estimate 이후 남은 inline main mutation cluster를 재감리해 다음 structure-only 배치를 `addEstimateBtn` local add/update orchestration으로 확정한다.
- [x] Step 53: `addEstimateBtn` local add/update orchestration + follow-up save-button show listener contract를 focused tests로 freeze한다.
- [x] Step 54: `addEstimateBtn` local add/update orchestration + follow-up save-button show listener를 static JS module로 분리하고 host giant script에는 thin bootstrap만 남긴다.
- [x] Step 55: add-estimate 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `#estimatesListContainer` 이벤트 위임 클러스터로 확정한다.
- [x] Step 56: `#estimatesListContainer` 이벤트 위임(수정/이름편집/삭제/카드클릭)의 DOM/selector/runtime contract를 focused tests로 freeze한다.
- [x] Step 57: `#estimatesListContainer` 이벤트 위임 클러스터를 static JS module로 분리하고 host giant script에는 thin bootstrap만 남긴다.
- [x] Step 58: list-events 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `calculateTotalEstimates()` aggregate summary display cluster로 확정한다.
- [x] Step 59: `calculateTotalEstimates()` aggregate summary display의 DOM/selector/runtime contract를 focused tests로 freeze한다.
- [x] Step 60: `calculateTotalEstimates()` aggregate summary display cluster를 static JS module로 분리하고 host giant script에는 thin orchestration만 남긴다.
- [x] Step 61: total-estimates display 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 helper-load resolver pair로 확정한다.
- [x] Step 62: helper-load resolver pair의 pass-through signature와 helper 미로드 오류 문자열 contract를 focused tests로 freeze한다.
- [x] Step 63: `resolveWdcCurrentEstimateMath()` + `resolveWdcAggregateTotals()`를 `static/js/wdcalculator/calculation-resolvers.js`로 분리하고 host giant script에는 alias만 남긴다.
- [x] Step 64: calculation-resolvers 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `beforeunload` unsaved-exit guard로 확정한다.
- [x] Step 65: `beforeunload` unsaved-exit guard의 브라우저 side-effect contract를 focused tests로 freeze하고 helper batch를 완료한다.
- [x] Step 66: beforeunload 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `addOptionBtn` click wiring으로 확정한다.
- [x] Step 67: `addOptionBtn` click wiring의 DOM/lookup/call-shape contract를 focused tests로 freeze하고 helper batch를 완료한다.
- [x] Step 68: add-option 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `calculateBtn` click wiring으로 확정한다.
- [x] Step 69: `calculateBtn` click wiring의 null-guard/single-call contract를 focused tests로 freeze하고 helper batch를 완료한다.
- [x] Step 70: calculate-button 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 layout sync wiring으로 확정한다.
- [x] Step 71: layout sync wiring(`resize`/`load` → `requestWdCalculatorLayoutSync`)의 listener/immediate sync contract를 focused tests로 freeze하고 helper batch를 완료한다.
- [x] Step 72: layout-sync 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 sidebar bootstrap으로 확정한다.
- [x] Step 73: sidebar bootstrap의 init call shape와 returned API pass-through contract를 focused tests로 freeze하고 helper batch를 완료한다.
- [x] Step 74: sidebar-bootstrap 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `loadEstimateToForm` wrapper alias로 확정한다.
- [x] Step 75: `loadEstimateToForm` wrapper alias의 call-through + direct wiring contract를 focused tests로 freeze한다.
- [x] Step 76: inline `loadEstimateToForm` wrapper function을 제거하고 saved-estimate helper ref direct wiring으로 치환한다.
- [x] Step 77: wrapper-removal 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 startup init shell로 확정한다.
- [x] Step 78: early startup calls + empty-category warning shell을 `startup-init.js`로 분리하고 call order/warn contract를 focused tests로 freeze한다.
- [x] Step 79: startup-init 이후 남은 inline cluster를 재감리해 다음 structure-only 배치를 `loadProducts()` / `ensureBaseComponentsUI()` terminal init calls로 확정한다.
- [x] Step 80: `loadProducts()` / `ensureBaseComponentsUI()` terminal init shell을 분리하고 ordering/call-through contract를 focused tests로 freeze한다.
- [x] Step 81: terminal-init 이후 remaining inline cluster를 재감리해 다음 batch를 `calculateEstimate()` contract-first 분해로 확정한다.
- [x] Step 82: `calculateEstimate()` / `collectCurrentEstimate()` DOM-state orchestration을 helper로 분리하고 current-estimate contract + host direct wiring contract를 새 module 기준으로 재고정한다.
- [x] Step 83: current-estimate orchestration 이후 남은 host mutable state/bootstrap shell을 재감리해 다음 batch를 state-store/boot-order contract-first 후보로 확정한다.
- [x] Step 84: `isLoadingEstimate` / `currentDatabaseEstimateId` host scalar를 helper로 분리하고 consumer contract를 새 getter/setter 경로로 재고정한다.
- [x] Step 85: `products` 단일 source를 helper로 분리하고 base/current-estimate/product-catalog/url-bootstrap wiring contract를 새 helper 기준으로 재고정한다.
- [x] Step 86: `editingEstimateId` scalar를 helper로 분리하고 edit-mode/reset/load/add/list consumer contract를 새 helper 기준으로 재고정한다.
- [x] Step 87: 남은 `estimates` mutable array 정책을 stable-reference helper로 고정하고 consumer contract를 새 helper 기준으로 재고정한다.
- [x] Step 88: host 초반의 guard/layout configure+init 4문장을 `early-bootstrap.js` thin shell로 분리하고 exact ordering contract를 focused tests로 고정한다.
- [x] Step 89: residual late-phase bootstrap(`sidebar bootstrap → returned API capture → refresh/url configure/init`)을 `late-bootstrap.js` thin shell로 분리하고 exact ordering/render contract를 focused tests로 고정한다.
- [x] Step 90: reset/load/add/list/save contiguous wiring slab을 `estimate-mutation-bridge.js` thin shell로 분리하고 alias/order/render contract를 focused tests로 고정한다.
- [x] Step 91: `WdCalculatorEstimatesState.configure({ initialEstimates: [] })` + `WdCalculatorEarlyBootstrap.configure/init` host head 구간을 thin shell로 분리하고 render/order contract를 focused tests로 고정한다.
- [x] Step 92: `WdCalculatorProductsState.configure({ initialProducts: [] })` + `WdCalculatorEditingEstimateId.configure({ initialValue: null })` host seed pair를 thin shell로 분리하고 render/order contract를 focused tests로 고정한다.
- [x] Step 93: `WdCalculatorLoadingState.configure({ initialValue: false })` + `WdCalculatorCurrentDatabaseEstimateId.configure({ initialValue: null })` host seed pair를 thin shell로 분리하고 render/order contract를 focused tests로 고정한다.
- [x] Step 94: `WdCalculatorBaseComponentsUI.configure` + `WdCalculatorCouponDisplayHelpers.configure` + `WdCalculatorAdditionalOptionsUI.configure`와 바로 뒤 destructuring bridge를 thin shell로 분리하고 render/order contract를 focused tests로 고정한다.
- [x] Step 95: `WdCalculatorAddOptionButton.configure` + `WdCalculatorCalculateButton.configure` + `WdCalculatorProductCatalogUI.configure` contiguous trio를 thin shell로 분리하고 render/order contract를 focused tests로 고정한다.
- [x] Step 96: `WdCalculatorCouponShippingWiring.configure` + `WdCalculatorSearchResultsLoad.configure` + `WdCalculatorRenderEstimatesList.configure` contiguous configure trio를 thin shell로 분리하고 render/order contract를 focused tests로 고정한다.
- [x] Step 97: tail phase의 `WdCalculatorLateBootstrap.configure/init` + `renderInitialBaseComponentsUi()` contiguous 구간을 thin shell로 분리하고 ordering contract를 focused tests로 고정한다.
- [x] Step 98: `WdCalculatorTotalEstimatesDisplay.configure` + `WdCalculatorStartupInit.configure` + `WdCalculatorTerminalInit.configure` + `initStartupInteractions()` contiguous block을 thin shell로 분리하고 coupon/bootstrap/mutation ordering contract를 focused tests로 고정한다.
- [x] Step 99: direct `WdCalculatorNotesUI.initNotesUi()` leaf bootstrap call을 thin shell로 분리하고 totals/startup/terminal 이후 ordering contract를 focused tests로 고정한다.
- [x] Step 100: direct `WdCalculatorLoadingDatabaseBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 coupon-search-render 뒤/totals-startup-terminal 앞 ordering contract를 focused tests로 고정한다.
- [x] Step 101: direct `WdCalculatorProductsEditingBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 primary UI bootstrap 앞 ordering contract를 focused tests로 고정한다.
- [x] Step 102: direct `WdCalculatorEstimatesEarlyBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 estimates alias 뒤/current-estimate-orchestration 앞 ordering contract를 focused tests로 고정한다.
- [x] Step 103: direct `WdCalculatorPostMutationUiBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 mutation bridge 뒤 exact late tail ordering contract를 focused tests로 고정한다.
- [x] Step 104: direct `WdCalculatorNotesUiBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 totals-startup-terminal 뒤/loadInitialProducts 앞 ordering contract를 focused tests로 고정한다.
- [x] Step 105: direct `WdCalculatorCatalogButtonsBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 current-estimate-orchestration 뒤/coupon-search-render 앞 ordering contract를 focused tests로 고정한다.
- [x] Step 106: direct `WdCalculatorCouponSearchRenderBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 catalog-buttons host 뒤/totals-startup-terminal 앞 ordering contract를 focused tests로 고정한다.
- [x] Step 107: direct `WdCalculatorTotalsStartupTerminalBootstrap.configure/init` host invocation pair를 thin host shell로 분리하고 coupon-search-render host 뒤/notes-ui host 앞 ordering contract를 focused tests로 고정한다.
- [ ] Step 108 (보류): direct `WdCalculatorEstimateMutationBridge.configure/init` host invocation pair를 thin host shell로 분리하고 `loadInitialProducts()` 뒤/post-mutation host 앞 ordering contract를 focused tests로 고정한다.
- [ ] Step 109: WDCalculator 남은 구조 작업을 micro host wrapper가 아니라 유지보수 의미 덩어리 기준으로 재기준선하고, 다음 실행 batch를 3~5개 chunk로 재편한다.

## 4. Historical verification archive
- 아래 검증 체크는 micro module 시대의 verification archive다. 이후 새 batch의 승인 기준은 `## 6. Direction Lock / 검증 규칙`을 따른다.
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
- [x] `search-results-load.js` contract(Node) 통과
- [x] `render-estimates-list.js` contract(Node) 통과
- [x] `reset-input-form-keep-customer.js` contract(Node) 통과
- [x] `load-estimate-to-input-form.js` contract(Node) 통과
- [x] `refresh-after-save.js` contract(Node) 통과
- [x] `base-components-ui.js` live interactions contract(Node) 통과
- [x] `url-bootstrap.js` contract(Node) 통과
- [x] `load-saved-estimate-to-form.js` contract(Node) 통과
- [x] `save-estimate.js` contract(Node) 통과
- [x] `add-estimate.js` contract(Node) 통과
- [x] `estimate-list-events.js` contract(Node) 통과
- [x] `total-estimates-display.js` contract(Node) 통과
- [x] `calculation-resolvers.js` contract(Node) 통과
- [x] `current-estimate-orchestration.js` contract(Node) 통과
- [x] `unsaved-exit-guard.js` contract(Node) 통과
- [x] `add-option-button.js` contract(Node) 통과
- [x] `calculate-button.js` contract(Node) 통과
- [x] `layout-sync-wiring.js` contract(Node) 통과
- [x] `sidebar-bootstrap.js` contract(Node) 통과
- [x] `startup-init.js` contract(Node) 통과
- [x] `terminal-init.js` contract(Node) 통과
- [x] `loading-state.js` contract(Node) 통과
- [x] `current-database-estimate-id.js` contract(Node) 통과
- [x] `products-state.js` contract(Node) 통과
- [x] `editing-estimate-id.js` contract(Node) 통과
- [x] `estimates-state.js` contract(Node) 통과
- [x] `estimates-early-bootstrap.js` contract(Node) 통과
- [x] `products-editing-bootstrap.js` contract(Node) 통과
- [x] `loading-database-bootstrap.js` contract(Node) 통과
- [x] `loading-database-host-bootstrap.js` contract(Node) 통과
- [x] `primary-ui-bootstrap.js` contract(Node) 통과
- [x] `catalog-buttons-bootstrap.js` contract(Node) 통과
- [x] `coupon-search-render-bootstrap.js` contract(Node) 통과
- [x] `coupon-search-render-host-bootstrap.js` contract(Node) 통과
- [x] `post-mutation-ui-bootstrap.js` contract(Node) 통과
- [x] `post-mutation-ui-host-bootstrap.js` contract(Node) 통과
- [x] `products-editing-host-bootstrap.js` contract(Node) 통과
- [x] `estimates-early-host-bootstrap.js` contract(Node) 통과
- [x] `totals-startup-terminal-bootstrap.js` contract(Node) 통과
- [x] `totals-startup-terminal-host-bootstrap.js` contract(Node) 통과
- [x] `notes-ui-bootstrap.js` contract(Node) 통과
- [x] `notes-ui-host-bootstrap.js` contract(Node) 통과
- [x] `catalog-buttons-host-bootstrap.js` contract(Node) 통과
- [x] `early-bootstrap.js` contract(Node) 통과
- [x] `late-bootstrap.js` contract(Node) 통과
- [x] `estimate-mutation-bridge.js` contract(Node) 통과
- [x] `wdcalculator_scripts.html` syntax parse smoke 통과
- [x] 신규 lint 없음
- [x] `python -c "import app; print('APP_OK')"` 통과

## 5. Next execution steps
- [ ] Step 1: `static/js/wdcalculator/README.md`를 만들고 current file map, 읽기 순서, canonical chunk, removal target을 정리한다.
- [ ] Step 2: `composition` chunk부터 시작해 bootstrap/host/helper inflation을 먼저 줄인다.
- [ ] Step 3: `primary form` chunk에서 form-related UI leaf를 큰 owner chunk로 다시 묶는다.
- [ ] Step 4: `estimate lifecycle` chunk에서 save/load/list/sidebar/url/state shard를 정리한다.
- [ ] Step 5: `pricing core` chunk에서 math/totals/resolvers/orchestration을 큰 pricing cluster로 다시 묶는다.
- [ ] Step 6: obsolete micro file과 obsolete micro contract pair를 같은 축에서 제거/통합한다.

## 6. Direction Lock / 검증 규칙
- [ ] `/wdcalculator` runtime contract와 API payload surface를 유지한다.
- [ ] 새 batch는 structure-only first 원칙을 지키고, pricing/API/business logic 변경을 섞지 않는다.
- [ ] 새 batch는 `delete -> merge -> extend existing chunk -> add new file` 순서를 실제로 검토한다.
- [ ] 새 file이 있다면 왜 그것이 **가장 큰 유지보수 가능 chunk**인지 적는다.
- [ ] file/wrapper/test delta와 removal target이 같은 기록 안에 있다.
- [ ] local `README.md`가 현재 chunk map과 읽기 순서를 반영한다.
- [ ] 같은 concern의 peer file이 계속 늘어나면 merge-back review 없이 다음 batch로 가지 않는다.
- [ ] micro contract pair를 늘리기보다 chunk contract로 접는 방향인지 확인한다.

## 7. Historical QA baseline (chunk merge 전 reference)
- 아래 baseline은 micro extraction이 누적된 현재 runtime surface의 archive다.
- 이후 chunk merge가 진행되면 여러 micro check를 하나의 chunk contract로 접는 방향을 기본값으로 삼는다.
- runtime coverage는 유지하되, 장기 목표는 테스트 파일 수도 함께 정리하는 것이다.
- `/wdcalculator` 첫 로드 시 console error 없음
- categories / notes categories UI 표시 정상
- product dropdown 로드 정상
- estimate add/save/load smoke 정상
- sidebar estimate search/refresh/delete smoke 정상
- 저장 직후 sidebar row highlight가 버튼이 아닌 row container 기준으로 동작
- aggregate totals/save payload totals가 같은 helper 경로를 사용
- current estimate DOM summary와 collect snapshot이 같은 helper 경로를 사용
- current estimate coupon/final price DOM render와 edit-mode/add-save button visibility가 helper 경로에서 유지됨
- beforeunload unsaved-exit guard가 module 경로로 유지됨
- reset/load/add/list/save configure+init bridge가 `estimate-mutation-bridge.js` module 경로로 유지됨
- `#addOptionBtn` → `appendAdditionalOptionRow(..., { forceMode: 'select', formatPriceOnInput: false })` wiring이 module 경로로 유지됨
- add-option/calculate/product-catalog host ordering이 `catalog-buttons-host-bootstrap.js` module 경로로 유지되고 underlying configure trio payload는 `catalog-buttons-bootstrap.js` 경로로 전달됨
- notes load/collect roundtrip과 currentEstimate.notes snapshot이 유지됨
- base-components row render/read/update와 delegated recalculation hook이 module 경로로 유지됨
- coupon input parse와 final price/coupon text style helper가 module 경로로 유지됨
- additional-options row add/toggle/remove/read와 loadEstimate restore wiring이 module 경로로 유지됨
- search results render와 `.load-estimate-btn` → `loadEstimateToForm` bridge가 module 경로로 유지됨
- coupon-shipping/search-results/render-list configure trio가 `coupon-search-render-bootstrap.js` module 경로로 유지됨
- in-session estimates card render와 summary panel/style pass가 module 경로로 유지됨
- 저장 직후 clear/reset/render/sidebar-refresh/highlight orchestration이 module 경로로 유지됨
- 고객명 보존 reset path가 module 경로로 유지됨
- local estimate → input-form restore path가 module 경로로 유지됨
- saved DB estimate → form hydrate path가 module 경로로 유지됨
- save button clone/replace + save fetch orchestration이 module 경로로 유지됨
- add/update local mutation + follow-up save-button listener가 module 경로로 유지됨
- baseComponentsContainer add row/click/input/change live interactions가 module 경로로 유지됨
- `order_id` back link와 `estimate_id` deep-link bootstrap이 module 경로로 유지됨
- `?estimate_id=` / `?order_id=` query param flow 정상
- early startup call order 7개와 empty-category warning branch가 `startup-init.js` module 경로로 유지됨
- `loadProducts()` 초기 호출과 `ensureBaseComponentsUI()` terminal bootstrap call이 `terminal-init.js` module 경로로 유지됨
- late tail host ordering이 `post-mutation-ui-host-bootstrap.js` module 경로로 유지되고 underlying late/bootstrap/render payload는 `post-mutation-ui-bootstrap.js` 경로로 전달됨
- totals/startup/terminal contiguous configure+init block이 `totals-startup-terminal-bootstrap.js` module 경로로 유지됨
- notes leaf bootstrap host ordering이 `notes-ui-host-bootstrap.js` module 경로로 유지되고 underlying notes init call-through는 `notes-ui-bootstrap.js` 경로로 전달됨
- estimates seed + early bootstrap host head ordering이 `estimates-early-host-bootstrap.js` module 경로로 유지되고 underlying seed/bootstrap payload는 `estimates-early-bootstrap.js` 경로로 전달됨
- products/editing state seed pair host ordering이 `products-editing-host-bootstrap.js` module 경로로 유지되고 underlying seed payload는 `products-editing-bootstrap.js` 경로로 전달됨
- loading/currentDatabase state seed pair host ordering이 `loading-database-host-bootstrap.js` module 경로로 유지되고 underlying seed payload는 `loading-database-bootstrap.js` 경로로 전달됨
- base/coupon/additional primary UI configure + destructuring bridge가 `primary-ui-bootstrap.js` module 경로로 유지됨
- `WdCalculatorUnsavedExitGuard` / `WdCalculatorLayoutSyncWiring` early configure+init ordering이 `early-bootstrap.js` module 경로로 유지됨
- sidebar returned API capture와 `refresh-after-save` / `url-bootstrap` late ordering이 `late-bootstrap.js` module 경로로 유지됨
- `isLoadingEstimate`, `currentDatabaseEstimateId`, `products`, `editingEstimateId`, `estimates`가 helper module 경로에서 공유되고 host raw local 변수로 남지 않음

## 8. 참고 자료
- 관련 inventory: `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
- 관련 spec: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
- 관련 상태 문서: `docs/AI_STATUS.md`
