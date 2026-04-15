# Strict final canonical tree — SFC-B11D run record

> **date:** 2026-04-15  
> **batch:** `SFC-B11D` — `src/` retirement (`docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §6.18)

## 1. Goal

- Remove ambiguous repo-root `src/` per `SF3` / §6.18.
- Relocate non-product TypeScript/React Native prototype to approved non-product home: `Add In Program/WDPlanner/legacy-mobile-prototype/`.
- Preserve `src/README.md` classification narrative (Wave 1 W1-B2); add physical-location note after move.

## 2. Relocation (git-tracked)

| From | To |
|------|-----|
| `src/` (root) | `Add In Program/WDPlanner/legacy-mobile-prototype/` |

**Command:** `git mv src "Add In Program/WDPlanner/legacy-mobile-prototype"`

## 3. Contract test

- `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_src_overlay_directory_removed_sfc_b11d_closeout`
- Module docstring references SFC-B11D closeout test name.

## 4. Verification

- `python -c "import app; print('APP_OK')"` — OK  
- `python tools/harness/verify_result.py --json` — OK  
- `pytest tests` — **586 passed** (2026-04-15)

## 5. Next

- **`SFC-B12`** — clean-room exact-match audit + `SG*` scoreboard re-measure (plan §6.19).
