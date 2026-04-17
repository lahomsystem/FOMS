# EPT-B4 — Secondary 5 primary shell-aware dual-mode (run record)

**Status:** completed (2026-04-17)  
**Authoritative with:** `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, B1–B3 run records (do not redo R0/B1/B2/B3).

## Verification (closeout)

- `python -c "import app; print('APP_OK')"` → `APP_OK`
- `python tools/harness/verify_result.py --json` → green
- `pytest tests/domains/test_erp_shell_fragment_contract.py -q` → 30 passed (B4: secondary 5 + 9-path alignment + tier parity tests)

## Scope (locked)

- **In:** Five secondary primary surfaces only:
  - `/erp/drawing-workbench` (list/dashboard route; **not** `/erp/drawing-workbench/<id>` — B5)
  - `/erp/production/dashboard`
  - `/erp/construction/dashboard`
  - `/erp/completion`
  - `/erp/history/` (trailing slash canonical)
- **Out:** Subordinate/detail pages, non-primary ERP surfaces, DB/schema/migrations, KPI/filter semantics changes.

## Acceptance

- Each path uses `get_erp_shell_view_mode` / `wants_erp_shell_tab_body` / `apply_erp_shell_fragment_headers` (B3 pattern).
- `view=fragment|critical|heavy` + `X-FOMS-ERP-SHELL: 1` returns body-only HTML with `X-FOMS-ERP-FRAGMENT: 1` and `X-FOMS-ERP-FRAGMENT-TIER` matching mode; critical/heavy body bytes match fragment (tier header differs).
- `view=fragment` **without** shell header returns **full document** (JS-off safe).
- `ERP_FRAGMENT_READY_PATHS` / client `FRAGMENT_READY_PATHS` extended only for verified paths (this batch: all five together after tests green).
- Single-truth templates: full page `{% include %}` same body partial(s) as fragment wrapper.
- Tests: `APP_OK`, `verify_result.py --json`, `pytest tests/domains/test_erp_shell_fragment_contract.py`, B4-focused cases.

## Hard stop

- Blindly adding paths to `FRAGMENT_READY_PATHS` before server+test parity.
- Mixing detail/subordinate work into B4.
- Semantic drift (KPI, pagination, permissions, URLs).

## GDM super hard review

- Diff vs SPEC §2–§3 (fragment headers, tier), B3 patterns on five handlers; `ERP_FRAGMENT_READY_PATHS` order matches `ERP_PRIMARY_NAV_PATHS`; no detail routes in batch.
- Full verification commands run before status → completed (see §Verification).
