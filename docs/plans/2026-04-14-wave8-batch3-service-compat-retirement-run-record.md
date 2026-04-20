# Wave 8 — W8-B3 Service compat shim retirement — Run record

**Date:** 2026-04-14  
**Branch:** A  
**Baseline:** inherited-red (collect-only); fresh green (APP_OK + verify_result)

## Direction locks (this batch)

| Lock | Status |
|------|--------|
| Bridge count non-increasing | **PASS** — removed 4 shim modules (−4 bridges) |
| Shell collapse not promoted | **PASS** — no high-risk cluster edits |
| `blueprints.py` registration order | **N/A** — not modified in B3 |
| Retirement sentinel per deleted bridge | **PASS** — `find_spec` None for all four legacy import paths in `foms_namespace_surface_tests.py` |

## Legacy paths removed

- `services/realtime_notifications.py`
- `services/file_utils.py`
- `foms/services/realtime_notifications.py`
- `foms/services/file_utils.py`

## Files touched

- Deleted: four shim files above
- `foms/services/notifications/__init__.py`, `foms/services/files/__init__.py`, `foms/services/README.md`
- `tests/contracts/runtime/foms_namespace_surface_tests.py` — retirement sentinels + canonical API checks
- `tests/test_realtime_notifications.py` — canonical import

## Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `python tools/harness/verify_result.py --json` | ok |
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/test_realtime_notifications.py tests/test_foms_namespace_imports.py -q` | 287 passed |

## rg zero-import (product + non-deferred tests)

- `services.realtime_notifications` / `foms.services.realtime_notifications` / `services.file_utils` / `foms.services.file_utils`: no **import** usage in `apps/` or `foms/**/*.py` except docstrings in `foms/services/*/ __init__.py` and sentinel assertions in `foms_namespace_surface_tests.py`.

## Bridge count delta

**−4** (four compat shims removed)

## Next legal batch

**W8-B4** — Direct-import bridge freeze
