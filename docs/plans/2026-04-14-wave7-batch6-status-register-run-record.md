# Wave 7 Batch W7-B6 — Test status register

> **batch ID:** W7-B6  
> **실행일:** 2026-04-14  
> **branch:** `Branch A` (full mainline completed through B5)

## Authoritative register

| Family | contract tier | queue class | execution state | bridge-coupled | Wave 8 owner | continuation owner | micro-pair delta | why not now / prep | suggested restart |
|--------|---------------|-------------|-----------------|----------------|--------------|---------------------|------------------|---------------------|-------------------|
| runtime-anchor | runtime anchor | mainline-pilot | **completed** | no | **N/A** | tests/docs maintainer | giant → thin agg + `foms_namespace_surface_tests` | — | — |
| wdcalculator-composition-primary-form | chunk contract | mainline-pilot | **completed** (chunk tests + 37 wrapper removal) | no | **N/A** | Wave 5 product + tests | −37 pytest wrappers; +2 parametrized modules | defer 16 pairs need estimate-lifecycle/pricing prep | W5-B4+ or Wave 7 continuation after W5 chunks stable |
| wdcalculator-estimate-lifecycle-pricing-core | chunk contract | active-product-coupled defer | **not started** (16 pairs remain) | no | **N/A** | Wave 5 + tests | 16× 1:1 pair unchanged | W5-B4 estimate-lifecycle not done; pricing-core churn | After W5-B4/B5 product + freeze |
| harness | harness contract | already aligned precedent | reference only | no | **N/A** | harness maintainer | 0 | Wave 7 scope | — |
| measurement-contract-family | domain contract | high-risk suite defer | not started | no | **N/A** | future domain wave | — | scope | — |
| orders-api-bridge-family | domain contract | bridge-coupled defer | not started | **yes** | **Wave 8 bridge retirement** | domain + platform | — | needs bridge removal | Wave 8 planning |

## Notes

- **`Wave 8 owner`** populated only for `orders-api-bridge-family` (bridge-coupled yes).
- Defer **16** WDCalculator micro pairs: see `docs/plans/2026-04-14-wave7-batch4-wdcalculator-chunk-freeze-run-record.md` §4.3.

## Direction Lock

All **Y** for docs-only batch; next = **W7-B7**.
