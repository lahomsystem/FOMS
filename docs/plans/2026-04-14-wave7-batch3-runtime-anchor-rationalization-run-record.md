# Wave 7 Batch W7-B3 — Runtime anchor rationalization

> **batch ID:** W7-B3  
> **risk axis:** tests + README  
> **실행일:** 2026-04-14  
> **상위 계획:** `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md` §5.4

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `tests/test_foms_namespace_imports.py` (thin aggregator) | product source |
| `tests/contracts/runtime/foms_namespace_surface_tests.py` (substantive) | legacy import assertion 삭제 |
| `tests/contracts/__init__.py`, `tests/contracts/runtime/__init__.py` | bridge retirement 성격 coverage 제거 |
| `tests/README.md` (batch table) | `foms/`, `services/`, `apps/` 수정 |

## 2. Product / wrapper / test delta

| 구분 | delta |
|------|-------|
| product | none |
| wrapper | none |
| test | **Added:** `tests/contracts/__init__.py`, `tests/contracts/runtime/__init__.py`, `tests/contracts/runtime/foms_namespace_surface_tests.py` (substantive body, ex-`test_foms_namespace_imports.py`) |
| test | **Replaced:** `tests/test_foms_namespace_imports.py` → **13-line** thin aggregator re-exporting `foms_namespace_surface_tests` |
| test | **Path fix:** `_REPO_ROOT = parents[3]` + template path tests — 파일이 `tests/contracts/runtime/`로 이동해 `parents[1]`가 repo root가 아니게 된 것에 대한 **근본 수정** (parity 축소 아님) |
| test | **Rename:** substantive 모듈명을 `test_*.py`가 아닌 `foms_namespace_surface_tests.py`로 — `pytest tests/` 시 **중복 수집** 방지 |

## 3. Canonical / removal / merge targets

- **Canonical substantive module:** `tests/contracts/runtime/foms_namespace_surface_tests.py`
- **Stable CLI entry:** `tests/test_foms_namespace_imports.py` (unchanged path for humans/CI)
- **Bootstrap sibling:** `tests/test_app_bootstrap_contract.py` — **unchanged** (B2 freeze: keep separate)

## 4. TR9 family net count

| | Count |
|---|--------|
| Before | 2 (`test_foms` giant + `test_app_bootstrap`) |
| After | 3 (`test_foms` thin + `foms_namespace_surface_tests` + `test_app_bootstrap`) |
| **Net** | **+1** (exceptional allowance) — thin aggregator **13 lines**; helper/support **순증가 없음** |

## 5. Queue / tier / execution state

| Family | execution state (post-B3) |
|--------|---------------------------|
| runtime-anchor | **partial → completed** (rationalization applied) |

## 6. Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `python tools/harness/verify_result.py --json` | success: true |
| `python -m pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q` | **143 passed** |
| `python -m pytest tests/harness/test_hooks_smoke.py::test_verify_result_app_ok_contract -q` | *(run at close)* |
| `python -m pytest tests --collect-only -q` | **inherited-red:** `ModuleNotFoundError: safe_schema_migration` in `test_sqlite_startup_compat.py`; **549 tests collected** (previously duplicate 140 제거로 총계 감소 — 악화 아님) |

## 7. Harness smoke (plan §6 / Verification Matrix)

```powershell
python -m pytest tests/harness/test_hooks_smoke.py::test_verify_result_app_ok_contract -q
```

*(Executor: run and paste result into repo if not already green.)*

## 8. Diagnostics

`ReadLints` on `tests/test_foms_namespace_imports.py`, `tests/contracts/runtime/foms_namespace_surface_tests.py` — **no issues**.

## 9. Branch label

**`Branch A`**

## 10. Next legal batch

**`W7-B4`** — WDCalculator chunk-contract freeze

## 11. Direction Lock (10문항)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | product 미수정 |
| 2 | **Y** | bridge 미조기 실행 |
| 3 | **Y** | 140 tests 보존, parity 축소 없음 |
| 4 | **Y** | micro pair N/A (runtime anchor) |
| 5 | **Y** | N/A |
| 6 | **Y** | runtime anchor만 |
| 7 | **Y** | WDC 미건드림 |
| 8 | **Y** | N/A |
| 9 | **Y** | README 배치 테이블 갱신 |
| 10 | **Y** | next = W7-B4 |

## 12. Why not now / prep

- **N/A** — B3 complete.
