# WR-P1 — Personal board adapter shell retirement

> **batch ID:** WR-P1  
> **risk axis:** structure / adapter shell  
> **실행일:** 2026-04-15  
> **상위 문서:** `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md` Program 2, `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md` WR-P1

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `foms/api/personal_board.py`, `foms/platform/blueprints.py`, runtime sentinel, 본 run record | `orders` shell, jobs string contract, storage singleton, high-risk cluster, packaging reopen |

## 2. Live truth before

- `apps/api/personal_board.py` held the `Blueprint`, `@login_required`, and `/summary` route shell.
- `foms/api/personal_board.py` already held the canonical response helper and policy imports.
- `foms/platform/blueprints.py` still imported `personal_board_bp` from `apps.api.personal_board`.

## 3. Implementation delta

### 3.1 Product file delta

- `foms/api/personal_board.py`
  - absorbed `personal_board_bp`
  - absorbed `@login_required` route binding for `/api/personal-board/summary`
  - now exports the full canonical surface (`personal_board_bp`, `api_summary`, `personal_board_summary_response`)
- `foms/platform/blueprints.py`
  - registry import source rerouted from `apps.api.personal_board` to `foms.api.personal_board`

### 3.2 Removal target

- `apps/api/personal_board.py` removed

### 3.3 Test file delta

- `tests/contracts/runtime/foms_namespace_surface_tests.py`
  - added WR-P1 sentinel asserting:
    - `apps.api.personal_board` no longer resolves
    - route decorators live on `foms.api.personal_board`
    - `foms/platform/blueprints.py` imports the canonical module only

## 4. Canonical target

- authoritative module: `foms/api/personal_board.py`
- legacy adapter retired: `apps/api/personal_board.py`

## 5. Verification

### 5.1 Automated

- `python -c "import app; print('APP_OK')"` -> pass
- `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "personal_board or wave8_remaining_direct_import_bridges_retired"` -> `3 passed`
- `python tools/harness/verify_result.py --json` -> `"success": true`

### 5.2 Lint

- `ReadLints` on edited files: no new WR-P1 error introduced
- residual workspace diagnostic remains at `tests/contracts/runtime/foms_namespace_surface_tests.py` unrelated to WR-P1 (`erp_automation.build_auto_tasks`)

## 6. Guardrail check

- thin wrapper 추가 없이 canonical module로 shell을 흡수했다.
- `app.py`, deploy, worker, alembic, packaging 경계는 건드리지 않았다.
- one-family-per-batch 원칙을 유지했다.
- removal condition 없는 신규 shim을 만들지 않았다.

## 7. Next legal batch

- `WR-O1` — `apps/api/orders/__init__.py` adapter shell
