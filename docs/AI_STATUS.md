# FOMS 현재 상태
> 자동 업데이트: 2026-04-14 | 마지막 작업: Wave 5 W5-B3 WDCalculator `primary-form.js` 병합(구 notes/base/coupon/additional/add-option/calculate/catalog 7모듈 제거)

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-04-14] Wave 5 W5-B3 WDCalculator **primary-form** 청크: `notes-ui`, `base-components-ui`, `coupon-display-helpers`, `additional-options-ui`, `add-option-button`, `calculate-button`, `product-catalog-ui` 7개를 `static/js/wdcalculator/primary-form.js`로 병합·삭제하고 `wdcalculator_scripts_config.html`은 `primary-form.js` 단일 태그 + `current-estimate-orchestration.js` 순서로 정렬. Node contract·페이지 렌더 테스트는 `primary-form.js` 소스 기준으로 갱신. 검증: `APP_OK`, `verify_result.py --json`, `test_wdcalculator_product_settings`, primary-form 관련 pytest subset. run record: `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md`.
- [2026-04-14] Wave 5 W5-B2 WDCalculator **composition** 청크: 구 `*-bootstrap.js` / `*-host-bootstrap.js` 밴드 22개를 `static/js/wdcalculator/composition.js`로 수령하고 `wdcalculator_scripts_config.html`은 단일 `<script src=composition.js>`로 로드. Node contract 테스트는 동일 `WdCalculator*` 계약을 `composition.js` 전체 eval(+ `document` sandbox)로 검증. 검증: `APP_OK`, `verify_result.py --json`, `tests/test_wdcalculator_product_settings.py`, 22개 bootstrap contract pytest. run record: `docs/plans/2026-04-14-wave5-batch2-wdcalculator-composition-run-record.md`.
- [2026-04-14] Wave 4 Web/page slice migration 완료: `docs/plans/2026-04-13-wave4-web-page-slice-migration-execution-plan.md` 순서대로 pilot **`cs`** (`foms/web/cs/completion_dashboard` + `templates/cs/`)와 dashboard family winner **`production`** (`foms/web/production/dashboard` + `templates/production/`)를 정본으로 두고 `apps/erp_completion_page`·`apps/erp_production_page`는 Measurement식 module alias thin shim만 유지. `blueprints.py`·shared shell freeze 목록은 비변경. `construction`은 W4-B4에서 비교 패배로 defer, `drawing`/shipment/as/shell은 W4-B7 defer register. 검증: `APP_OK`, `verify_result.py --json`, `tests/test_foms_namespace_imports.py`, `tests/test_menu_config.py`. run record W4-B0~B7·spec §5 참고·`docs/ARCHIVE_INDEX.md` 갱신.
- [2026-04-13] Wave 3 API 정본화 실행 완료: `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md` 배치 순서(W3-B0~B6)대로 `files`/`address`/`personal_board`를 `foms/api/*` 정본 + `apps/api/*` thin으로 정렬했고, 집계 읽기 잠금은 winner `personal_board`(loser `events`는 run record에 명시). `foms/platform/blueprints.py` 등록 순서·import 경로는 변경하지 않았으며, run record·`docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §5·`docs/ARCHIVE_INDEX.md`에 흔적 반영. 검증: `APP_OK`, `verify_result.py --json`, 네임스페이스·저장소 계약 테스트 통과.
- [2026-04-13] wdcalculator handoff checkpoint + chunking rebaseline 정리: 새 세션에서 바로 이어갈 수 있도록 `docs/context/COMPACT_CHECKPOINT.md`를 신설했고, 최종 목표는 유지하되 WDCalculator는 더 이상 thin host shell 1개씩 늘리는 micro-batch로 진행하지 않고 유지보수 편의성이 실제로 올라가는 의미 있는 chunk 단위로 재기준선하기로 확정했다.

## 진행 중
- [2026-04-14] Wave 5 WDCalculator: W5-B3 primary-form 완료. 다음은 계획서 순서대로 **W5-B4 estimate-lifecycle** 청크.
- [2026-03-26] 채널톡 연동 파일럿(Wave 0 ~ 5) 운영 모니터링 (실제 데이터 축적 대기 중)

## 검증 필요
- [x] 실측 summary panel vs 실측 대시보드/지도 건수 parity 수동 확인 (temp QA 기준 2026-04-11 row 3 / panel 3 / map total_orders 3 일치 확인)
- [x] 실측 지도 E2E: `/erp/measurement?open_map=1` → `map_view` redirect, `/api/map_data`·`/api/generate_map` server smoke와 브라우저 시각 확인까지 temp QA 기준 완료
- [x] Legacy 정리: `python scripts/fix_geocode_status_inconsistency.py` 1회 실행 완료 (`정리 대상 없음`)
- [x] Phase C 마이그레이션: Railway/운영에서 인덱스 2개 적용 완료 확인 (2026-03-18 `check_phase_c_indexes.py`로 검증)
- [x] 시공팀 접근 제한 + mine 필터 수동 테스트 (temp QA construction user 기준 `/erp/shipment` mine=assigned only, `/erp/measurement`·`/erp/dashboard` 접근 시 `/erp/shipment` redirect 확인)
- [x] 출고 대시보드 시공자 그룹 파스텔 색상 확인 (temp QA shipment UI에서 `시공1` light-blue pastel 그룹 스타일 확인)
- [x] 성능 최적화(Phase) 전반 체감 속도 향상 확인 (temp QA 기준 `/erp/measurement`, `/map_view`, `/api/generate_map`, `/api/map_data` timing smoke 재확인)

## 알려진 이슈
- 차단 이슈 없음. W5-B2~B3 이후 구 thin bootstrap은 `composition.js`, 주요 폼/카탈로그 밴드는 `primary-form.js`로 수령했으며, Node contract 테스트는 레거시 파일명을 쓰더라도 실제 `helperPath`/`vm` 소스는 해당 canonical chunk 기준이다. `wdcalculator_scripts_config.html` Jinja 상단 변수 주입 구간의 JS lint false-positive는 기존과 동일하게 남아 있다.

## 핵심 모듈 (최근 수정)
| 파일 | 역할 |
|------|------|
| `docs/plans/2026-04-13-wave4-batch*-run-record.md` | Wave 4 Web/page slice 실행 기록(B0~B7). pilot `cs` + dashboard winner `production`; `foms/web/cs|production` 정본, `apps/erp_*_page` thin alias; W4-B7 defer·continuation |
| `foms/web/cs/completion_dashboard.py` | 시공 완료 대시보드 Blueprint SoT (`/erp/completion`) |
| `foms/web/production/dashboard.py` | 생산 대시보드 Blueprint SoT (`/erp/production/dashboard`) |
| `templates/cs/completion_dashboard.html`, `templates/production/dashboard.html` | Wave 4 canonical 템플릿 네임스페이스; legacy `erp_*` 경로는 extends/include-only |
| `docs/plans/2026-04-13-wave3-batch*-run-record.md` | Wave 3 API 정본화 실행 기록(B0~B6). `files`·`address`·`personal_board`는 `foms/api/*` 정본 + `apps/api/*` thin, 집계 읽기 잠금 winner `personal_board` |
| `foms/api/files.py`, `foms/api/address.py`, `foms/api/personal_board.py` | Wave 3 정본 API 모듈(라우트·헬퍼·집계). `apps/api/*.py`는 Blueprint·`login_required`·재노출만 담당 |
| `docs/context/COMPACT_CHECKPOINT.md` | 새 Cursor 창에서 바로 이어가기 위한 handoff 기준 문서. 최종 목표 유지, micro-batch 중단, 다음 세션 첫 작업을 한 장에 요약 |
| `docs/plans/2026-04-14-wave5-batch2-wdcalculator-composition-run-record.md` | W5-B2 composition 병합·검증·제거 파일 목록 |
| `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md` | W5-B3 primary-form 병합·검증·제거 파일 목록 |
| `static/js/wdcalculator/composition.js` | Wave 5 **composition** canonical chunk: 구 thin bootstrap / host-bootstrap 밴드 22개 모듈 본문을 단일 파일로 수령(주석 `/* included: … */`로 구간 표시). `wdcalculator_scripts_config.html`에서 `shared`·guard·layout 다음 단일 `<script src>` |
| `static/js/wdcalculator/primary-form.js` | Wave 5 **primary-form** canonical chunk: notes / base-components / coupon / additional-options / add-option / calculate / product-catalog 7모듈을 단일 파일로 병합·개별 파일 제거. `WdCalculatorNotesUI`, `WdCalculatorBaseComponentsUI`, `WdCalculatorCouponDisplayHelpers`, `WdCalculatorAdditionalOptionsUI`, `WdCalculatorAddOptionButton`, `WdCalculatorCalculateButton`, `WdCalculatorProductCatalogUI` 등 동일 전역 계약 유지 |
| `static/js/wdcalculator/estimate-mutation-bridge.js` | host 중반의 `WdCalculatorResetInputFormKeepCustomer` / `WdCalculatorLoadEstimateToInputForm` / `WdCalculatorLoadSavedEstimateToForm` / `WdCalculatorAddEstimate` / `WdCalculatorEstimateListEvents` / `WdCalculatorSaveEstimate` configure+init 순서를 giant inline script 밖으로 분리한 thin mutation bridge shell |
| `static/js/wdcalculator/estimates-state.js` | `estimates` live array를 stable-reference로 유지하면서 delete/hydrate/refresh replacement와 add/rename direct mutation을 함께 수용하는 host-state helper |
| `static/js/wdcalculator/editing-estimate-id.js` | `editingEstimateId` scalar state를 giant inline script 밖으로 분리한 thin host-state helper |
| `static/js/wdcalculator/products-state.js` | `products` 단일 source를 giant inline script 밖으로 분리한 thin host-state helper |
| `static/js/wdcalculator/current-database-estimate-id.js` | `currentDatabaseEstimateId` scalar state를 giant inline script 밖으로 분리한 thin host-state helper |
| `static/js/wdcalculator/loading-state.js` | `isLoadingEstimate` scalar state를 giant inline script 밖으로 분리한 thin host-state helper |
| `static/js/wdcalculator/layout-sync-wiring.js` | `resize`/`load` listener와 immediate `requestWdCalculatorLayoutSync()` 호출을 giant inline script 밖으로 분리한 thin layout wiring helper |
| `static/js/wdcalculator/unsaved-exit-guard.js` | `estimates.length > 0`일 때 beforeunload 경고 문구와 `preventDefault`/`returnValue`를 적용하는 unsaved-exit guard helper |
| `static/js/wdcalculator/calculation-resolvers.js` | current-estimate math helper와 aggregate totals helper의 load-order guard/pass-through를 giant inline script 밖으로 분리한 thin resolver module |
| `static/js/wdcalculator/total-estimates-display.js` | `calculateTotalEstimates()`의 aggregate display orchestration(zero-state/current summary/overall summary/notes toggle)을 giant inline script 밖으로 분리한 helper |
| `static/js/wdcalculator/estimate-list-events.js` | `#estimatesListContainer` delegated click(수정/이름편집/삭제/카드클릭)과 `isLoadingEstimate` 가드를 giant inline script 밖으로 분리한 list-interactions helper |
| `static/js/wdcalculator/current-estimate-orchestration.js` | `calculateEstimate()`와 `collectCurrentEstimate()`의 DOM render/snapshot assembly를 giant inline script 밖으로 분리한 current-estimate orchestration helper |
| `static/js/wdcalculator/current-estimate-math.js` | 건별 base component + option 합산 정책과 normalized snapshot을 계산하는 current-estimate helper |
| `static/js/wdcalculator/estimate-totals.js` | aggregate totals/coupon/shipping 정책을 giant inline script 밖으로 분리한 순수 helper |
| `static/js/wdcalculator/search-results-load.js` | 고객명 search-estimates 호출, 검색 결과 render, `.load-estimate-btn`→`loadEstimateToForm` bridge를 giant inline script 밖으로 분리한 search/load module |
| `static/js/wdcalculator/render-estimates-list.js` | in-session estimates card render, summary panel, post-render style pass를 giant inline script 밖으로 분리한 estimates-list view module |
| `static/js/wdcalculator/reset-input-form-keep-customer.js` | 고객명 보존 reset path(`editingEstimateId` reset, base-components/notes clear, section hide, totals/button reset, 재계산)를 giant inline script 밖으로 분리한 reset helper |
| `static/js/wdcalculator/load-estimate-to-input-form.js` | local `estimates[]` 항목을 base-components/additional-options/notes UI로 복원하고 edit mode/add button/loading-state를 정리하는 local edit-load helper |
| `static/js/wdcalculator/load-saved-estimate-to-form.js` | DB estimate hydrate path(`currentDatabaseEstimateId`, header/reset button, saved line-item mapping, form reset, 재계산)를 giant inline script 밖으로 분리한 saved-estimate hydrate helper |
| `static/js/wdcalculator/save-estimate.js` | save button clone/replace, payload 조립, save fetch, button spinner/restore, success refresh ordering을 giant inline script 밖으로 분리한 save helper |
| `static/js/wdcalculator/add-estimate.js` | add/update listener의 local estimate mutation, displayName 유지/갱신 규칙, follow-up save-button show listener를 giant inline script 밖으로 분리한 add helper |
| `static/js/wdcalculator/refresh-after-save.js` | 저장 성공 뒤 local estimates clear, form reset, delayed list/sidebar refresh, saved row highlight/badge cleanup을 giant inline script 밖으로 분리한 post-save helper |
| `static/js/wdcalculator/url-bootstrap.js` | `order_id` back link, `estimate_id` deep-link load, product-ready polling/timeout을 giant inline script 밖으로 분리한 URL bootstrap module |
| `static/js/wdcalculator/order-match-ui.js` | search result의 주문 매칭 버튼, modal 선택, match API 호출을 giant inline script 밖으로 분리한 order-match module |
| `static/js/wdcalculator/coupon-shipping-wiring.js` | shipping/coupon global input listener를 giant inline script 밖으로 분리한 recalculation wiring module |
| `templates/wdcalculator/partials/wdcalculator_scripts_config.html` | Jinja config 주입 + `shared.js` → guard → layout → **`composition.js`** → 나머지 모듈 순서. 구 개별 bootstrap `<script>` 다발은 제거됨 |
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | giant inline WDCalculator app bootstrap을 유지하는 current app script boundary |
| `tests/test_wdcalculator_*_bootstrap_contract_node.py` (host/bootstrap 계열) | **W5-B2:** 레거시 파일명 유지. 실제 검증은 `static/js/wdcalculator/composition.js`를 Node VM에서 eval(`document` stub 포함)하고, 해당 밴드에 해당하는 `WdCalculator*` configure/init/forwarding 계약을 고정한다. |
| `tests/support/wdcalculator_*_bootstrap_contract_node_checks.js` | 위와 동일: `helperPath`가 `composition.js`를 가리키며 구 per-file bootstrap 소스는 제거됨 |
| `tests/test_wdcalculator_estimates_early_host_bootstrap_contract_node.py` | composition.js 내 estimates-early **host** 밴드의 configure/init forwarding contract (Node) |
| `tests/support/wdcalculator_estimates_early_host_bootstrap_contract_node_checks.js` | composition.js eval로 host 밴드 helper 동작 고정 |
| `tests/test_wdcalculator_products_editing_host_bootstrap_contract_node.py` | composition.js 내 products-editing **host** 밴드 contract (Node) |
| `tests/support/wdcalculator_products_editing_host_bootstrap_contract_node_checks.js` | composition.js eval로 host 밴드 helper 동작 고정 |
| `tests/test_wdcalculator_loading_database_host_bootstrap_contract_node.py` | composition.js 내 loading-database **host** 밴드 contract (Node) |
| `tests/support/wdcalculator_loading_database_host_bootstrap_contract_node_checks.js` | composition.js eval로 host 밴드 helper 동작 고정 |
| `tests/test_wdcalculator_notes_ui_bootstrap_contract_node.py` | composition.js 내 notes-ui bootstrap 밴드의 `initNotesUi()` call-through contract (Node) |
| `tests/support/wdcalculator_notes_ui_bootstrap_contract_node_checks.js` | composition.js eval로 notes-ui 밴드 고정 |
| `tests/test_wdcalculator_totals_startup_terminal_bootstrap_contract_node.py` | composition.js 내 totals/startup/terminal bootstrap 밴드 ordering contract (Node) |
| `tests/support/wdcalculator_totals_startup_terminal_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_post_mutation_ui_bootstrap_contract_node.py` | composition.js 내 post-mutation UI bootstrap 밴드 contract (Node) |
| `tests/support/wdcalculator_post_mutation_ui_bootstrap_contract_node_checks.js` | composition.js eval로 post-mutation UI 밴드 고정 |
| `tests/test_wdcalculator_post_mutation_ui_host_bootstrap_contract_node.py` | composition.js 내 post-mutation UI **host** 밴드 contract (Node) |
| `tests/support/wdcalculator_post_mutation_ui_host_bootstrap_contract_node_checks.js` | composition.js eval로 post-mutation host 밴드 고정 |
| `tests/test_wdcalculator_coupon_search_render_bootstrap_contract_node.py` | composition.js 내 coupon/search/render configure 밴드 contract (Node) |
| `tests/support/wdcalculator_coupon_search_render_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_catalog_buttons_bootstrap_contract_node.py` | composition.js 내 catalog-buttons configure 밴드 contract (Node) |
| `tests/support/wdcalculator_catalog_buttons_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_primary_ui_bootstrap_contract_node.py` | composition.js 내 primary-ui configure 밴드 contract (Node) |
| `tests/support/wdcalculator_primary_ui_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_loading_database_bootstrap_contract_node.py` | composition.js 내 loading-database (non-host) seed 밴드 contract (Node) |
| `tests/support/wdcalculator_loading_database_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_products_editing_bootstrap_contract_node.py` | composition.js 내 products-editing seed 밴드 contract (Node) |
| `tests/support/wdcalculator_products_editing_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_estimates_early_bootstrap_contract_node.py` | composition.js 내 estimates-early bootstrap 밴드 contract (Node) |
| `tests/support/wdcalculator_estimates_early_bootstrap_contract_node_checks.js` | composition.js eval로 해당 밴드 고정 |
| `tests/test_wdcalculator_estimate_mutation_bridge_contract_node.py` | `estimate-mutation-bridge.js`의 reset/load/add/list/save configure+init ordering contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_estimate_mutation_bridge_contract_node_checks.js` | estimate-mutation bridge helper를 VM sandbox에서 직접 실행해 각 submodule configure payload와 init call order를 고정하는 Node support script |
| `tests/test_wdcalculator_late_bootstrap_contract_node.py` | composition.js 내 late-bootstrap 밴드(sidebar API → refresh/url) contract (Node) |
| `tests/test_wdcalculator_early_bootstrap_contract_node.py` | composition.js 내 early-bootstrap 밴드(unsaved/layout) contract (Node) |
| `tests/test_wdcalculator_estimates_state_contract_node.py` | `estimates-state.js`의 stable-reference get/set/configure contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_product_settings.py` | wdcalculator render contract + calculate/save/load/search/delete smoke를 고정하는 focused regression test |
| `tests/test_wdcalculator_editing_estimate_id_contract_node.py` | `editing-estimate-id.js`의 get/set/configure contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_products_state_contract_node.py` | `products-state.js`의 array source/setter contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_current_database_estimate_id_contract_node.py` | `current-database-estimate-id.js`의 get/set/configure contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_loading_state_contract_node.py` | `loading-state.js`의 boolean state contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_terminal_init_contract_node.py` | `terminal-init.js`의 terminal bootstrap call-through contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_terminal_init_contract_node_checks.js` | terminal-init helper를 VM sandbox에서 직접 실행해 `loadProducts`/`ensureBaseComponentsUI` exact target/result pass-through를 고정하는 Node support script |
| `tests/test_wdcalculator_startup_init_contract_node.py` | `startup-init.js`의 early startup call order와 empty-category warning contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_startup_init_contract_node_checks.js` | startup-init helper를 VM sandbox에서 직접 실행해 init order 7개와 empty-category warning/no-warning branch를 고정하는 Node support script |
| `tests/test_wdcalculator_render_list_contract_node.py` | renderEstimatesList view의 empty state/card markup/summary layout/render completion contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_render_list_contract_node_checks.js` | render list helper를 VM DOM stub에서 직접 실행해 card/summary/style/callback contract를 고정하는 Node support script |
| `tests/test_wdcalculator_reset_input_form_keep_customer_contract_node.py` | resetInputFormKeepCustomerName의 customer restore/base-components reset/notes reset/button reset/currentDatabaseEstimateId 유지 contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_reset_input_form_keep_customer_contract_node_checks.js` | reset-input-form helper를 VM DOM stub에서 직접 실행해 reset 단계, fail-soft logging, outer catch customer 재복원 contract를 고정하는 Node support script |
| `tests/test_wdcalculator_load_estimate_to_input_form_contract_node.py` | loadEstimateToInputForm의 confirm/invalid/missing-id/legacy fallback/loading-state finally contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_load_estimate_to_input_form_contract_node_checks.js` | load-estimate-to-input-form helper를 VM DOM stub에서 직접 실행해 local estimate → form restore/edit mode/loading-state contract를 고정하는 Node support script |
| `tests/test_wdcalculator_refresh_after_save_contract_node.py` | refreshAfterSave post-save refresh/highlight의 clear/reset/timer/sidebar retry/highlight contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_refresh_after_save_contract_node_checks.js` | refresh-after-save helper를 VM DOM stub에서 직접 실행해 clear→reset 순서, nested timeout, saved row badge cleanup, fallback refresh contract를 고정하는 Node support script |
| `tests/test_wdcalculator_load_saved_estimate_to_form_contract_node.py` | `load-saved-estimate-to-form.js`의 DB id/header/reset button/estimate hydrate/empty-estimates contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_load_saved_estimate_to_form_contract_node_checks.js` | saved-estimate hydrate helper를 VM DOM stub에서 직접 실행해 create-or-reuse reset button, line-item mapping, empty path baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_save_estimate_contract_node.py` | `save-estimate.js`의 clone/replace, synthesized save payload, button lifecycle, success/error refresh ordering contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_save_estimate_contract_node_checks.js` | save helper를 VM DOM stub에서 직접 실행해 save button rebinding, aggregate/fetch branches, payload shape, refresh ordering baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_add_estimate_contract_node.py` | `add-estimate.js`의 add/update mutation, displayName preserve vs refresh, follow-up save-button visibility contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_add_estimate_contract_node_checks.js` | add helper를 VM DOM stub에서 직접 실행해 primary/follow-up listener binding, ID 보존, missing target alert/log, original onclick replay baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_estimate_list_events_contract_node.py` | `estimate-list-events.js`의 delegated load/loading guard/inline name edit/delete/card click contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_estimate_list_events_contract_node_checks.js` | list-events helper를 VM DOM stub에서 직접 실행해 0ms focus, 10ms rerender, blur 200ms auto-save, delete confirm/edit-reset baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_calculation_resolvers_contract_node.py` | `calculation-resolvers.js`의 current/aggregate helper pass-through signature와 helper 미로드 오류 문자열 contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_calculation_resolvers_contract_node_checks.js` | resolver helper를 VM sandbox에서 직접 실행해 current/aggregate call shape와 load-order guard baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_unsaved_exit_guard_contract_node.py` | `unsaved-exit-guard.js`의 beforeunload listener 등록/no-op/exact leave-warning contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_unsaved_exit_guard_contract_node_checks.js` | unsaved-exit guard helper를 VM sandbox에서 직접 실행해 `preventDefault`/`returnValue` baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_sidebar_bootstrap_contract_node.py` | `sidebar-bootstrap.js`의 bootstrap option shape와 returned API pass-through contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js` | sidebar bootstrap helper를 VM sandbox에서 직접 실행해 `loadEstimateToForm`/`formatNumber` bridge와 `loadSidebarEstimates`/`deleteEstimate` ref pass-through baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_layout_sync_wiring_contract_node.py` | `layout-sync-wiring.js`의 resize/load listener 등록과 immediate sync contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_layout_sync_wiring_contract_node_checks.js` | layout-sync wiring helper를 VM sandbox에서 직접 실행해 listener 등록, shared handler, immediate sync/no-window branch baseline을 고정하는 Node support script |
| `tests/test_wdcalculator_calculate_button_contract_node.py` | `primary-form.js` 내 `WdCalculatorCalculateButton` 밴드의 null-guard + `calculateEstimate()` click bridge contract를 Node로 검증 |
| `tests/support/wdcalculator_calculate_button_contract_node_checks.js` | `primary-form.js` 전체를 VM에서 로드한 뒤 `WdCalculatorCalculateButton.configure`·init contract 고정 |
| `tests/test_wdcalculator_add_option_button_contract_node.py` | `primary-form.js` 내 `WdCalculatorAddOptionButton` 밴드의 button binding·`appendAdditionalOptionRow` call shape contract를 Node로 검증 |
| `tests/support/wdcalculator_add_option_button_contract_node_checks.js` | `primary-form.js` 전체를 VM에서 로드한 뒤 add-option wiring contract 고정 |
| `tests/test_wdcalculator_calculate_total_estimates_contract_node.py` | `total-estimates-display.js`의 zero-state reset, aggregate helper 호출, editing guard, notes/summary DOM write contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_calculate_total_estimates_contract_node_checks.js` | total-estimates-display helper를 VM DOM stub에서 직접 실행해 coupon/shipping DOM read, option aggregation, optional totalAllPrice, helper error stop branch를 고정하는 Node support script |
| `tests/test_wdcalculator_base_live_events_contract_node.py` | `primary-form.js`에서 추출한 base-components live interactions(add row + delegation) contract를 Node로 검증 |
| `tests/support/wdcalculator_base_live_events_contract_node_checks.js` | `primary-form.js` 소스에서 live-interaction 블록을 추출·실행해 wiring contract 고정 |
| `tests/test_wdcalculator_url_bootstrap_contract_node.py` | URL/deep-link bootstrap의 back button/deep-link fetch/poll/timeout/retry contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_url_bootstrap_contract_node_checks.js` | URL bootstrap helper를 VM stub에서 직접 실행해 order_id/estimate_id/timer/fetch surface를 고정하는 Node support script |
| `tests/test_wdcalculator_search_load_contract_node.py` | search results render와 `.load-estimate-btn` load-to-form bridge contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_search_load_contract_node_checks.js` | search results + load bridge helper를 VM DOM stub에서 직접 실행해 search-estimates URL/render/button dataset/load bridge contract를 고정하는 Node support script |
| `tests/test_wdcalculator_order_match_contract_node.py` | order matching UI의 delegated click/direct match/modal selection contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_order_match_contract_node_checks.js` | order matching legacy UI cluster를 VM DOM stub에서 직접 실행해 DOM/API contract를 고정하는 Node support script |
| `tests/test_wdcalculator_coupon_shipping_wiring_contract_node.py` | coupon/shipping global input listener의 DOM/event/recalc wiring contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_coupon_shipping_wiring_contract_node_checks.js` | template 하단 shipping/coupon listener source를 VM DOM stub에서 직접 실행해 wiring contract를 고정하는 Node support script |
| `tests/test_wdcalculator_product_catalog_contract_node.py` | `primary-form.js` 내 product-catalog 밴드의 fetch/select/info/sync contract를 Node로 검증 |
| `tests/test_wdcalculator_additional_options_contract_node.py` | `primary-form.js`에서 추출한 additional-options row DOM/selectors·mode·read contract를 Node로 검증 |
| `tests/test_wdcalculator_coupon_display_contract_node.py` | `primary-form.js` 내 `WdCalculatorCouponDisplayHelpers` 쿠폰 파싱·스타일 contract를 Node로 검증 |
| `tests/test_wdcalculator_base_components_contract_node.py` | `primary-form.js`에서 추출한 base-components row DOM/selectors·hook contract를 Node로 검증 |
| `tests/test_wdcalculator_estimate_totals_node.py` | `estimate-totals.js` 수식을 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_notes_contract_node.py` | `primary-form.js`에서 추출한 notes load/collect·formatting contract를 Node로 검증 |

## 아키텍처 요약
- 파일 업로드: 브라우저→R2 Presigned PUT 직접 (배치+병렬, UUID키)
- 도면 생명주기: 발송(보존)→취소(신규만삭제)→확정(구버전정리)
- 지도: Folium iframe + `/api/map_data` 경량 폴링 (15s×5회)
- 성능/조회: `OrderScheduleDate`(날짜정규화), Partial Indexes, `Order.active_filter()` / `dashboard_active_filter(days=60)` 병행 계약 존재
- 권한: CONSTRUCTION팀 출고/시공만, 도면팀 발송/취소
- 하네스 문서 자산: Step 7에서 `docs/harness/{policy,bundles,runtime,logs}` canonical taxonomy로 분리됐고, `docs/context`는 incident/reference 기록만 유지한다
- 패키징: Step 8 verdict는 repo-root `foms/` boundary 유지이며, full `src/foms`/metadata hardening은 boot/worker/Alembic/tests import contract explicit화 전까지 defer 상태다
- 대형 파일 분해: Step 6에서 inventory와 separate governance spec이 분리됐고, 실제 split은 future batch에서 contract freeze 후 실행한다
