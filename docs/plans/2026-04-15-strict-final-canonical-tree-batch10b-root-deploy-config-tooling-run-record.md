# Strict final canonical tree — SFC-B10B run record

> **date:** 2026-04-15  
> **batch:** `SFC-B10B` — Root deploy/config/tooling artifact liquidation (`docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §6.14)

## 1. Goal

- Remove root deploy/config/tooling debt per ledger §2.5 / §6.14: `.cursorrules`, root `config/`, `app.yaml`, `runtime.txt`, `pyrightconfig.json`, `railway_bootstrap.py`.
- Consumer proof before deletes: root `config/` had **no** Python imports (`rg`); live rate limiting uses `foms.services.rate_limit`.

## 2. Removals / relocations (git-tracked)

| From (repo root or path) | To / disposition |
|--------------------------|------------------|
| `railway_bootstrap.py` | `scripts/ops/railway_bootstrap.py` (repo root on `sys.path` for `from app import app`) |
| `pyrightconfig.json` | `tools/harness/pyrightconfig.json` (`executionEnvironments.root` = `../..`); IDE: `.vscode/settings.json` `python.analysis.extraPaths` |
| `app.yaml` | `docs/context/manual-artifacts/legacy-deploy/app.yaml` (legacy GAE sample) |
| `runtime.txt` | `docs/context/manual-artifacts/legacy-deploy/runtime.txt` (Heroku-style hint; no code consumer) |
| `.cursorrules` | removed (superseded by `.cursor/rules/*.mdc` + AGENTS) |
| `config/` (`__init__.py`, `rate_limit.py`) | removed (dead duplicate) |

## 3. Docs / ops references

- `scripts/ops/sync_local_to_railway.ps1` — bootstrap path → `scripts/ops/railway_bootstrap.py`
- `docs/guides/MIGRATION_GUIDE_RAILWAY.md`, `MIGRATION_RAILWAY_R2.md`, `RAILWAY_ENV_VARS.md`, `RAILWAY_LOCAL_TO_REMOTE_SYNC.md` — same
- `README.md` — GAE `app.yaml` sample path → `docs/context/manual-artifacts/legacy-deploy/app.yaml`
- `.cursor/agents/GDM_EXECUTION_PLAN.md` — bootstrap path
- `docs/guides/MIGRATION_GUIDE_RAILWAY.md` — SQLite path note (B10A hygiene): `data/localdb/...`

## 4. Contract test

- `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_root_deploy_tooling_artifacts_sfc_b10b`

## 5. Verification

- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **579 passed** (2026-04-15)

## 6. Next

- **`SFC-B11A`** — `apps/` consumer migration freeze + reroute (plan §6.15).
