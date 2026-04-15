# SFC-B7 — Template namespace relocation

> Batch: `SFC-B7`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.10`)  
> 선행: `SFC-B6` (ledger·target freeze)

## 1. 목표 달성

- 루트 `templates/*.html` **0개** — B6 ledger대로 `orders/`, `measurement/`, `admin/`, `auth/`, `channel/`, `wdcalculator/`, `shared/`, `errors/`로 물리 이동 완료.
- `render_template` 및 `{% extends %}` 호출 문자열을 namespaced path로 정렬.
- **SG7 = 0** 계약: `test_strict_canonical_templates_root_has_no_html_files` 추가 (`foms_namespace_surface_tests.py`).

## 2. 제품 코드 변경 요약

| 영역 | 내용 |
|------|------|
| `apps/` | `order_pages` index, `auth`, `user_pages`, `dashboards`, `excel_import`, `storage_dashboard` 등 템플릿 경로 갱신 |
| `foms/web/admin/routes.py` | `admin.html` → `admin/admin.html` |
| `foms/web/orders/trash.py` | `trash.html` → `orders/trash.html` |
| `foms/platform/http.py` | `errors/error_404|500.html`, 디버그 JSON `templates/shared/layout.html` |
| `foms/api/erp_map.py` | `measurement/map_view.html` |
| `foms/web/wdcalculator/planner.py` | `wdcalculator/wdplanner*.html` |
| `foms/api/chat/routes_pages.py` | `channel/chat.html` |
| `templates/**/*.html` | `{% extends "shared/layout.html" %}` 일괄 (one-shot 스크립트 후 삭제) |

## 3. 테스트·계약

- `tests/domains/test_map_view_manager_contract.py`: `templates/measurement/map_view.html` 경로로 갱신.
- `test_strict_canonical_templates_root_has_no_html_files`: SG7 고정.

## 4. 도구 위생

- 원샷 `tools/_b7_extends_replace.py` 삭제 — `test_strict_canonical_tools_taxonomy` (루트 `tools/` 비파일만 허용) 준수.

## 5. 검증 (증거)

| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests` | **575 passed** (전체) |

## 6. 비범위

- `backups/**` 내 스냅샷은 갱신하지 않음 (기존 배치와 동일).
