# Wave 7 Batch W7-B5 — WDCalculator composition + primary-form rationalization

> **batch ID:** W7-B5  
> **risk axis:** tests + README  
> **실행일:** 2026-04-14  
> **상위 계획:** `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md` §5.6

## 1. Product / wrapper / test delta

| 구분 | delta |
|------|-------|
| product | none |
| wrapper | none |
| test | **Added:** `tests/contracts/wdcalculator/__init__.py`, `_node_runner.py`, `test_composition_contracts.py`, `test_primary_form_contracts.py` |
| test | **Removed:** 37× `tests/test_wdcalculator_*_contract_node.py` (exact list = B4 §5 merge targets) |
| test | **Retained:** 16× defer `test_wdcalculator_*_contract_node.py` + all 53 `tests/support/wdcalculator_*_contract_node_checks.js` |

## 2. Micro-pair delta

| Metric | Before | After |
|--------|--------|-------|
| `test_wdcalculator_*_contract_node.py` | 53 | **16** |
| Chunk contract entrypoints | 0 | **2** (`test_composition_contracts`, `test_primary_form_contracts`) + **1** runner |

**Net pytest file reduction:** 53 − 37 − 3 + 0 = **+13** new − 37 removed = **−24** test modules net?  
Actually: removed 37, added 3 → **−34** `.py` files under `tests/` root for this family; defer 16 remain.

## 3. Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `python tools/harness/verify_result.py --json` | success: true |
| `python -m pytest tests/contracts/wdcalculator/test_composition_contracts.py tests/contracts/wdcalculator/test_primary_form_contracts.py -q` | **37 passed** |
| `python -m pytest tests/test_wdcalculator_product_settings.py -q` | **26 passed** |
| `python -m pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q` | **143 passed** |
| `node --version` | v20.19.5 |
| `python -m pytest tests --collect-only -q` | inherited-red: `safe_schema_migration` missing; **549 tests collected** |

## 4. Defer register (16)

Same as B4 §4.3 — still using 1:1 micro pair until estimate-lifecycle/pricing-core wave.

## 5. Branch label

**`Branch A`**

## 6. Direction Lock (10문항)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | product 미수정 |
| 2 | **Y** | bridge 미조기 |
| 3 | **Y** | Node assertions 동일 스크립트 경로 |
| 4 | **Y** | 새 1:1 pair 미추가 |
| 5 | **Y** | −37 wrapper, 증가 이유 = chunk parametrization |
| 6 | **Y** | tier chunk only |
| 7 | **Y** | composition + primary-form only |
| 8 | **Y** | node 기록 |
| 9 | **Y** | README B5 반영 |
| 10 | **Y** | next = W7-B6 |

## 7. Next legal batch

**`W7-B6`**
