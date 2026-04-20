# EPT-B7 — HTML diet + page-scoped assets + profiling (run record)

**Status:** closed (2026-04-17)  
**Locks with:** `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, R0–B6 (do not redo shell/prefetch/history truth).

## Delivered

| Area | Change |
|------|--------|
| Orders ERP dashboard | `orders/partials/dashboard_main.html`: inline `<style>` + `<script>` (알림·도면 뷰어) → `static/css/contexts/orders/dashboard-gateway-notifications.css`, `static/js/orders/dashboard-notifications.js` (`defer`). Full + fragment both include partial → parity. |
| AS dashboard | `cs/partials/as_dashboard_body.html`: first large `<style>` block → `static/css/contexts/cs/as-dashboard-body.css` via `<link>` in body partial. |
| Shipment dashboard | `shipment/partials/dashboard_main.html`: table-area `<style>` (~777 lines) → `static/css/contexts/shipment/dashboard-table-extras.css`. |
| Profiling | `foms/services/common/ept_b7_profile.py`: `X-FOMS-EPT-B7-ROUTE`, `X-FOMS-EPT-B7-RENDER-MS` + `[EPT-B7]` info log. Wired after `render_template` only for `erp_dashboard`, `erp_as_dashboard`, `erp_shipment_dashboard`. |
| Tests | `tests/domains/test_ept_b7_profile.py` — header helper + static file existence. |

## Template byte reduction (approximate, UTF-8)

- Removed from HTML templates: ~15 KB orders inline + ~5 KB AS + ~27 KB shipment inline (now served as separate cacheable static files). Initial HTML response is smaller; browser may fetch CSS/JS in parallel.

## Deferred (explicit, no semantic / data deferral)

- **Row-level or KPI lazy-load / extra round-trips:** would risk “data late” vs full GET; out of scope for B7 per stop rules. If needed, register under ERP perf follow-up (query rewrite is also out of scope for B7).

## Verification (executed)

- `python -c "import app; print('APP_OK')"` OK  
- `python tools/harness/verify_result.py --json` OK  
- `pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_ept_b7_profile.py -q` → **47 passed**

## Scope (locked)

### In

- **HTML diet (semantic parity):** move large inline `<style>` / bulky inline `<script>` from ERP dashboard surfaces to **static files**, referenced via `<link>` / `<script src>` from **body partials** so **full HTML and shell fragment** both load the same rules (no head-only CSS that fragments would miss).
- **Targets (this batch):**
  - `orders/partials/dashboard_main.html` — drawing-gateway + notification panel CSS; notification panel JS → `static/js/orders/dashboard-notifications.js` (deferred).
  - `cs/partials/as_dashboard_body.html` — first AS dashboard CSS block → `static/css/contexts/cs/as-dashboard-body.css`.
  - `shipment/partials/dashboard_main.html` — large table-area `<style>` → `static/css/contexts/shipment/dashboard-table-extras.css`.
- **Profiling (cache-outside split):** optional response headers + structured log line for **Jinja render time** only on:
  - `erp_dashboard` (`/erp/dashboard`)
  - `erp_as_dashboard` (`/erp/as`)
  - `erp_shipment_dashboard` (`/erp/shipment`)
- **Headers:** `X-FOMS-EPT-B7-ROUTE`, `X-FOMS-EPT-B7-RENDER-MS` (milliseconds for `render_template` only). Log: `[EPT-B7] route=… render_ms=…`.
- **Out of scope (hard):** query rewrite / ORM change (defer to register); Railway p50/p95 closeout (**B8**); shrinking row counts or KPI payloads.

### Hard stop

- Removing or deferring **data** that full mode already had on first paint.
- Breaking JS-off full GET or fragment/full parity.
- Weakening prefetch/history/cache contracts.
- Claiming B8 Railway evidence from B7.

## Acceptance

- Initial HTML/fragment responses for touched pages are **lighter** (inline CSS/JS bytes removed from templates; browser may cache static assets).
- `dashboard`, `as`, `shipment` surfaces keep **identical** DOM semantics for the same query/user (no fewer rows, no different filters).
- Profiling headers present on the three routes above; logs parseable for render vs cache story.
- `APP_OK`, `verify_result.py --json`, `pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py` (+ B7 unit test if added) green.

## Verification

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_ept_b7_profile.py -q
```
