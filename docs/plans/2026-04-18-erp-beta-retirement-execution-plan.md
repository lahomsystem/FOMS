# ERP_BETA Retirement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** FOMS active runtime/product code에서 `ERP_BETA` legacy compatibility를 운영 무중단 기준으로 단계적으로 제거한다.

**Architecture:** `ERP_BETA` 전량 삭제를 한 배치로 밀어넣지 않고, live gate 확인 → stale debt 제거 → runtime alias 제거 → DB/bootstrap canonicalization 순으로 진행한다. 운영 안전은 “코드 정리”보다 “실제 DB/env/inbound 사용량 증거”를 우선하는 방식으로 확보한다.

**Tech Stack:** Flask 2.3, SQLAlchemy 2.0, PostgreSQL, Jinja2, Vanilla JS, Railway

---

### Task 1: Retirement Gates Freeze

**Files:**
- Modify: `docs/specs/2026-04-18-erp-beta-retirement_SPEC.md`
- Test: `tests/domains/test_erp_order_shared_form_scripts.py`
- Test: `tests/domains/test_erp_shell_fragment_contract.py`

**Step 1: Write/extend failing tests**
- add a focused test for `open=erp-beta` compatibility boundary
- add a focused test for `ERP_ORDER_ENABLED` precedence over beta fallback
- add a focused test describing which stale refs are allowed vs forbidden

**Step 2: Run tests to verify current gaps**
- Run: `pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_shell_fragment_contract.py -q`
- Expected: current green or targeted red revealing unguarded retirement gaps

**Step 3: Document live gate checklist**
- lock DB/env/inbound/data evidence items in the spec

**Step 4: Re-run tests**
- Run: `pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_shell_fragment_contract.py -q`
- Expected: PASS

### Task 2: P1 Stale Naming Debt Cleanup

**Files:**
- Modify: `templates/orders/partials/erp_order_tab.html`
- Modify: `static/css/foundation/erp-pro/09-mobile-erp-optimization.css`
- Modify: `foms/platform/erp_blueprint.py`
- Modify: `foms/api/notifications/__init__.py`
- Modify: `foms/api/orders/calendar.py`
- Modify: `foms/api/erp_orders_structured.py`
- Test: existing focused tests

**Step 1: Remove clearly stale template/css/debug/comment refs**
- remove dead `erp_beta_default_stage_received` fallback
- remove stale `#erp-beta`, `#erpBetaTabs`, `.erp-beta-tabs-nav` selectors
- remove dead `ERP_BETA_DEBUG` reads if no consumer exists
- rename internal helper/log/comment naming that is cosmetic only

**Step 2: Run focused verification**
- Run: `pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_shell_fragment_contract.py -q`
- Expected: PASS

**Step 3: App import smoke**
- Run: `python -c "import app; print('APP_OK')"`
- Expected: `APP_OK`

### Task 3: P2 Env and Frontend Alias Retirement

**Files:**
- Modify: `foms/services/context_processors.py`
- Modify: `static/js/orders/erp-order-shared.js`
- Modify: `static/js/orders/estimate-preview.js`
- Modify: `templates/orders/add_order.html`
- Modify: `templates/orders/edit_order.html`
- Modify: `foms/web/orders/listing.py`
- Modify: `foms/api/personal_board.py`
- Modify: `foms/web/orders/trash.py`
- Test: `tests/domains/test_erp_order_shared_form_scripts.py`
- Test: `tests/domains/test_erp_shell_fragment_contract.py`

**Step 1: Confirm live gate evidence**
- verify Railway env explicitly provides `ERP_ORDER_ENABLED`
- verify inbound use of `open=erp-beta` and `create_mode=ERP_BETA` is zero or intentionally cut over
- verify placeholder rows are cleaned or accepted for same-batch data migration
- use `tools/harness/erp_beta_flat_placeholder_backfill_*.sql` runbook to clear the flat-column blocker first; current production dry-run says `564` rows are auto-fixable and `orders.id=1845` is the lone manual follow-up row

**Step 2: Remove env fallback**
- change `context_processors.py` to canonical-only `ERP_ORDER_ENABLED`

**Step 3: Remove JS beta aliases**
- remove `ERP_BETA_ENABLED`, `__ERP_BETA_DRAFT_MODE`, `data-erp-beta-*` fallback from `erp-order-shared.js`
- remove beta fallback from `estimate-preview.js`

**Step 4: Remove inbound/template aliases**
- remove `open=erp-beta` acceptance
- remove `create_mode=ERP_BETA`
- remove backend placeholder/status suppressors that are no longer needed

**Step 5: Run focused verification**
- Run: `pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_shell_fragment_contract.py -q`
- Expected: PASS

**Step 6: Verify app/runtime**
- Run: `python -c "import app; print('APP_OK')"`
- Run: `python tools/harness/verify_result.py --json`
- Expected: `APP_OK`, verify_result success

### Task 4: P3 DB and Bootstrap Canonicalization

**Files:**
- Modify: `models.py`
- Modify: `foms/services/erp_order_flags.py`
- Modify: `scripts/migrations/safe_schema_migration.py`
- Modify: `scripts/ops/erp_build_step_runner.py`
- Modify: `run.py`
- Modify: `tests/domains/test_sqlite_startup_compat.py`
- Test: `tests/domains/test_app_init.py`
- Test: `tests/domains/test_app_bootstrap_contract.py`

**Step 1: Confirm DB-side evidence**
- all live DBs must have `is_erp_order` only
- no dual-column state
- legacy step keys must be either migrated or intentionally frozen

**Step 2: Remove model/helper legacy seam**
- remove `is_erp_beta` synonym
- remove helper fallback to `is_erp_beta`

**Step 3: Canonicalize startup/bootstrap**
- retire legacy repair paths in `safe_schema_migration.py`
- update `run.py` startup path
- retire or migrate `ERP_BETA` step-runner keys/logic

**Step 4: Update startup tests**
- rewrite SQLite/startup compatibility tests to canonical-only expectations

**Step 5: Run verification**
- Run: `pytest tests/domains/test_sqlite_startup_compat.py tests/domains/test_app_init.py tests/domains/test_app_bootstrap_contract.py -q`
- Expected: PASS

### Task 5: Final Verification and Closeout

**Files:**
- Modify: `docs/specs/2026-04-18-erp-beta-retirement_SPEC.md`
- Modify: `docs/AI_STATUS.md` if status materially changes

**Step 1: Full focused command set**
- Run: `python -c "import app; print('APP_OK')"`
- Run: `python tools/harness/verify_result.py --json`
- Run: `pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_sqlite_startup_compat.py tests/domains/test_app_init.py tests/domains/test_app_bootstrap_contract.py -q`

**Step 2: Manual smoke**
- `/add`
- `/edit/<id>`
- measurement dashboard
- shipment dashboard
- CS dashboard
- attachment/payment/draft flow

**Step 3: Residual search**
- confirm active runtime/product code has no unapproved `ERP_BETA`, `erp-beta`, `is_erp_beta` references

**Step 4: Closeout**
- update spec status and evidence summary

