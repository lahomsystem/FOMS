# Wave 4 Batch W4-B6 — Dashboard template namespace stabilization (winner: `production`)

> **batch ID:** W4-B6  
> **risk axis:** code / template  
> **winner_context:** `production`  
> **실행일:** 2026-04-14

## Scope lock

- **허용:** `templates/production/dashboard.html`, `templates/production/partials/*`, legacy `templates/erp_production_dashboard.html` 및 `templates/partials/erp_production_*.html` thin include/extends, 관련 테스트, 본 run record.  
- **금지:** shared shell (`erp_beta_js`, `erp_sub_nav`, `erp_mobile_shell`) 이동, 빈 `static/js/production`, giant script 분해.

## Inputs consumed

| # | 소스 |
|---|------|
| 1 | W4-B5 — `render_template('production/dashboard.html', ...)` |
| 2 | W4-B4 — winner `production` |

## Canonical template namespace

| 역할 | 경로 |
|------|------|
| primary dashboard body | `templates/production/dashboard.html` |
| partial family | `templates/production/partials/filters.html`, `filters_grid.html`, `mobile_filters.html`, `mobile_queue.html`, `modals.html`, `scripts.html`, `styles.html` |
| legacy primary wrapper | `templates/erp_production_dashboard.html` → `{% extends "production/dashboard.html" %}` (단일 줄) |
| legacy partial wrappers | 각 `templates/partials/erp_production_*.html` → `{% include 'production/partials/...' %}` 한 줄 |

## Wave 5 defer

- `partials/scripts.html` 등 내부 **대형 inline / 스크립트 핫스팟** 구조 재작성은 **하지 않음** — namespace·owner만 정리.

## FR19 decision

- 본문 단일 SoT: `templates/production/`; legacy 경로는 thin bridge만.

## Spec §4 delta summary

| 항목 | 값 |
|------|-----|
| product file delta | +`templates/production/dashboard.html`, +`templates/production/partials/*.html` |
| wrapper delta | 기존 `erp_production_*` 경로들 → include/extends-only |
| test delta | `test_production_dashboard_template_path_exists`, `test_legacy_erp_production_dashboard_is_thin_extends_wrapper`, `test_erp_production_page_shim_reexports_canonical_module` |
| new static dir | **없음** |

## Verification

| 검사 | 결과 |
|------|------|
| APP_OK | ✅ |
| verify_result.py --json | ✅ |
| Automated include/path | ✅ 위 테스트 3종 + 전체 `test_foms_namespace_imports.py` 138 passed |
| Manual smoke | **Equivalent:** pytest contract + APP_OK (브라우저 `/erp/production/dashboard`는 운영자 선택) |
| web+worker parity | **N/A** |

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 템플릿 본문은 `templates/production` 한 곳 |
| 2 | yes | legacy는 한 줄 include/extends |
| 3 | yes | 중복 본문 없음 |
| 4 | yes | dashboard + partial family가 한 context 네임스페이스 |
| 5 | yes | 증가는 namespace 정리에 필요한 만큼만 |
| 6 | N/A | |
| 7 | N/A | |
| 8 | yes | |
| 9 | yes | |
| 10 | yes | 구조만 |

## Wrapper / canonical / retirement metadata

| legacy path | canonical path | removal condition |
|-------------|----------------|-------------------|
| `templates/erp_production_dashboard.html` | `production/dashboard.html` | 외부 Jinja 참조가 모두 `production/`로 이전 시 |
| `templates/partials/erp_production_*.html` | `production/partials/*` | 동일 |

## Next batch

- **W4-B7** — defer register + closeout.
