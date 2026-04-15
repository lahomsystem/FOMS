# Wave 8 — W8-B5 Direct-import bridge retirement — Run record

**Date:** 2026-04-14  
**Branch:** A

## Direction locks

| Lock | Status |
|------|--------|
| Bridge count non-increasing | **PASS** — 6 direct-import bridge files deleted (−6) |
| Shell collapse not promoted | **PASS** — high-risk shells untouched |
| `blueprints.py` registration order | **PASS** — import source lines only; register sequence unchanged |
| Retirement sentinel / canonical smoke | **PASS** — `find_spec` None + canonical module smoke in runtime tests |

## Legacy paths removed (6 files)

- `apps/api/files.py`
- `apps/api/address.py`
- `apps/api/erp_measurement.py`
- `apps/erp_measurement_dashboard.py`
- `apps/erp_production_page.py`
- `apps/erp_completion_page.py`

## Files touched (summary)

- **Registry:** `foms/platform/blueprints.py` — canonical `foms.web.*` / `foms.api.*` imports only
- **Consumer import reroute (import line only):** `apps/api/attachments*.py`, `apps/api/chat/*.py`, `apps/api/erp_orders_*.py`
- **Canonical doc sync:** `foms/api/files.py`, `foms/api/address.py`, `foms/web/measurement/README.md`
- **Tests:** `tests/contracts/runtime/foms_namespace_surface_tests.py`, `tests/test_measurement_slice_contract.py`, `tests/test_channel_push_messages.py`, `tests/test_erp_measurement_mobile_render.py`

## Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `python tools/harness/verify_result.py --json` | ok |
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/test_measurement_slice_contract.py tests/test_menu_config.py tests/test_foms_namespace_imports.py -q` | 297 passed |
| `pytest tests/test_channel_push_messages.py tests/test_erp_measurement_mobile_render.py -q` | 9 passed |

## rg zero-import (product + non-deferred tests)

- Legacy dotted paths appear only in: `backups/**` (out of gate), docstrings noting removal, and `find_spec` sentinel tests.

## Bridge count delta

**−6** (six `apps/*` direct-import bridges removed)

## Next legal batch

**W8-B6** — Bridge status register
