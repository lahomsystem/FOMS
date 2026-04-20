# Wave 7 Batch W7-B2 — Runtime anchor contract freeze

> **batch ID:** W7-B2  
> **risk axis:** docs (+ README supplement)  
> **실행일:** 2026-04-14  
> **상위 계획:** `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md` §5.3  
> **git HEAD (pre-B3):** `ca144560a4e4e68954c18402bc67a95b4b486793`

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `tests/README.md` (runtime anchor section) | runtime anchor **test code** (B3 전용) |
| 본 run record | new domain/harness pilot |

## 2. Current `tests/test_foms_namespace_imports.py` surface classification

Live evidence (grep `^def test_`): **140** test functions.

| Surface | Description | Examples (non-exhaustive) |
|---------|-------------|---------------------------|
| **A. Service namespace parity** | Legacy `services.*` vs `foms.services.*` shims: `__all__`, identity of callables | `test_legacy_*_shim_preserves_canonical_contract`, channel/erp/helper pairs |
| **B. Persistence parity** | `foms.persistence.main` DB/models vs `db` / `models` legacy | `test_namespaced_db_reexports_legacy_contract`, `test_namespaced_models_reexport_legacy_classes` |
| **C. Packaged import-surface / jobs / policy** | `services.jobs.*`, `erp_policy` data paths, app binding to canonical imports | `test_app_uses_canonical_*`, `test_erp_automation_uses_canonical_erp_policy_import` |
| **D. Consumer binding / lazy import inspection** | `inspect.getsource` on apps/api for canonical import strings | `test_erp_orders_drawing_uses_canonical_*`, `test_erp_display_lazy_callers_use_canonical_import_paths` |
| **E. Thin template / blueprint shim (Wave 4)** | Template path existence, `extends` only wrappers | `test_cs_completion_dashboard_template_path_exists`, `test_legacy_erp_completion_dashboard_is_thin_extends_wrapper` |

All of the above remain **runtime anchor** tier (not domain regression suites); they preserve **legacy-vs-canonical** parity and public import contracts.

## 3. `tests/test_app_bootstrap_contract.py` — freeze decision

| Decision | **Keep as separate file** |
|----------|---------------------------|
| Rationale | Already minimal (~36 lines, 4 tests); distinct concern (root `app` public exports); no merge required for clarity. |
| B3 action | **No structural merge** into `test_foms_namespace_imports.py`; stays sibling runtime-anchor file. |

## 4. Frozen target shape (B3 must follow exactly)

| Artifact | Role | Budget |
|----------|------|--------|
| `tests/contracts/runtime/test_foms_namespace_surface.py` | **Substantive:** hosts all current body of `test_foms_namespace_imports.py` (imports + 140 tests) | **1** substantive file |
| `tests/test_foms_namespace_imports.py` | **Thin compatibility aggregator:** stable CLI path `pytest tests/test_foms_namespace_imports.py`; re-exports tests for discovery | **≤ ~80 lines** (target) |
| `tests/contracts/__init__.py`, `tests/contracts/runtime/__init__.py` | Package markers for `tests.contracts.runtime` | minimal |
| `tests/fixtures/*` shared matrix | **Optional:** only if B3 finds unavoidable duplication; **max 1** helper file | default **omit** |

**Not allowed in B3 without new freeze:** a **second** substantive runtime-anchor file beyond the one listed above (unless same-batch run record documents split and still satisfies TR9).

## 5. Runtime-anchor family file-count rule (TR9)

| Before B3 | After B3 (planned) |
|-----------|---------------------|
| `test_foms_namespace_imports.py` (1 giant) + `test_app_bootstrap_contract.py` (1) = **2** files | `test_foms_namespace_imports.py` (thin) + `test_foms_namespace_surface.py` (1 substantive) + `test_app_bootstrap_contract.py` (1) = **3** files |

**Net change:** **+1** file vs pre-Wave-7 family count.

**Classification:** **TR9 exceptional +1 allowance** — giant file replaced by thin aggregator (≤80 lines target) + single substantive module; **no** new `tests/support` net growth; helper matrix **absent by default**.

## 6. Parity preservation evidence strategy (B3)

1. **No deletion** of `test_*` functions; **move** only (same assertions, same legacy vs namespaced checks).
2. **pytest entrypoint preserved:** `pytest tests/test_foms_namespace_imports.py` still collects **140** tests via aggregator re-export.
3. **Full anchor command unchanged:** `pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q` must remain **143 passed** (140 + 3 bootstrap).
4. Post-move: `ReadLints` on touched files.

## 7. Frozen stop rules (trigger `runtime-anchor-freeze-stop` if B3 cannot close without)

- Legacy-vs-canonical parity assertion **must shrink** to go green
- `services/` / `apps/` / `foms/` **source** edit required
- Bridge retirement **assumption** required to delete assertions

**None of these are anticipated** at B2 freeze time; B3 proceeds on **Branch A**.

## 8. Product / wrapper / test / docs delta (B2 only)

| 구분 | delta |
|------|-------|
| product | none |
| wrapper | none |
| test | none |
| docs | 본 run record; `tests/README.md` runtime anchor subsection (supplement) |

## 9. Verification (B2 — docs)

- README runtime anchor section: target file names + TR9 net + stop rules **present**
- Target file budget: **explicit** in README + 본 문서 §4

## 10. Next legal batch

**`W7-B3`** — `docs/plans/2026-04-14-wave7-batch3-runtime-anchor-rationalization-run-record.md`

## 11. Branch label

**`Branch A`**

## 12. Direction Lock (10문항)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | product 미수정 |
| 2 | **Y** | bridge retirement 미시도 |
| 3 | **Y** | parity 축소 금지 명시 |
| 4 | **Y** | micro pair N/A |
| 5 | **Y** | single substantive + thin agg |
| 6 | **Y** | tier runtime anchor only |
| 7 | **Y** | WDC 미건드림 |
| 8 | **Y** | Node N/A (B2) |
| 9 | **Y** | README 보강 예정 |
| 10 | **Y** | next = W7-B3 |
