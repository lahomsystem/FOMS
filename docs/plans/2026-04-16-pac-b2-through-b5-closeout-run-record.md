# PAC-B2 — PAC-B5 closeout run record (post-audit correction tranche)

> Date: 2026-04-16  
> Plan: `docs/plans/2026-04-16-strict-final-canonical-tree-post-audit-correction-plan.md`

## PAC-B2 — Channel page endpoint correction

- **Change:** `url_for('channel_chat_pages.chat')`, `url_for('channel_chat_pages.chat_scripts_js')` in `templates/partials/shared/layout_nav.html`, `templates/channel/chat.html`.
- **rg:** `chat.chat` / `chat.chat_scripts_js` in `templates` + `foms` → 0 (excludes plan/docs historical mentions if any remain only under `docs/`).

## PAC-B3 — Inline HTTP error finalization

- **Change:** `foms/platform/http.py` serves `_INLINE_HTML_404` / `_INLINE_HTML_500`; `render_template("partials/http_errors/...")` removed.
- **Removed:** `templates/partials/http_errors/` (directory absent).

## PAC-B4 — Shared partial redistribution (§4.3 ledger)

- **Moves:** Context-owned paths under `templates/orders/partials/`, `templates/construction/partials/`, `templates/cs/partials/` per plan ledger; wrappers retired (`erp_production_*`, `erp_measurement_mobile_*` deleted).
- **Callers:** Dashboards and order/cs templates updated to new include paths.
- **Frozen:** `templates/partials/shared/*.html` == §3.3 exact allowlist (10 files).

## PAC-B5 — Final proof

Commands (representative; run on clean tree at same commit):

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q
python -m pytest tests -q
powershell -NoProfile -File tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest
```

- **Overclaim correction:** see `docs/plans/2026-04-16-pac-slgb-overclaim-correction-note.md`.

## Reviewer matrix (GDM)

| Role | Check |
|------|--------|
| A (literal/spec) | §3.1–§3.3 decision locks, §4.3 ledger paths |
| B (runtime) | No `chat.chat` page callers; 404/500 from `http.py` only |
| C (proof) | Commands above green; clean-room uses `-RunFullPytest` |

**Status:** PASS when committed snapshot reproduces green clean-room.
