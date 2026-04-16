# PTC-B7 — Final dual-surface closeout (run record)

## Evidence (this workspace session)

| Gate | Result | Notes |
|------|--------|--------|
| `python -c "import app; print('APP_OK')"` | OK | After edits |
| `python tools/harness/verify_result.py --json` | OK | |
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` | 185 passed | |
| `pytest tests -q` | 605 passed | Includes `test_ptc_physical_exactness.py` when present |
| `tools/harness/ptc_workspace_cleanup.ps1 -RecursePyCache` then `ptc_workspace_hygiene_probe.ps1 -RecursePyCache` | OK | `node_modules` / `venv` / `.venv` excluded from recursive `__pycache__` scan |
| `strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest` | OK | See **HEAD lag warning** below |

## HEAD lag warning (mandatory)

`strict_canonical_b12` replays tests on **committed** `HEAD`. At run time, many PTC files were still **untracked/uncommitted** (e.g. `test_ptc_physical_exactness.py`, harness scripts, run records). The clean-room run succeeded at `ff65f267` but reported **600** tests passed vs **605** on the dirty tree — consistent with PTC tests not yet in `HEAD`.

**Before declaring production PTC closeout:** stage and commit the full PTC tranche, then re-run:

```powershell
powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest
```

## Dual-spec 1:1 GDM audit

- **R1 Spec:** Controlling specs `2026-04-07-repo-structure-governance_SPEC.md` and `2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` were updated in PTC-B1; no new controlling spec file was introduced.
- **R2 Physical tree:** Root allowlist + `data/` policy enforced by `test_ptc_physical_exactness.py` (must be **committed** for `HEAD` proof).
- **R3 Code / README:** FR20 README batch + `PTC_RUNTIME_COMMON_INVENTORY.md`.
- **R4 Proof:** PAC/SLG gates retained in `foms_namespace_surface_tests.py` + clean-room script; workspace probe + cleanup documented.

**Manual:** Maintainer signs off that spec wording has **no unresolved conflict** before merge to production branches.

## Hard-stop checklist (plan §6.3)

- Not claiming code closeout while spec text conflicts remain.
- Not claiming workspace green without running cleanup when residue exists.
- Not using workspace-only cleanup to hide spec/code drift.
