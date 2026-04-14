# Wave 4 Batch W4-B5 — Dashboard page owner canonicalization (winner: `production`)

> **batch ID:** W4-B5  
> **risk axis:** code / page owner  
> **winner_context:** `production`  
> **실행일:** 2026-04-14

## Scope lock

- **허용:** `foms/web/production/__init__.py`, `foms/web/production/dashboard.py`, `apps/erp_production_page.py` shim, 본 run record.  
- **금지:** `construction` 모듈, template 경로 변경, `foms/platform/blueprints.py`, API 본편.

## Inputs consumed

| # | 소스 |
|---|------|
| 1 | `docs/plans/2026-04-13-wave4-batch4-dashboard-family-lock-run-record.md` — winner `production` |

## Wave key normalization

| 키 | 값 |
|----|-----|
| FR20 context key | `production` |

## Public contract table (routes — freeze)

| route path | methods | auth | blueprint | endpoint | render target (post W4-B6) |
|------------|---------|------|-----------|----------|----------------------------|
| `/erp/production/dashboard` | GET | `@login_required` | `erp_production_page` | `erp_production_dashboard` | `production/dashboard.html` |

## Hidden coupling

- `foms.services.erp_display`, `erp_order_detail`, `erp_permissions`, `erp_policy` — **shared service**; Wave 4에서 이동/정본화 재개하지 않음.

## FR19 decision

- **merge:** `apps/erp_production_page.py` → module alias shim → `foms.web.production.dashboard`
- **extend:** canonical page logic 전부 `foms/web/production/dashboard.py`

## Spec §4 delta summary

| 항목 | 값 |
|------|-----|
| product file delta | +`foms/web/production/__init__.py`, +`foms/web/production/dashboard.py` (SoT) |
| wrapper delta | `apps/erp_production_page.py` → 6-line shim |
| test delta | `tests/test_foms_namespace_imports.py` — production shim + template path (W4-B6 정합 후 추가 assertion) |
| canonical target | `foms/web/production/dashboard.py` |
| removal target | 장기: `apps.erp_production_page` 직접 import 소비자 축소 후 제거 검토 |
| local README | **없음** (단일 dashboard module — FR20 미충족) |

## Verification

| 검사 | 결과 |
|------|------|
| APP_OK | ✅ |
| verify_result.py --json | ✅ |
| tests/test_foms_namespace_imports.py | ✅ |
| tests/test_menu_config.py | ✅ (5 passed) |
| web+worker parity | **N/A** — blueprints 등록 경로 불변 |

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 생산 대시보드 SoT 단일 파일 |
| 2 | yes | legacy 이름은 shim으로만 |
| 3 | yes | 서비스 레이어는 건드리지 않고 page owner만 이동 |
| 4 | yes | `dashboard.py` 단일 chunk |
| 5 | yes | 최소 파일 증가 |
| 6 | N/A | |
| 7 | N/A | README 불필요 |
| 8 | yes | |
| 9 | yes | |
| 10 | yes | 기능 변경 없음 |

## Next batch

- **W4-B6** — `templates/production/*` + legacy thin wrappers.
