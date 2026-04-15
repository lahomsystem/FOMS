# WR-O1 — Orders adapter shell collapse

> **batch ID:** WR-O1  
> **risk axis:** structure / adapter shell  
> **실행일:** 2026-04-15  
> **상위 문서:** `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md` Program 2, `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md` WR-O1

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `foms/api/orders/__init__.py`, `apps/api/orders/__init__.py`, `foms/platform/blueprints.py`, `foms/api/orders/README.md`, runtime sentinel, 본 run record | jobs string contract, storage singleton, high-risk cluster, ERP order owners, packaging reopen |

## 2. Live truth before

- `apps/api/orders/__init__.py` still owned the Flask `Blueprint`, decorators, and route shell.
- `foms/api/orders/*` only owned `*_response` helpers.
- `foms/platform/blueprints.py` still imported `orders_bp` from `apps.api.orders`.

## 3. Implementation delta

### 3.1 Product file delta

- `foms/api/orders/__init__.py`
  - now owns `orders_bp`
  - now owns route decorators and shell handlers
  - re-exports stable helper surface (`can_edit_erp`, `enqueue_geocode_order_address`, `get_today_kst`)
- `foms/platform/blueprints.py`
  - registry import source rerouted to `foms.api.orders`

### 3.2 Wrapper file delta

- `apps/api/orders/__init__.py`
  - reduced from route owner to compatibility re-export wrapper
  - no longer defines `@orders_bp.route(...)` handlers
  - retains stable import surface for existing callers/tests

### 3.3 Local README delta

- `foms/api/orders/README.md`
  - updated from “helper cluster + apps shell” to “canonical route + helper cluster”
  - documents `apps.api.orders` as re-export-only wrapper

### 3.4 Removal / retention decision

- full package-path removal was **not** bundled in WR-O1
- reason: `apps.api.orders` is still a public compatibility surface and package-directory retirement is separable from shell collapse
- removal target: later cleanup tranche only if package-path callers are explicitly drained and directory retirement is approved

## 4. Canonical target

- authoritative route owner: `foms/api/orders/__init__.py`
- authoritative helper cluster: `foms/api/orders/*`
- legacy compatibility wrapper: `apps/api/orders/__init__.py`

## 5. Verification

### 5.1 Automated

- `python -c "import app; print('APP_OK')"` -> pass
- `python -m pytest tests/test_orders_boundary_contract.py` -> `9 passed`
- `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "orders_adapter_shell or erp_display_lazy_callers_use_canonical_import_paths or erp_api_modules_use_canonical_erp_display_imports"` -> `3 passed`
- `python tools/harness/verify_result.py --json` -> `"success": true`

### 5.2 Lint

- `ReadLints` on edited files: no new WR-O1 diagnostic introduced
- residual workspace diagnostic remains at `tests/contracts/runtime/foms_namespace_surface_tests.py` unrelated to WR-O1 (`erp_automation.build_auto_tasks`)

## 6. Guardrail check

- one-family-per-batch 원칙 유지
- new shim을 늘리지 않고 기존 shell을 canonical owner + compatibility wrapper로 축소
- `app.py`, deploy, worker, alembic, schema lifecycle 미변경
- `apps.api.orders`를 다른 ERP owner batch와 섞지 않음

## 7. Next legal batch

- `WR-J1` — `services.jobs/*` runtime-string contract
