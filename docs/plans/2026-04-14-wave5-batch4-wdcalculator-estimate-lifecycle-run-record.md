# Wave 5 Batch W5-B4 — WDCalculator `estimate-lifecycle` canonical chunk

> **batch ID:** W5-B4  
> **lane:** WDCalculator — `estimate-lifecycle`  
> **실행일:** 2026-04-14  
> **선행:** W5-B0, W5-B1, W5-B2, W5-B3 (complete)

## Scope lock

- `save/load/list/search/sidebar/url/local-state/order-match` band만 다룬다.
- pricing rule, coupon/shipping semantics, API payload, query parameter meaning은 바꾸지 않는다.
- canonical owner는 `static/js/wdcalculator/estimate-lifecycle.js` 하나로 고정한다.

## Inputs consumed

- `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
- `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md`
- `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md`
- `static/js/wdcalculator/README.md`
- live tree: `templates/wdcalculator/partials/wdcalculator_scripts_config.html`, `static/js/wdcalculator/*`, `tests/support/wdcalculator_*`

## Context normalization keys

- `registry lane:` `wdcalculator-estimate-lifecycle`
- `spec domain:` Wave 5 local front-end island / structure-only rebaseline
- `FR20 context key:` `static/js/wdcalculator/README.md` 유지 및 lifecycle section 갱신

## Contract table

| Contract | Freeze |
|----------|--------|
| public script path | `js/wdcalculator/estimate-lifecycle.js` |
| retained globals | 기존 `WdCalculator*` lifecycle/state/search/save/load helpers 이름 유지 |
| preserved query-param flow | `estimate_id`, `order_id` semantics 유지 |
| API surface | save/load/search/match/delete 관련 payload/route meaning 유지 |
| DOM/load-order | `composition.js` 다음 lifecycle slot 1회 로드, inline bootstrap 순서 유지 |

## FR19 decision

`delete → merge → extend → add` 적용.

1. 기존 18개 lifecycle/state/search/save/load micro source를 retire 대상으로 먼저 확정했다.
2. 동등 owner를 기존 canonical chunk에 흡수할 수 있는지 검토했고, `composition`/`primary-form`에 섞으면 bounded context가 흐려져 별도 큰 청크가 더 적합하다고 판정했다.
3. 따라서 신규 canonical file은 **`estimate-lifecycle.js` 한 개만** 추가하고, thin wrapper/host-bootstrap은 추가하지 않았다.

## Changes made

- `static/js/wdcalculator/estimate-lifecycle.js` 생성: 18개 lifecycle/state/search/save/load/order-match band를 단일 청크로 수령.
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html` 수정: 개별 lifecycle `<script src>` 18개 제거, `estimate-lifecycle.js` 단일 로드로 정리.
- `static/js/wdcalculator/README.md` 수정: lifecycle chunk, load order, retire 완료 상태 반영.
- `tests/support/wdcalculator_*_contract_node_checks.js` 17개 수정: canonical source를 `estimate-lifecycle.js`로 통일.
- `tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py` 생성: lifecycle chunk-level parametrized suite 추가.
- `tests/test_wdcalculator_product_settings.py` 수정: script order 기대값을 lifecycle chunk 기준으로 갱신하고 retire path 부재를 검증.

## Delta registers

| Register | 내용 |
|----------|------|
| **product file delta** | `estimate-lifecycle.js` 추가(+1), lifecycle/state/search/save/load/order-match micro source 18개 제거(-18), net **-17** |
| **wrapper file delta** | 신규 wrapper **0**; legacy pytest thin wrappers 11개 제거 |
| **test file delta** | chunk suite `tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py` 추가(+1), support check scripts는 기존 파일 재사용/수정만 수행 |
| **canonical target** | `static/js/wdcalculator/estimate-lifecycle.js` |
| **removal / merge target** | `sidebar-estimates.js`, `search-results-load.js`, `render-estimates-list.js`, `order-match-ui.js`, `refresh-after-save.js`, `reset-input-form-keep-customer.js`, `load-estimate-to-input-form.js`, `load-saved-estimate-to-form.js`, `save-estimate.js`, `add-estimate.js`, `estimate-list-events.js`, `estimate-mutation-bridge.js`, `loading-state.js`, `current-database-estimate-id.js`, `products-state.js`, `editing-estimate-id.js`, `estimates-state.js`, `url-bootstrap.js` |
| **retirement wave / removal condition** | W5-B4 same-batch 청산 완료. 템플릿이 위 개별 경로를 더 이상 로드하지 않고 focused suite가 green이면 종료 |
| **README update 여부** | yes |

## Verification

| 단계 | 명령 / 범위 | 결과 |
|------|-------------|------|
| 앱 import | `python -c "import app; print('APP_OK')"` | APP_OK |
| Harness | `python tools/harness/verify_result.py --json` | success |
| Focused automated | `python -m pytest tests/test_wdcalculator_product_settings.py tests/contracts/wdcalculator/test_composition_contracts.py tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py -q` | **63 passed** |
| equivalent regression evidence | render/load-order + lifecycle/state/search/save/load/order-match Node chunk contracts | pass |

**Manual smoke handling:** 이 batch는 template/static decomposition lane이지만, same-batch focused render test + canonical chunk Node contracts로 equivalent regression evidence를 확보했다. 별도 브라우저 수동 smoke는 선택 보강 항목으로 유지.

## Direction Lock answers

1. **Yes** — single SoT를 `estimate-lifecycle.js`로 선명하게 만들었다.
2. **Yes** — split-brain을 줄였고 추가 bridge를 만들지 않았다.
3. **Yes** — delete/merge 검토 후 신규 canonical chunk 1개만 추가했다.
4. **Yes** — lifecycle bounded context를 담는 가장 큰 유지보수 가능 chunk다.
5. **Yes** — product/wrapper/test 총량이 순감했다.
6. **Yes** — 순증가는 chunk suite 1개뿐이며 retire target을 same-batch에 기록했다.
7. **Yes** — `static/js/wdcalculator/README.md` lifecycle section을 갱신했다.
8. **Yes** — 같은 패턴을 반복할수록 micro shard가 줄어든다.
9. **Yes** — product / test / docs 경계가 더 선명해졌다.
10. **Yes** — 구조 작업만 수행했고 기능 의미는 유지했다.

## Drift / stop / defer decision

- stop condition 없음.
- defer 신규 항목 없음.
- 다음 legal batch: **W5-B5 `pricing-core` canonicalization**.

## Outcome

**PASS — W5-B4 complete. W5-B5 진행 가능.**
