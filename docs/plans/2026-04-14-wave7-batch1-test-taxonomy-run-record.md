# Wave 7 Batch W7-B1 — Test taxonomy + entrypoint freeze

> **batch ID:** W7-B1  
> **risk axis:** docs  
> **실행일:** 2026-04-14  
> **상위 계획:** `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md` §5.2  
> **git HEAD:** `ca144560a4e4e68954c18402bc67a95b4b486793` (same session as W7-B0 unless amended)

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `tests/README.md` (authoritative rewrite) | actual test code movement |
| 본 run record | product source |

## 2. Product / wrapper / test / docs delta

| 구분 | delta |
|------|-------|
| product | none |
| wrapper | none |
| test | none (no file moves) |
| docs | **`tests/README.md` created** (new); 본 run record |

## 3. Canonical targets

- **Entrypoint:** `tests/README.md` = Wave 7 local taxonomy + pilot/defer map + TR1–TR9 + target vs live distinction.
- **Removal / merge:** N/A (docs-only batch).

## 4. Queue class / contract tier / execution state

- **Global execution path:** still **Branch A** (no gate failure).
- Table in README §10: W7-B0 completed; W7-B1 completed; B2+ not started.

## 5. Verification (docs-only batch — 직전 fresh baseline 재사용 + sanity)

Same-session commands (repo root, PowerShell):

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `python -m pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q` | *(run at batch close — see §6)* |

**Note:** B1 introduces no test code; baseline must not regress vs W7-B0 green paths.

## 6. Verification results (filled at completion)

Run after README write:

```text
python -c "import app; print('APP_OK')"  → APP_OK
python tools/harness/verify_result.py --json  → success: true
python -m pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q  → 143 passed in 0.19s
```

Collect-only not re-run for docs-only batch; W7-B0 inherited-red baseline unchanged.

## 7. Why not now / required prep / suggested restart

- **N/A** — B1 complete; next = **W7-B2** runtime anchor contract freeze.

## 8. Next legal batch

**`W7-B2`** — `docs/plans/2026-04-14-wave7-batch2-runtime-anchor-freeze-run-record.md`

## 9. Branch label

**`Branch A`** (unchanged).

## 10. Direction Lock (10문항)

| # | Y/N | 한 줄 근거 |
|---|-----|------------|
| 1 | **Y** | product source 미수정 |
| 2 | **Y** | bridge retirement 미시도 |
| 3 | **Y** | parity assertion 미삭제 |
| 4 | **Y** | micro pair 미추가 |
| 5 | **Y** | tier 혼합 문서에서 분리 정의 |
| 6 | **Y** | pilot = runtime-anchor + composition/primary-form 명시 |
| 7 | **Y** | pricing-core / estimate-lifecycle pilot 제외 명시 |
| 8 | **Y** | Node 요구는 README §8에 명시 (후속 B5) |
| 9 | **Y** | `tests/README.md` 존재 + taxonomy entrypoint |
| 10 | **Y** | next = W7-B2 |

---

## Appendix — checklist (plan §5.2)

- [x] `tests/README.md` 새로 작성 (기존 파일 없었음 → authoritative create)
- [x] contract tier / queue class / mainline pilot / defer family / TR1–TR9 / micro pair 금지
- [x] target taxonomy(`tests/contracts`, `tests/domains`, …) vs **live tree** 구분 문구 포함
- [x] `composition` + `primary-form` pilot 제한 명시
- [x] `test_wdcalculator_product_settings.py`가 단순 composition+primary-form만이 아님을 README에 반영 (B4에서 분류 예고)
