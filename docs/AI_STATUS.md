# FOMS 현재 상태
> 자동 업데이트: 2026-04-12 | 마지막 작업: wdcalculator search results + load-to-form batch 완료

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-04-12] wdcalculator search results + load-to-form batch 완료: 고객명 검색 버튼, `displaySearchResults()`, `.load-estimate-btn` re-fetch bridge를 `static/js/wdcalculator/search-results-load.js`로 분리하고, host giant script에는 `WdCalculatorSearchResultsLoad.configure({ loadEstimateToForm, formatNumber })` + `initSearchResultsLoadBridge()` bootstrap만 남겼다. 선행으로 고정한 Node contract는 blank input alert, search-estimates URL, empty-result message, rendered `data-customer-name`/`data-estimate-id`, `loadEstimateToForm` bridge, missing-estimate alert를 helper 기준으로 계속 검증하게 유지했다. `/wdcalculator` render contract에는 새 helper load-order를 추가했고 최종 검증은 related pytest `12 passed`, 신규 lint 없음이었다.
- [2026-04-12] wdcalculator coupon/shipping wiring batch 완료: 하단 global input listener(`shippingCost`, `shippingIncluded`, `globalCouponValue`)를 `static/js/wdcalculator/coupon-shipping-wiring.js`로 분리하고, host giant script에는 `WdCalculatorCouponShippingWiring.configure(...)` + `initCouponShippingWiring()` bootstrap만 남겼다. 선행으로 고정한 Node wiring contract도 extracted helper 기준으로 다시 연결해 shipping input/change, shippingIncluded change, coupon input/change/blur, empty/0 coupon 초기값 보정, initial load recalc, missing coupon input error branch를 계속 검증하도록 유지했다. `/wdcalculator` render contract에는 새 helper load-order를 추가했고 최종 검증은 focused pytest `12 passed`, 신규 lint 없음이었다.
- [2026-04-12] wdcalculator order-match UI batch 완료: `.match-order-btn` delegated click, `showOrderSelectionModal`, `matchEstimateToOrder`를 `static/js/wdcalculator/order-match-ui.js`로 분리하고, host giant script에는 `bindOrderMatchButtons()` bootstrap만 남겼다. 선행으로 고정한 Python API smoke와 Node DOM contract를 extracted helper 기준으로 다시 연결했고, `/wdcalculator` render contract에 `order-match-ui.js` load-order를 추가했다. Node contract는 direct-match / multi-order modal / empty-result alert뿐 아니라 `search-orders`와 `match-order` 실패 메시지 분기까지 함께 고정했다. 최종 검증은 focused pytest `10 passed`, 신규 lint 없음이었다.
- [2026-04-12] wdcalculator product-catalog batch 완료: `loadProducts`, `updateProductSelect`, `showProductInfo`, `#productSelect` change 경로를 `static/js/wdcalculator/product-catalog-ui.js`로 분리하고, host giant script에는 `products` state 연결과 bootstrap만 남겼다. 선행으로 focused Node contract(`tests/test_wdcalculator_product_catalog_contract_node.py`)와 render/API shape smoke를 고정했고, extraction 중에는 Node DOM stub의 `textContent`/`escapeHtml` drift를 브라우저 동작과 맞춰 `showProductInfo()` escaping contract까지 안정화했다. 최종 검증은 focused pytest `3 passed`, 신규 lint 없음이었다.
- [2026-04-12] wdcalculator additional-options batch 완료: 추가 옵션 row UI(`setOptionMode`, add/remove/toggle/select/read, loadEstimate restore 경로)를 `static/js/wdcalculator/additional-options-ui.js`로 분리하고, host giant script에는 `appendAdditionalOptionRow`, `loadAdditionalOptionRows`, `readAdditionalOptionRowsFromUI` bridge만 남겼다. 선행으로 focused Node contract(`tests/test_wdcalculator_additional_options_contract_node.py`)를 추가해 row DOM/schema, mode toggle, single remove recalc path, direct-input/select read contract를 고정했고, extraction 중에는 add path의 remove direct+delegated 중복 경로를 단일화했다. 최종 검증은 focused pytest `12 passed`, inline script syntax parse `WD_SCRIPTS_PARSE_OK`, `APP_OK`, 신규 lint 없음이었다.

## 진행 중
- [2026-04-12] 구조 트랙 다음 단계: 남은 giant inline cluster를 재감리한 결과, 다음 안전 후보는 `renderEstimatesList` + summary card + post-render style pass다. 현재는 이 in-session estimates list view의 DOM/selectors/render completion contract freeze를 준비 중이다.
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
- 차단 이슈 없음. search results + load bridge까지 빠지면서 남은 주요 리스크는 `renderEstimatesList`/summary panel, `refreshAfterSave`, `resetInputFormKeepCustomerName`, `loadEstimateToInputForm`, save button clone/replace, URL bootstrap이 `editingEstimateId`, `currentDatabaseEstimateId`, sidebar refresh 타이밍과 더 촘촘히 결합돼 있다는 점이다. 다음 batch는 그중에서도 read-mostly인 in-session estimates list view만 얇게 분리하고, save/API/URL orchestration은 계속 host에 남겨야 한다.

## 핵심 모듈 (최근 수정)
| 파일 | 역할 |
|------|------|
| `static/js/wdcalculator/additional-options-ui.js` | 추가 옵션 row add/toggle/remove/read와 loadEstimate restore 경로를 giant inline script 밖으로 분리한 UI module |
| `static/js/wdcalculator/coupon-display-helpers.js` | 쿠폰 입력값 읽기와 최종가/쿠폰 문구 스타일 적용을 giant inline script 밖으로 분리한 helper module |
| `static/js/wdcalculator/base-components-ui.js` | 복합 기본견적 행 렌더/DOM 읽기/product select 옵션 갱신을 giant inline script 밖으로 분리한 base-components module |
| `static/js/wdcalculator/notes-ui.js` | 비고 상태/렌더/이벤트와 `loadNotes`/`collectNotes` contract를 giant inline script 밖으로 분리한 notes UI module |
| `static/js/wdcalculator/current-estimate-math.js` | 건별 base component + option 합산 정책과 normalized snapshot을 계산하는 current-estimate helper |
| `static/js/wdcalculator/estimate-totals.js` | aggregate totals/coupon/shipping 정책을 giant inline script 밖으로 분리한 순수 helper |
| `static/js/wdcalculator/product-catalog-ui.js` | products fetch/dropdown/product info/base-components sync를 giant inline script 밖으로 분리한 product catalog module |
| `static/js/wdcalculator/search-results-load.js` | 고객명 search-estimates 호출, 검색 결과 render, `.load-estimate-btn`→`loadEstimateToForm` bridge를 giant inline script 밖으로 분리한 search/load module |
| `static/js/wdcalculator/order-match-ui.js` | search result의 주문 매칭 버튼, modal 선택, match API 호출을 giant inline script 밖으로 분리한 order-match module |
| `static/js/wdcalculator/coupon-shipping-wiring.js` | shipping/coupon global input listener를 giant inline script 밖으로 분리한 recalculation wiring module |
| `templates/wdcalculator/partials/wdcalculator_scripts_config.html` | Jinja config 주입 + `shared.js` load-order를 giant app script에서 분리한 새 thin partial |
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | giant inline WDCalculator app bootstrap을 유지하는 current app script boundary |
| `tests/test_wdcalculator_product_settings.py` | wdcalculator render contract + calculate/save/load/search/delete smoke를 고정하는 focused regression test |
| `tests/test_wdcalculator_search_load_contract_node.py` | search results render와 `.load-estimate-btn` load-to-form bridge contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_search_load_contract_node_checks.js` | search results + load bridge helper를 VM DOM stub에서 직접 실행해 search-estimates URL/render/button dataset/load bridge contract를 고정하는 Node support script |
| `tests/test_wdcalculator_order_match_contract_node.py` | order matching UI의 delegated click/direct match/modal selection contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_order_match_contract_node_checks.js` | order matching legacy UI cluster를 VM DOM stub에서 직접 실행해 DOM/API contract를 고정하는 Node support script |
| `tests/test_wdcalculator_coupon_shipping_wiring_contract_node.py` | coupon/shipping global input listener의 DOM/event/recalc wiring contract를 Node로 검증하는 focused regression test |
| `tests/support/wdcalculator_coupon_shipping_wiring_contract_node_checks.js` | template 하단 shipping/coupon listener source를 VM DOM stub에서 직접 실행해 wiring contract를 고정하는 Node support script |
| `tests/test_wdcalculator_product_catalog_contract_node.py` | product catalog legacy UI의 fetch/select/info/base-components sync contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_additional_options_contract_node.py` | additional-options row DOM/selectors, mode toggle, read/remove recalc contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_coupon_display_contract_node.py` | 쿠폰 입력 파싱과 final price/coupon style helper contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_base_components_contract_node.py` | base-components row DOM/selectors와 재계산 hook contract를 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_estimate_totals_node.py` | `estimate-totals.js` 수식을 Node로 검증하는 focused regression test |
| `tests/test_wdcalculator_notes_contract_node.py` | notes load/collect roundtrip과 formatting contract를 Node로 검증하는 focused regression test |

## 아키텍처 요약
- 파일 업로드: 브라우저→R2 Presigned PUT 직접 (배치+병렬, UUID키)
- 도면 생명주기: 발송(보존)→취소(신규만삭제)→확정(구버전정리)
- 지도: Folium iframe + `/api/map_data` 경량 폴링 (15s×5회)
- 성능/조회: `OrderScheduleDate`(날짜정규화), Partial Indexes, `Order.active_filter()` / `dashboard_active_filter(days=60)` 병행 계약 존재
- 권한: CONSTRUCTION팀 출고/시공만, 도면팀 발송/취소
- 하네스 문서 자산: Step 7에서 `docs/harness/{policy,bundles,runtime,logs}` canonical taxonomy로 분리됐고, `docs/context`는 incident/reference 기록만 유지한다
- 패키징: Step 8 verdict는 repo-root `foms/` boundary 유지이며, full `src/foms`/metadata hardening은 boot/worker/Alembic/tests import contract explicit화 전까지 defer 상태다
- 대형 파일 분해: Step 6에서 inventory와 separate governance spec이 분리됐고, 실제 split은 future batch에서 contract freeze 후 실행한다
