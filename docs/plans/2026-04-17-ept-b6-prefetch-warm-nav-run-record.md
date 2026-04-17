# EPT-B6 — Prefetch + warm navigation + runtime restore (run record)

**Status:** completed (2026-04-17)  
**Locks with:** `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, R0–B5 (do not redo).

**Evidence:** `APP_OK`; `verify_result.py --json` success; `pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py -q` → **45 passed** (Win11, Python 3.12). 브라우저 Performance·Railway ms 실측은 §4.8/B8 범주(본 배치에서 수치 closeout 주장 안 함).

## Scope (locked)

### In

- **`static/js/erp/runtime-shell.js` only** (no server payload/schema change; no micro-cache policy change).
- **Shell fragment swap** extended from 9-primary exact match to **B5 subordinate fragment-capable** GET surfaces:
  - `/erp/drawing-workbench/<order_id>` (numeric id)
  - `/edit/<order_id>` (+ query preserved in cache key)
  - `/erp/shipment-settings`
- **Prefetch** (same-origin, `credentials: 'same-origin'`, `view=fragment`, `X-FOMS-ERP-SHELL: 1`):
  - **Idle**: staggered prefetch of other **primary 9** paths (not current); no guessed subordinate IDs.
  - **Hover / focus**: debounced prefetch for anchors that pass the shell-swap allowlist (primary + subordinate patterns).
- **Warm navigation**: in-memory LRU + TTL cache of successful fragment HTML; **cache hit** → immediate `#main-content` swap (no second network).
- **History / scroll**: `pushState` entries tagged `fomsErpShell`; `popstate` restores body from **cache-first** then fetch fallback; **scroll Y** restored from per-URL memory on back/forward (forward nav still resets to top).
- **Explicit out of prefetch + shell swap**: `/map_view`, legacy redirect-only paths, non-fragment full documents.

### Out (hard)

- B7 HTML diet, asset stripping, profiling tranche.
- DB / migration / template semantics change beyond JS client behavior.
- Changing `ERP_FRAGMENT_READY_PATHS` / `PRIMARY_NAV_PATHS` **9-tuple** on server (client list stays 9 + subordinate patterns **additive**).
- Prefetch without cookie (`credentials: 'same-origin'` always).

## Acceptance

- Idle + hover/focus prefetch run without throwing; duplicate in-flight deduped; LRU evicted past cap.
- Warm path: second navigation to same canonical key uses cache (no full reload).
- `popstate` on shell-managed URLs: no unconditional `location.reload` when cache or fetch can restore.
- JS-off / no script: unchanged full GET (script not executed).
- `pytest tests/domains/test_erp_shell_fragment_contract.py` + `test_erp_runtime_shell_js_contract.py` green; `APP_OK` + `verify_result.py --json`.

## Hard stop

- Cross-user / cross-session cache (in-memory only; page lifetime).
- Prefetch `map_view` or non-fragment routes.
- Shrinking HTML or skipping `view=fragment` to fake speed.

## Verification

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py -q
```
