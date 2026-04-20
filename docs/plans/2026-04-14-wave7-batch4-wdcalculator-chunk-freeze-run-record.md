# Wave 7 Batch W7-B4 — WDCalculator chunk-contract freeze

> **batch ID:** W7-B4  
> **risk axis:** docs  
> **실행일:** 2026-04-14  
> **상위 계획:** `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md` §5.5

## 1. W5-B1 ownership boundary (locked)

| Chunk | Owner modules (product) | Wave 7 second pilot |
|-------|-------------------------|---------------------|
| **primary-form** | `base-components-ui`, `notes-ui`, `coupon-display-helpers`, `additional-options-ui`, `product-catalog-ui`, `add-option-button`, `calculate-button` | **in scope** (Node checks for these bands) |
| **pricing-core** | `current-estimate-orchestration`, `calculation-resolvers`, `current-estimate-math`, `estimate-totals`, `total-estimates-display`, `coupon-shipping-wiring` | **out of scope** — defer |

## 2. `tests/test_wdcalculator_product_settings.py` — read-and-classify

| Question | Result |
|----------|--------|
| `composition` + `primary-form` only sufficient? | **No** — asserts script tag order for `estimate-totals.js`, `current-estimate-math.js`, `calculation-resolvers.js`, `current-estimate-orchestration.js`, and multiple `WdCalculatorCurrentEstimateOrchestration.configure` blocks. |
| **Continued-use justification** | **Yes** — integration/regression for full `wdcalculator_scripts_config.html` load order and orchestration wiring; not replaceable without duplicating pricing-core coverage or editing product templates (frozen). |
| Replacement smoke path | **None** — not required; B5 verification uses this file as-is per plan §5.6 step 6. |

## 3. File budget (B5 target — locked)

| Path | Role |
|------|------|
| `tests/contracts/wdcalculator/_node_runner.py` | Shared Node subprocess runner (optional, ≤1) |
| `tests/contracts/wdcalculator/test_composition_contracts.py` | Parametrized composition-band checks |
| `tests/contracts/wdcalculator/test_primary_form_contracts.py` | Parametrized primary-form-band checks |
| `tests/support/wdcalculator/composition_contract_checks.js` | **Not used** — physical checks remain in existing `*_contract_node_checks.js` files; runner-shared-first at **pytest** layer per TR5 |

## 4. Micro pair classification (53 → 37 merge + 16 defer)

### 4.1 Merge into `test_composition_contracts.py` (26 scripts)

`tests/support/wdcalculator_*` paths listed in `test_composition_contracts.py::_COMPOSITION_SCRIPTS`.

### 4.2 Merge into `test_primary_form_contracts.py` (11 scripts)

Paths listed in `test_primary_form_contracts.py::_PRIMARY_FORM_SCRIPTS`.

### 4.3 Defer — **estimate-lifecycle / pricing-core / mutation / state** (16 pairs)

Keep legacy **pytest + support** pair until later wave (product prerequisite or Wave 5 follow-up):

- `calculation_resolvers`, `coupon_shipping_wiring`, `order_match`
- `load_saved_estimate_to_form`, `estimate_mutation_bridge`, `current_estimate`, `refresh_after_save`
- `current_database_estimate_id`, `calculate_total_estimates`, `save_estimate`, `unsaved_exit_guard`
- `products_state`, `add_estimate`, `editing_estimate_id`, `load_estimate_to_input_form`, `reset_input_form_keep_customer`

## 5. Exact removal list (pytest wrappers only — B5 executed)

**37 files deleted** (same names as former `test_wdcalculator_*_contract_node.py` for merged bands).  
**Support JS:** **retained** — still executed by parametrized chunk tests (no loss of Node coverage).

## 6. `node` snapshot

`node --version` → **v20.19.5** (session)

## 7. Branch / stop

**No `wdcalculator-freeze-stop`** — removal list does not require `pricing-core` product edits; `test_wdcalculator_product_settings.py` justified; B5 opened.

## 8. Next legal batch

**`W7-B5`**

## 9. Direction Lock (10문항)

| # | Y/N |
|---|-----|
| 1–7 | **Y** (docs-only; pilot boundary respected) |
| 8 | **Y** (node recorded) |
| 9 | README updated in B5 |
| 10 | next = W7-B5 |
