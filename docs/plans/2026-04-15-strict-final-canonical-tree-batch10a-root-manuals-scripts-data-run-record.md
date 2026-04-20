# Strict final canonical tree — SFC-B10A run record

> **date:** 2026-04-15  
> **batch:** `SFC-B10A` — Root manuals/scripts/data artifact liquidation (`docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §6.13)

## 1. Goal

- Remove manual/script/data/db/dump artifacts from the repository root per ledger §2.5 / §6.13.
- Update consumers (runtime paths, harness exact-match lists, migration/sync scripts, docs).

## 2. Moves (git-tracked)

| From (repo root) | To |
|------------------|-----|
| `build_wdplanner.bat` | `scripts/maintenance/build_wdplanner.bat` |
| `start_foms_utf8.bat` | `scripts/maintenance/start_foms_utf8.bat` |
| `findings.md`, `progress.md`, `task_plan.md` | `docs/context/analysis/` |
| `MIGRATION_GUIDE_RAILWAY.md`, `MIGRATION_RAILWAY_R2.md`, `RAILWAY_ENV_VARS.md`, `TEST_GUIDE.md` | `docs/guides/` |
| `foms_address_learning_data.json` | `data/address/foms_address_learning_data.json` |
| `menu_config.json` | `data/admin/menu_config.json` |

## 3. New directories

- `data/dumps/` — canonical location for `pg_dump` output (`data/dumps/foms.dump`; `.gitkeep` only in repo).
- `data/localdb/` — SQLite / migration scratch DBs (`.gitkeep` only in repo).

## 4. Code / config updates

- **`foms/services/menu_config.py`:** `_MENU_CONFIG_PATH` → `data/admin/menu_config.json`.
- **`foms/web/admin/routes.py`:** write path + `os.makedirs("data/admin", exist_ok=True)` before save.
- **`foms/services/admin/backup_service.py`:** backup list path for menu config.
- **`scripts/ops/sync_local_to_railway.ps1`:** `$DumpPath` → `data\dumps\foms.dump`.
- **`scripts/migrations/migrate_local_to_remote.py`:** `LOCAL_DB_URL` → `data/localdb/furniture_orders.db` (absolute URL from repo root).
- **`scripts/ops/foms_address_learning.py`:** default learning file → `data/address/foms_address_learning_data.json`.
- **`tools/harness/prompt_router.py` / `tools/harness/run_codex.ps1`:** harness context exact matches for `task_plan.md` / `findings.md` / `progress.md` → `docs/context/analysis/...`.
- **`scripts/maintenance/build_wdplanner.bat`:** `pushd` to repo root (`%~dp0..\..`) so WDPlanner + `static/wdplanner` paths stay valid.
- **`scripts/maintenance/start_foms_utf8.bat`:** `pushd` to repo root before `python app.py`.
- **Docs:** `docs/guides/WDPLANNER_INTEGRATION.md`, `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `docs/guides/MIGRATION_RAILWAY_R2.md` — paths for scripts and dumps.

## 5. Local-only hygiene (ignored artifacts)

If present at repo root, these should live under `data/` for B10A contract tests and ops consistency:

- `foms.dump` → `data/dumps/foms.dump`
- `furniture_orders.db`, `migration_ready.db`, `ops_browser_qa.db` → `data/localdb/`

(Not committed; developer/CI may or may not have them.)

## 6. Contract test

- `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_root_manual_artifacts_sfc_b10a`

## 7. Verification

- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **578 passed** (2026-04-15)

## 8. Next

- **`SFC-B11A`** — `apps/` consumer migration freeze + reroute (plan §6.15). **`SFC-B10B`** complete: `docs/plans/2026-04-15-strict-final-canonical-tree-batch10b-root-deploy-config-tooling-run-record.md`.
