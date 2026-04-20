# PTC-B5 — Workspace artifact generator closure (run record)

## Scope

- Document + script the cleanup sequence for final workspace exactness (plan §5.6, §4.4).
- Block/repair path: operators run `ptc_workspace_cleanup.ps1` before `ptc_workspace_hygiene_probe.ps1` green.
- `.gstack/` remains gitignored; removal is manual/scripted, not a code generator change inside this batch.

## Delivered

- `tools/harness/ptc_workspace_cleanup.ps1` — removes `.gstack`, `.pytest_cache`, `.tmp_strict_tree_verify`, root `__pycache__`, root `*.db`/`*.dump`; optional `-RecursePyCache`.
- `docs/harness/PTC_WORKSPACE_HYGIENE.md` — sequence, optional external pytest cache env, pointer to probe.
- `tools/harness/ptc_workspace_hygiene_probe.ps1` — header points to cleanup doc/script.

## B4 follow-through (same tranche, ledger §4.3)

- `scripts/ops/sync_local_to_railway.ps1` — dump → `FOMS_RUNTIME_OUTPUT_ROOT\dumps\foms.dump` (ensure `dumps\` exists).
- `scripts/migrations/migrate_local_to_remote.py` — SQLite → `FOMS_RUNTIME_OUTPUT_ROOT\localdb\furniture_orders.db`.
- `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `MIGRATION_RAILWAY_R2.md`, `MIGRATION_GUIDE_RAILWAY.md` — paths/docs aligned.

## Verification (local)

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q
pytest tests -q
```

## GDM

| Role | Result |
|------|--------|
| R1 Spec | Paths match §2.6.2 / plan §3.4 `FOMS_RUNTIME_OUTPUT_ROOT` contract. |
| R2 Physical | No new tracked junk; scripts write outside repo tree. |
| R3 Code owner | Operational scripts + migration only; inventory doc for runtime/common. |
| R4 Proof | Full pytest green; probe green **after** cleanup on audit machine. |

**High = 0, Medium = 0.**

## Note

`ptc_workspace_hygiene_probe.ps1` may still **fail** on a dev PC until cleanup is run — expected. Final PTC-B7 closeout: cleanup → probe green → `strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest`.
