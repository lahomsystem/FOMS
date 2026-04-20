# Wave 5 Batch W5-B5 — WDCalculator `pricing-core` canonicalization

> **batch ID:** W5-B5  
> **lane:** WDCalculator — `pricing-core`  
> **실행일:** 2026-04-14  
> **선행:** W5-B4 complete / `estimate-lifecycle` canonicalized

## Scope lock

- `current-estimate math`, `aggregate totals`, `resolver`, `current-estimate orchestration`, `total estimates display`, `coupon/shipping recalculation wiring`만 canonicalize 한다.
- product meaning, coupon/shipping rule, displayed numeric contract, public global names는 바꾸지 않는다.
- `primary-form` owner set과 lifecycle owner set을 다시 건드리지 않는다.

## Inputs consumed

- `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md`
- `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
- `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md`
- `docs/plans/2026-04-14-wave5-batch4-wdcalculator-estimate-lifecycle-run-record.md`
- `static/js/wdcalculator/README.md`
- live tree: `templates/wdcalculator/partials/wdcalculator_scripts_config.html`, `static/js/wdcalculator/*`, `tests/support/wdcalculator_*`

## Context normalization keys

- `registry lane:` `wdcalculator-pricing-core`
- `spec domain:` Wave 5 large front-end island mainline continuation
- `FR20 context key:` `static/js/wdcalculator/README.md` pricing slot/load-order refresh

## Contract table

| Contract | Freeze |
|----------|--------|
| public script path | `js/wdcalculator/pricing-core.js` |
| retained globals | `window.wdcComputeCurrentEstimateMath`, `window.wdcComputeAggregateTotals`, `window.WdCalculatorCalculationResolvers`, `window.WdCalculatorCurrentEstimateOrchestration`, `window.WdCalculatorTotalEstimatesDisplay`, `window.WdCalculatorCouponShippingWiring` |
| load order | `shared.js` → `unsaved-exit-guard.js` → `layout-sync-wiring.js` → `composition.js` → `estimate-lifecycle.js` → `primary-form.js` → `pricing-core.js` |
| numeric semantics | base/option/current/aggregate total calculation meaning 유지 |
| orchestration boundary | pricing-core reads host state but does not expand API/domain scope |

## FR19 decision

`delete → merge → extend → add` 적용.

1. 기존 pricing micro source 6개를 모두 retire 후보로 잠갔다.
2. `primary-form.js`나 `estimate-lifecycle.js`로 흡수하면 owner boundary가 흐려져 token 효율이 오히려 악화된다고 판단했다.
3. 따라서 **`pricing-core.js` 한 개만** canonical target으로 신설하고, 기존 6개 파일과 5개 thin pytest wrapper는 same-batch 제거했다.

## Changes made

- `static/js/wdcalculator/pricing-core.js` 생성: 6개 pricing/totals/orchestration band를 한 파일에 병합.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html` 수정: 6개 개별 `<script src>` 제거 후 `pricing-core.js` 1회 로드.
- `static/js/wdcalculator/README.md` 수정: pricing-core chunk, global helper source, public order 반영.
- `tests/support/wdcalculator_*_contract_node_checks.js` 5개 수정: canonical source를 `pricing-core.js`로 통일.
- `tests/support/wdcalculator_calculation_resolvers_contract_node_checks.js` 수정: resolver harness가 chunk load 후 helper stub를 override하도록 교정.
- `tests/contracts/wdcalculator/test_pricing_core_contracts.py` 생성: pricing-core chunk suite 추가.
- `tests/test_wdcalculator_product_settings.py` 수정: pricing-core load-order 및 retired script absence 검증 추가.
- `tests/README.md` 수정: pricing-core canonicalization, defer micro-pair count `1` 반영.

## Delta registers

| Register | 내용 |
|----------|------|
| **product file delta** | `pricing-core.js` 추가(+1), pricing micro source 6개 제거(-6), net **-5** |
| **wrapper file delta** | 신규 wrapper **0**; legacy pytest thin wrappers 5개 제거 |
| **test file delta** | chunk suite `tests/contracts/wdcalculator/test_pricing_core_contracts.py` 추가(+1), support check scripts 5개는 수정만 수행 |
| **canonical target** | `static/js/wdcalculator/pricing-core.js` |
| **removal / merge target** | `current-estimate-math.js`, `estimate-totals.js`, `calculation-resolvers.js`, `current-estimate-orchestration.js`, `total-estimates-display.js`, `coupon-shipping-wiring.js` |
| **retirement wave / removal condition** | W5-B5 same-batch 청산 완료. 템플릿이 위 6개 script path를 더 이상 로드하지 않고 chunk suite가 green이면 종료 |
| **README update 여부** | yes |

## Verification

| 단계 | 명령 / 범위 | 결과 |
|------|-------------|------|
| 앱 import | `python -c "import app; print('APP_OK')"` | APP_OK |
| Harness | `python tools/harness/verify_result.py --json` | success |
| Focused automated | `python -m pytest tests/test_wdcalculator_product_settings.py tests/contracts/wdcalculator/test_composition_contracts.py tests/contracts/wdcalculator/test_primary_form_contracts.py tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py tests/contracts/wdcalculator/test_pricing_core_contracts.py -q` | **79 passed** |
| lint / diagnostics | edited files `ReadLints` | no linter errors found |
| equivalent regression evidence | render/load-order test + pricing/current-estimate/totals/coupon-shipping Node chunk contracts | pass |

**Verification note:** resolver Node harness initially failed because the old test assumed pre-chunk helper stubbing. The support script was corrected so stubs are bound after `pricing-core.js` loads, then the full W5 focused suite was rerun to green.

## Direction Lock answers

1. **Yes** — pricing owner를 `pricing-core.js` 하나로 축소했다.
2. **Yes** — duplicate math/totals script loading 경로를 제거했다.
3. **Yes** — canonical file 1개 외 새 wrapper/bridge를 만들지 않았다.
4. **Yes** — pricing/totals/orchestration를 묶는 가장 큰 유지보수 가능 chunk로 정리했다.
5. **Yes** — product/wrapper/test 총량이 순감했다.
6. **Yes** — 추가된 테스트는 chunk suite 1개뿐이고 thin wrappers는 즉시 제거했다.
7. **Yes** — local README와 tests README 둘 다 갱신했다.
8. **Yes** — post-W5 남은 WDCalculator defer micro-pair를 `unsaved-exit-guard` 1개로 줄였다.
9. **Yes** — `primary-form` / `estimate-lifecycle` / `pricing-core` owner boundary가 더 선명해졌다.
10. **Yes** — 기능 의미 변경 없이 구조 canonicalization만 수행했다.

## Drift / stop / defer decision

- stop condition 없음.
- 신규 drift 없음.
- next legal batch: **W5-B6 shared ERP island lock**.

## Outcome

**PASS — W5-B5 complete. Large front-end island mainline may proceed to W5-B6.**
