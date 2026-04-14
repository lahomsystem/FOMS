# Wave 5 Batch W5-B1 — WDCalculator contract freeze + chunk map lock

> **batch ID:** W5-B1  
> **risk axis:** docs / contract  
> **실행일:** 2026-04-14  
> **선행:** `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md` (complete)

## Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record | `apps/api/wdcalculator.py` 동작 변경 |
| `static/js/wdcalculator/README.md` 생성·보강 | pricing rule / API payload 변경 |
| | 신규 `*-host-bootstrap.js` |
| | 신규 micro contract pair 증식 |

## Stop check (§8 / 계획 §2.5)

| 조건 | 결과 |
|------|------|
| authoritative **four-chunk** map 확정 | **PASS** — 아래 §Authoritative four-chunk map |
| `composition`을 **first executable** canonical chunk로 lock | **PASS** — merge set + retire-later host band 명시 |
| `§2.4` 예시 표만 복사 | **아님** — `static/js/wdcalculator/*.js` **56개 전부** sweep |

→ **W5-B2 진행 가능.** 본 batch에서 W5-B9 partial closeout 트리거 없음.

## Public / runtime contract freeze

### Load order contract

| 순서 | 소스 | 내용 |
|------|------|------|
| 0 | `wdcalculator_scripts_config.html` 인라인 | `wdCalculatorCategories`, `wdNotesCategories`, `notesCategories` (Jinja `tojson`) |
| 1 | `shared.js` | 뷰포트/레이아웃 헬퍼·가격 유틸 `window.*` (아래 Globals) |
| 2 | `unsaved-exit-guard.js` | `WdCalculatorUnsavedExitGuard` |
| 3 | `layout-sync-wiring.js` | `WdCalculatorLayoutSyncWiring` → `requestWdCalculatorLayoutSync` 연동 |
| 4… | `wdcalculator_scripts_config.html` 나머지 `<script src>` | **고정 순서가 public contract**; chunk 수령 시에도 동일 의미의 초기화 순서를 유지하거나, 동일 batch에 bridge + removal plan 필요 |

**LF-compat:** `url_for('static', filename='js/wdcalculator/…')` 경로는 유지. 파일 물리 이동 금지(Wave 5 §1.1).

### Jinja / 페이지 글로벌 contract

| 심볼 | 출처 | freeze 메모 |
|------|------|----------------|
| `wdCalculatorCategories` | Jinja | 카테고리 배열 |
| `wdNotesCategories` / `notesCategories` | Jinja | 노트 카테고리 별칭 |
| `DEFAULT_COUPON_VALUE` 등 인라인 상수 | `wdcalculator_scripts.html` | DOMContentLoaded 핸들러 내부; chunk 병합 시 동일 의미 유지 |

### DOM / API / query contract (snapshot)

| 항목 | 관찰 근거 | freeze |
|------|-----------|--------|
| 글로벌 수학 진입점 | `current-estimate-math.js`, `estimate-totals.js` | `window.wdcComputeCurrentEstimateMath`, `window.wdcComputeAggregateTotals` — `calculation-resolvers.js`가 참조 |
| URL 자동 로드 | `url-bootstrap.js` | `URLSearchParams`; 쿼리 키 **`estimate_id`**; fetch `GET /api/wdcalculator/estimate/<id>` |
| `WdCalculator*` 네임스페이스 | 각 모듈 IIFE 패턴 | `window.WdCalculator*` 객체에 부착; **이름 변경은 same-batch bridge + removal plan 없으면 금지**(계획 §2.4) |
| 인라인 partial | `wdcalculator_scripts.html` | `WdCalculatorEstimatesEarlyHostBootstrap`, `WdCalculatorProductsEditingHostBootstrap` 등 **호스트가 런타임 조립** — 수령 시 host 파일 retire와 동기 |

### Globals inventory (non-exhaustive — authoritative는 repo grep)

`shared.js`: `syncWdCalculatorViewportLayout`, `requestWdCalculatorLayoutSync`, `ceilToTens`, `computeAutoPrice1cmFrom30cm`, `generateEstimateId`, `isSameId`, `normalizeId`, `formatPrice`, `parsePrice`, `escapeHtml`, `formatNumber`.

기타: 각 파일별 `window.WdCalculator…` 및 `wdcCompute*` (위 수학 진입점).

## Authoritative four-chunk map (W5-B1 locks)

| Canonical chunk | Target file | 역할 요약 | W5-B2…B5 실행 batch |
|-----------------|-------------|-----------|---------------------|
| `composition` | `static/js/wdcalculator/composition.js` | bootstrap / host orchestration / startup·terminal / sidebar shell / catalog·coupon search·loading·notes·post-mutation·products-editing·estimates-early·totals-terminal **밴드 수령** | **W5-B2** |
| `primary-form` | `static/js/wdcalculator/primary-form.js` | base components, notes UI, coupon helpers, additional options, catalog UI, add/calculate 버튼 | **W5-B3** |
| `estimate-lifecycle` | `static/js/wdcalculator/estimate-lifecycle.js` | sidebar list, search/render, load/save/add, state shards, URL, mutation bridge, order match | **W5-B4** |
| `pricing-core` | `static/js/wdcalculator/pricing-core.js` | current estimate math, totals, resolvers, orchestration, aggregate display, coupon/shipping wiring | **W5-B5** |

**`composition` first executable chunk — lock detail**

- **Merge sources (현재 파일 → `composition.js`로 수령 예정):** `early-bootstrap.js`, `late-bootstrap.js`, `startup-init.js`, `terminal-init.js`, `sidebar-bootstrap.js`, `primary-ui-bootstrap.js`, `catalog-buttons-bootstrap.js`, `coupon-search-render-bootstrap.js`, `loading-database-bootstrap.js`, `notes-ui-bootstrap.js`, `post-mutation-ui-bootstrap.js`, `products-editing-bootstrap.js`, `estimates-early-bootstrap.js`, `totals-startup-terminal-bootstrap.js` (총 14).
- **Retire-later (host-bootstrap band — wrapper 청산 대상, 신규 추가 금지):** `catalog-buttons-host-bootstrap.js`, `coupon-search-render-host-bootstrap.js`, `loading-database-host-bootstrap.js`, `notes-ui-host-bootstrap.js`, `post-mutation-ui-host-bootstrap.js`, `products-editing-host-bootstrap.js`, `estimates-early-host-bootstrap.js`, `totals-startup-terminal-host-bootstrap.js` (총 8).

## Current file disposition matrix (`static/js/wdcalculator/*.js` 전체 56)

> 분류: `keep` \| `merge-into-composition` \| `merge-into-primary-form` \| `merge-into-estimate-lifecycle` \| `merge-into-pricing-core` \| `retire-later`  
> §2.4 예시 목록이 아닌 **파일 단위 sweep** 결과.

| # | File | Disposition | Notes |
|---|------|-------------|-------|
| 1 | `add-estimate.js` | merge-into-estimate-lifecycle | |
| 2 | `add-option-button.js` | merge-into-primary-form | |
| 3 | `additional-options-ui.js` | merge-into-primary-form | |
| 4 | `base-components-ui.js` | merge-into-primary-form | |
| 5 | `calculate-button.js` | merge-into-primary-form | |
| 6 | `calculation-resolvers.js` | merge-into-pricing-core | `wdcCompute*` 의존 |
| 7 | `catalog-buttons-bootstrap.js` | merge-into-composition | |
| 8 | `catalog-buttons-host-bootstrap.js` | retire-later | host pair |
| 9 | `coupon-display-helpers.js` | merge-into-primary-form | |
| 10 | `coupon-search-render-bootstrap.js` | merge-into-composition | |
| 11 | `coupon-search-render-host-bootstrap.js` | retire-later | host pair |
| 12 | `coupon-shipping-wiring.js` | merge-into-pricing-core | |
| 13 | `current-database-estimate-id.js` | merge-into-estimate-lifecycle | |
| 14 | `current-estimate-math.js` | merge-into-pricing-core | `wdcComputeCurrentEstimateMath` |
| 15 | `current-estimate-orchestration.js` | merge-into-pricing-core | |
| 16 | `early-bootstrap.js` | merge-into-composition | |
| 17 | `editing-estimate-id.js` | merge-into-estimate-lifecycle | |
| 18 | `estimate-list-events.js` | merge-into-estimate-lifecycle | |
| 19 | `estimate-mutation-bridge.js` | merge-into-estimate-lifecycle | |
| 20 | `estimate-totals.js` | merge-into-pricing-core | `wdcComputeAggregateTotals` |
| 21 | `estimates-early-bootstrap.js` | merge-into-composition | |
| 22 | `estimates-early-host-bootstrap.js` | retire-later | host pair |
| 23 | `estimates-state.js` | merge-into-estimate-lifecycle | |
| 24 | `late-bootstrap.js` | merge-into-composition | |
| 25 | `layout-sync-wiring.js` | **keep** | 레이아웃 동기화; config 상단 고정 로드 |
| 26 | `load-estimate-to-input-form.js` | merge-into-estimate-lifecycle | |
| 27 | `load-saved-estimate-to-form.js` | merge-into-estimate-lifecycle | |
| 28 | `loading-database-bootstrap.js` | merge-into-composition | |
| 29 | `loading-database-host-bootstrap.js` | retire-later | host pair |
| 30 | `loading-state.js` | merge-into-estimate-lifecycle | |
| 31 | `notes-ui-bootstrap.js` | merge-into-composition | |
| 32 | `notes-ui-host-bootstrap.js` | retire-later | host pair |
| 33 | `notes-ui.js` | merge-into-primary-form | |
| 34 | `order-match-ui.js` | merge-into-estimate-lifecycle | |
| 35 | `post-mutation-ui-bootstrap.js` | merge-into-composition | |
| 36 | `post-mutation-ui-host-bootstrap.js` | retire-later | host pair |
| 37 | `primary-ui-bootstrap.js` | merge-into-composition | §2.4와 정합; primary-form과 경계는 수령 시 단일 오너로 정리 |
| 38 | `product-catalog-ui.js` | merge-into-primary-form | |
| 39 | `products-editing-bootstrap.js` | merge-into-composition | |
| 40 | `products-editing-host-bootstrap.js` | retire-later | host pair |
| 41 | `products-state.js` | merge-into-estimate-lifecycle | |
| 42 | `refresh-after-save.js` | merge-into-estimate-lifecycle | |
| 43 | `render-estimates-list.js` | merge-into-estimate-lifecycle | |
| 44 | `reset-input-form-keep-customer.js` | merge-into-estimate-lifecycle | |
| 45 | `save-estimate.js` | merge-into-estimate-lifecycle | |
| 46 | `search-results-load.js` | merge-into-estimate-lifecycle | |
| 47 | `shared.js` | **keep** | 전역 유틸·레이아웃; 타 chunk가 의존 |
| 48 | `sidebar-bootstrap.js` | merge-into-composition | |
| 49 | `sidebar-estimates.js` | merge-into-estimate-lifecycle | `initWdCalculatorSidebarEstimates` 등 |
| 50 | `startup-init.js` | merge-into-composition | |
| 51 | `terminal-init.js` | merge-into-composition | |
| 52 | `total-estimates-display.js` | merge-into-pricing-core | |
| 53 | `totals-startup-terminal-bootstrap.js` | merge-into-composition | |
| 54 | `totals-startup-terminal-host-bootstrap.js` | retire-later | host pair |
| 55 | `unsaved-exit-guard.js` | **keep** | 이탈 가드; config 상단 |
| 56 | `url-bootstrap.js` | merge-into-estimate-lifecycle | `estimate_id` query contract |

**요약 카운트:** keep 3 \| merge-into-composition 14 \| merge-into-primary-form 7 \| merge-into-estimate-lifecycle 18 \| merge-into-pricing-core 6 \| retire-later 8 → **56**.

## Local README coverage note

- `static/js/wdcalculator/README.md`에 chunk map, 로드 순서 포인터, merge/retire 방향, 금지 패턴을 반영했는지: **예** (동일 commit에서 생성·갱신).

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | four-chunk map + contract 표가 단일 SoT |
| 2 | yes | host-bootstrap는 retire-later로 청산 방향 고정 |
| 3 | yes | delete/merge/extend/add 순서로 disposition matrix에 사전 반영; W5-B2~에서 실행 |
| 4 | yes | canonical target은 네 파일(`composition.js` 등)이 최종 유지보수 단위 |
| 5 | yes | README + run record만 추가; product 런타임 JS 미변경 |
| 6 | N/A | 순증가 파일 없음 |
| 7 | yes | README가 chunk·retire를 반영 |
| 8 | yes | matrix가 재실행 시에도 재현 가능 |
| 9 | yes | shell/layout 미포함 |
| 10 | yes | 문서·README만; 동작 변경 없음 |

## Verification

| 검사 | 결과 |
|------|------|
| docs + README consistency | run record ↔ README 상호 참조 완료 |
| `static/js/wdcalculator/*.js` 56개 모두 matrix에 등장 | **예** |
| `python -c "import app; print('APP_OK')"` | **PASS** (2026-04-14 세션) |
| `python tools/harness/verify_result.py --json` | **PASS** `success: true` |
| Focused automated subset (Node contract) | `node tests/support/wdcalculator_layout_sync_wiring_contract_node_checks.js` — PASS; `node tests/support/wdcalculator_unsaved_exit_guard_contract_node_checks.js` — PASS; `node tests/support/wdcalculator_calculation_resolvers_contract_node_checks.js` — PASS (cross-cutting keep + pricing-core resolver 진입점) |
| Manual smoke | **N/A** — 본 batch는 런타임 JS/템플릿 미변경; `/wdcalculator` 스모크는 W5-B2~에서 |

## product / wrapper / test delta

| 구분 | delta |
|------|-------|
| product (`static/js/wdcalculator/*.js`) | 변경 없음 (contract만 고정) |
| wrapper (template) | 변경 없음 |
| test | 변경 없음 |
| docs | 본 run record + `README.md` |

## Changes made

- `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md` (본 파일)
- `static/js/wdcalculator/README.md`
