# Wave 8 — W8-B4 Direct-import bridge freeze — Run record

**Date:** 2026-04-14  
**Branch:** A

## Direction locks

| Lock | Status |
|------|--------|
| Bridge deletion | **FROZEN** — no code edits in B4 |
| `blueprints.py` | **FROZEN** — B5 only |
| Shell collapse pilots | **EXCLUDED** — `personal_board`, `orders` not touched |

## Direct-import candidate set (exact paths)

| Legacy bridge file | Canonical target |
|--------------------|------------------|
| `apps/api/files.py` | `foms.api.files` |
| `apps/api/address.py` | `foms.api.address` |
| `apps/api/erp_measurement.py` | `foms.api.measurement` |
| `apps/erp_measurement_dashboard.py` | `foms.web.measurement.dashboard` |
| `apps/erp_production_page.py` | `foms.web.production.dashboard` |
| `apps/erp_completion_page.py` | `foms.web.cs.completion_dashboard` |

## Known caller map (`from apps.api.files` — B5 reroute targets)

- `foms/platform/blueprints.py` (registry import — B5)
- `apps/api/attachments_internal/search.py`
- `apps/api/chat/routes_files.py`
- `apps/api/attachments.py`
- `apps/api/erp_orders_drawing.py`
- `apps/api/erp_orders_completion.py`
- `apps/api/erp_orders_blueprint.py`
- `apps/api/attachments_internal/common.py`
- `apps/api/attachments_internal/direct_upload.py`
- `apps/api/chat/utils.py`

## `apps.api.address` product callers (pre-B5)

- `foms/platform/blueprints.py` only (plus historical `backups/**` — out of gate scope per plan §1.2.1 item 18).

## Measurement / production / completion alias bridges — non-registry product callers

- **Dashboard / API / pages:** no `import apps.erp_measurement_dashboard` / `apps.erp_production_page` / `apps.erp_completion_page` / `apps.api.erp_measurement` in `apps/`, `foms/`, `services/` outside the six bridge files and `foms/platform/blueprints.py`.
- **Tests:** `tests/contracts/runtime/foms_namespace_surface_tests.py`, `tests/test_measurement_slice_contract.py`, `tests/test_erp_measurement_mobile_render.py`, `tests/test_channel_push_messages.py` — will switch to canonical imports in **W8-B5** (allowed non-doc test callers).

**Gate:** `foms/platform/blueprints.py` + dedicated tests 외 **doc-only** reference in `foms/web/measurement/README.md`; no additional product runtime caller beyond B4 map → **PASS** for mainline B5 (not `direct-import-freeze-stop`).

## Exclusions (no overlap with candidate set)

- `apps/api/personal_board.py`
- `apps/api/orders/__init__.py`
- `apps/api/notifications.py`

## Locked test surface (B5)

- `tests/contracts/runtime/foms_namespace_surface_tests.py`
- `tests/test_measurement_slice_contract.py`
- `tests/test_menu_config.py` (no legacy bridge imports — verify-only)
- `tests/test_foms_namespace_imports.py` (if needed)

## Verification (B4)

- Caller map + canonical targets documented
- Candidate ∩ exclusion = ∅
- Measurement/production/completion gate: registry + tests + README only

## Next legal batch

**W8-B5** — Direct-import bridge retirement (−6 bridge files)
