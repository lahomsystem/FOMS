# PTC-B2 — B4 convergence bundle (run record)

> B2 proof gates + B3 FR20 README + B4 `data/` runtime placeholder removal were executed in one push to avoid leaving `pytest tests` red (GDM High/Medium zero).

## PTC-B2 — Proof hardening

### Delivered

- `tests/contracts/runtime/test_ptc_physical_exactness.py` — committed root allowlist (§2.6.1), `static/js/runtime` + `foms/services/common` §4.5 inventories, tracked `data/` runtime-path ban, FR20 README presence.
- `tools/harness/strict_canonical_b12_clean_room.ps1` — comment lock to §2.6.1 / §4.1 (allowlist array unchanged; already matched spec).
- `tools/harness/ptc_workspace_hygiene_probe.ps1` — root probe for `.gstack`, `.pytest_cache`, `.tmp_strict_tree_verify`, root `__pycache__`, root `*.db`/`*.dump`.
- `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_root_manual_artifacts_sfc_b10a` no longer requires `data/dumps` / `data/localdb` dirs (PTC §4.3 supersedes prior B10A placeholder contract).

### Verification

```text
python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q
python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q
python -m pytest tests -q
```

Results: 5 + 185 + 605 passed (local run).

`ptc_workspace_hygiene_probe.ps1` may **fail** on dev trees with `.gstack` / `.pytest_cache` / `__pycache__` — **PTC-B5** targets zero residue before final audit.

## PTC-B3 — Context README canonicalization

- Added FR20 authoritative `README.md` under `foms/web/<context>/` for all page-first contexts (including `orders`).
- Added FR20 authoritative `README.md` under `foms/api/<context>/` for `channel`, `files`, `notifications`.
- Removed `foms/api/orders/README.md` — orders is **page-first**; single canonical entry is `foms/web/orders/README.md` (content merges web + API pointers).

## PTC-B4 — `data/` runtime-output retirement (partial)

### Done (tracked tree)

- `git rm` `data/dumps/.gitkeep`, `data/localdb/.gitkeep`; directories removed from working tree.

### Script/doc reroute (completed in PTC-B5 tranche)

- `scripts/ops/sync_local_to_railway.ps1`, `scripts/migrations/migrate_local_to_remote.py`, `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `MIGRATION_RAILWAY_R2.md`, `MIGRATION_GUIDE_RAILWAY.md` — aligned to `FOMS_RUNTIME_OUTPUT_ROOT` (see `2026-04-16-ptc-b5-run-record.md`).

## GDM (B2–B4 bundle)

| Role | Result |
|------|--------|
| R1 Spec | Dual-spec §2.6.1 / §2.2.3 / §2.5 lock consistent with edits. |
| R2 Physical tree | Root allowlist test green; `data/dumps`+`localdb` placeholders removed from index. |
| R3 Code owner | README + test adjustments only; no business-logic refactor. |
| R4 Proof | Full `pytest tests` green; namespace contract file green. |

**High = 0, Medium = 0** for merged B2–B4 scope above.

## Next

- **PTC-B5** — workspace generator closure + hygiene probe green on audit machine.
- **PTC-B6** — `runtime/common` rationale doc + any moves (inventory already enforced by `test_ptc_*`).
- **PTC-B7** — dual-surface closeout + clean-room on **committed** `HEAD` + script path migration completion.
