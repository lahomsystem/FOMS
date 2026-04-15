# FOMS tests — Wave 7 entrypoint

This directory is the **local authoritative entrypoint** for test taxonomy, contract tiers, and Wave 7 pilot boundaries. For product or deployment truth, use the live tree and `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`.

**Execution runbook:** `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md`

---

## 1. Contract tiers (exactly four)

| Tier | Meaning |
|------|---------|
| **runtime anchor** | Namespace parity, app bootstrap public contract, import-surface smoke. **Files:** `tests/domains/test_foms_namespace_imports.py`, `tests/domains/test_app_bootstrap_contract.py`, and their direct import-surface checks only. No domain regression or bridge retirement here. |
| **chunk contract** | One **canonical product chunk** → one contract surface (`TR1`). Wave 7 mainline pilot은 **WDCalculator `composition` + `primary-form`**였고, live tree에는 W5 후속으로 **`estimate-lifecycle` + `pricing-core` chunk contract**가 추가로 존재한다. |
| **domain contract** | Route/page/service/domain behavior regression (e.g. measurement, orders boundary). Often defer in Wave 7. |
| **harness contract** | `tests/harness/*` locks `tools/harness` **semantics**. Wave 7 does **not** modify `tools/harness/` (already aligned precedent). |

---

## 2. Queue classes

| Queue class | Wave 7 role |
|-------------|-------------|
| **mainline-pilot** | Code batch allowed (tests/docs only; product frozen). |
| **already aligned precedent** | Reference / status only (e.g. `tests/harness/*`). |
| **active-product-coupled defer** | Chunk not ready for test rationalization without product work (live tree currently has no active mainline WDCalculator chunk defer after W5-B5). |
| **bridge-coupled defer** | Strongly tied to Wave 8 bridge retirement; do not rationalize under Wave 7 mainline. |
| **high-risk suite defer** | Broad or cross-domain suites; defer unless explicitly scheduled. |

**Execution state** (per family): `not started` | `partial` | `completed`.

---

## 3. Wave 7 mainline pilots (fixed order)

1. **First pilot — `runtime-anchor`**  
   `tests/domains/test_foms_namespace_imports.py`, `tests/domains/test_app_bootstrap_contract.py` (rationalize structure; **preserve** legacy-vs-canonical parity and bootstrap smoke).

2. **Second pilot — `wdcalculator-composition-primary-form`**  
   Canonical chunks: `static/js/wdcalculator/composition.js`, `static/js/wdcalculator/primary-form.js` (Wave 5 B2/B3 evidence).  
   **In scope:** merge/fold micro pairs into chunk-level contracts per Wave 7 freeze records.  
   **Out of scope for this pilot:** `estimate-lifecycle`, `pricing-core`, measurement expansion, bridge retirement.

3. **Post-pilot live addendum — `wdcalculator-estimate-lifecycle`**  
   Canonical chunk: `static/js/wdcalculator/estimate-lifecycle.js` (Wave 5 B4 evidence).  
   기존 lifecycle/state/save/load/order-match support checks는 canonical source를 `estimate-lifecycle.js`로 읽고, thin pytest wrapper 대신 `tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py` 하나로 수렴한다.

4. **Post-pilot live addendum — `wdcalculator-pricing-core`**  
   Canonical chunk: `static/js/wdcalculator/pricing-core.js` (Wave 5 B5 evidence).  
   기존 pricing/current-estimate/totals/coupon-shipping support checks는 canonical source를 `pricing-core.js`로 읽고, thin pytest wrapper 대신 `tests/contracts/wdcalculator/test_pricing_core_contracts.py` 하나로 수렴한다.

### 3.1 W5-B1 owner boundaries (do not blur)

- **`primary-form` owner set:** `base-components-ui.js`, `notes-ui.js`, `coupon-display-helpers.js`, `additional-options-ui.js`, `product-catalog-ui.js`, `add-option-button.js`, `calculate-button.js`
- **`pricing-core` owner set (Wave 7 second pilot — exclude):** `current-estimate-orchestration.js`, `calculation-resolvers.js`, `current-estimate-math.js`, `estimate-totals.js`, `total-estimates-display.js`, `coupon-shipping-wiring.js`

`add-option-button.js` / `calculate-button.js` belong to **primary-form**, not pricing-core.

---

## 4. Defer families (Wave 7 register; not mainline code pilots)

| Family | Tier | Typical queue class |
|--------|------|------------------------|
| `wdcalculator-unsaved-exit-guard` | chunk contract | active-product-coupled defer |
| `measurement-contract-family` | domain contract | high-risk suite defer |
| `orders-api-bridge-family` | domain contract | bridge-coupled defer |
| Harness expansion / infra | harness contract | already aligned precedent (no Wave 7 harness rewrite) |

---

## 5. Shorthand (TR1–TR9)

| ID | Rule |
|----|------|
| **TR1** | One chunk = one contract surface (no tiny helper per pytest/support pair). |
| **TR2** | `reuse → merge → parameterize → add` (new files last). |
| **TR3** | **anchor-preserve:** runtime anchor work must not shrink legacy-vs-canonical parity coverage. |
| **TR4** | **micro-pair-budget:** new `tests/support/*` + `test_*_contract_node.py` pairs are **by default forbidden**; exceptions need same-batch run record justification. |
| **TR5** | **runner-shared-first:** duplicate Node subprocess wrappers → shared runner / parametrization first. |
| **TR6** | **bridge-aware:** while root `services/` or `apps/` bridges exist, matching legacy-path assertions stay. |
| **TR7** | **tier-lock:** do not mix multiple contract tiers in one file without clear separation. |
| **TR8** | **pilot-cap:** Wave 7 mainline code pilots = **runtime anchor** + **WDCalculator composition + primary-form** only. |
| **TR9** | **family-net-zero:** runtime-anchor rationalization should keep family-level `tests/*.py` count ≤ 0 net; **+1** only with thin aggregator (≈80 lines or less) and no helper/support net growth. |

---

## 6. Target taxonomy vs live tree (important)

**Target taxonomy** (spec / plan direction):

- `tests/contracts/` — chunk/runtime contract modules
- `tests/domains/` — domain suites
- `tests/harness/` — harness contract tests (exists today)
- `tests/fixtures/` — shared fixtures
- `tests/support/` — JS/checks for Node contract tests

**Strict §2.2.1 (2026-04-15):** domain pytest modules are under `tests/domains/*.py` (no `test_*.py` at `tests/` root). Load/k6 assets live under `tests/harness/load/`. `tests/contracts/`, `tests/harness/`, `tests/fixtures/`, `tests/support/` unchanged in role.

---

## 7. Live tree snapshot (Wave 7 closeout — W7-B7)

| Item | Value |
|------|--------|
| `test_wdcalculator_*_contract_node.py` count (defer micro-pairs) | **1** (`unsaved-exit-guard` lane만 잔존) |
| `tests/support/wdcalculator_*_contract_node_checks.js` count | **53** (unchanged; still invoked by parametrized chunk tests or defer wrappers) |
| Chunk parametrized suites | `tests/contracts/wdcalculator/test_composition_contracts.py` (20 scripts), `tests/contracts/wdcalculator/test_primary_form_contracts.py` (11 scripts), `tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py` (17 scripts), `tests/contracts/wdcalculator/test_pricing_core_contracts.py` (5 scripts); runner `tests/contracts/wdcalculator/_node_runner.py` |
| Runtime anchor | Thin `tests/domains/test_foms_namespace_imports.py` re-exports `tests/contracts/runtime/foms_namespace_surface_tests.py` (substantive body; non-`test_*.py` name avoids duplicate collection) |
| `tests/README.md` | **this file** |

**Representative WDCalculator page / settings smoke:** `tests/domains/test_wdcalculator_product_settings.py` — W7-B4 classified as **continued-use** (full script order + orchestration); not composition+primary-form-only.

**SQLite compat:** `tests/domains/test_sqlite_startup_compat.py` loads `scripts/migrations/safe_schema_migration.py` via `sys.path` (strict tree — no top-level `safe_schema_migration` package).

---

## 8. Verification (standard Wave 7 matrix)

Run from repo root (PowerShell; chain with `;`):

```powershell
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
python -m pytest tests/domains/test_foms_namespace_imports.py tests/domains/test_app_bootstrap_contract.py -q
python -m pytest tests --collect-only -q
```

**Node (WDCalculator batches):** `node --version` required; do not rely on skipif-hidden green as mainline success.

---

## 9. Branch labels (plan §3)

- **Branch A:** Full mainline through B7 (when gates pass).
- **Branch B:** Runtime anchor + docs path; WDCalculator code deferred early.
- **Branch C:** Docs-only partial closeout.
- **runtime-anchor-freeze-stop**, **runtime-anchor-b3-revert-stop**, **wdcalculator-freeze-stop**, **wdcalculator-b5-revert-stop:** see Wave 7 plan §3 / §6 — partial closeout to B6/B7, full revert when required.

---

## 10. Batch progress (Wave 7)

| Batch | Status | Notes |
|-------|--------|-------|
| W7-B0 | completed | Readiness gate + queue lock; Branch A; run record: `docs/plans/2026-04-14-wave7-batch0-readiness-gate-run-record.md` |
| W7-B1 | completed | Taxonomy entrypoint (this README); run record: `docs/plans/2026-04-14-wave7-batch1-test-taxonomy-run-record.md` |
| W7-B2 | completed | Runtime anchor contract freeze; run record: `docs/plans/2026-04-14-wave7-batch2-runtime-anchor-freeze-run-record.md` |
| W7-B3 | completed | `foms_namespace_surface_tests` + thin aggregator; run record: `docs/plans/2026-04-14-wave7-batch3-runtime-anchor-rationalization-run-record.md` |
| W7-B4 | completed | Chunk freeze + `test_wdcalculator_product_settings` continued-use; run record: `docs/plans/2026-04-14-wave7-batch4-wdcalculator-chunk-freeze-run-record.md` |
| W7-B5 | completed | composition + primary-form parametrization; −37 pytest wrappers; run record: `docs/plans/2026-04-14-wave7-batch5-wdcalculator-chunk-contracts-run-record.md` |
| W7-B6 | completed | Status register; run record: `docs/plans/2026-04-14-wave7-batch6-status-register-run-record.md` |
| W7-B7 | completed | Closeout + Wave 8 handoff; run record: `docs/plans/2026-04-14-wave7-batch7-closeout-run-record.md` |

**Closeout:** Branch A full mainline through B7. **Current after W5-B5:** `estimate-lifecycle` + `pricing-core` chunk suites added, lifecycle/pricing thin wrappers retired. **Next:** Wave 5 **W5-B6 shared ERP island lock**; **Wave 8** bridge retirement planning; optional continuation for remaining **1** defer micro-pair after product mainline closeout.
