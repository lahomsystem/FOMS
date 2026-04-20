# SLG-B3 — Web absorption I (run record)

> 배치: `SLG-B3` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` §6.4)  
> 실행일: 2026-04-15

## 1. Scope / acceptance

- `foms/web/dashboards` **삭제** — `dashboards_bp` 및 `/regional_dashboard`, `/metropolitan_dashboard`, `/self_measurement_dashboard` 구현을 **`foms/web/measurement/dashboard.py`**로 흡수.
- `foms/web/order_pages`, `order_edit`, `erp_dashboard`, `erp_history_page` **삭제** — 구현은 기존 복사본 기준 **`foms/web/orders/{listing,edit,dashboard,history}.py`** 단일 패키지로 정렬.
- `foms/platform/blueprints.py`: `dashboards_bp`는 `foms.web.measurement`에서 import; 주문/대시보드/히스토리 blueprint는 `foms.web.orders`에서 import (중복 import 제거).
- `tests/contracts/runtime/foms_namespace_surface_tests.py`: 위 모듈 경로 문자열·import 계약 갱신.
- §4.2 `foms/web` closed-set은 **아직 green 아님** (extra `erp`, `excel_import` 등은 SLG-B4+ 대상).

## 2. 증거

| 검증 | 결과 |
|------|------|
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "order_pages_uses_canonical or order_edit_uses_canonical or erp_pages_use_canonical_erp_permissions or erp_permissions_lazy_callers or erp_pages_use_canonical_erp_display or erp_display_lazy_callers or erp_dashboard_uses_canonical_erp_policy or strict_canonical_orders_dashboard"` | **8 passed** |
| `pytest … -k slg_literal_gap` | **8 passed, 3 failed** (§4.2–§4.4 foms subtree drift — 의도된 미해결; templates·partial 게이트 green) |
| `python -c "import app; print('APP_OK')"` | **APP_OK** |
| `python tools/harness/verify_result.py --json` | **success: true** |

## 3. 변경 요약

- `foms/web/measurement/dashboard.py`: `dashboards_bp` + 3개 public dashboard 라우트 추가.
- `foms/web/measurement/__init__.py`: `dashboards_bp`, `erp_measurement_dashboard_bp` export.
- `foms/web/orders/__init__.py`: `listing`, `edit`, `dashboard`, `history`, `trash`에서 blueprint·헬퍼 재수출.
- `foms/platform/blueprints.py`: `foms.web.dashboards` 제거; `orders` import 단일 블록으로 통합.
- 삭제된 디렉터리: `foms/web/dashboards/`, `order_pages/`, `order_edit/`, `erp_dashboard/`, `erp_history_page/` (구현은 `orders/*`, `measurement/dashboard.py`에 존재).
- 테스트: `foms.web.orders.*`·`orders/dashboard.py` 기준으로 계약 테스트 정렬.

## 4. 3축 + GDM 감리 (요약)

| 축 | 결과 |
|----|------|
| A literal | 제거 대상 5개 `foms/web/*` 패키지 디렉터리 없음; 구현이 허용 경로(`orders`, `measurement`)로만 존재 → **High 0** |
| B runtime | `dashboards_bp`·주문 BP 등록 순서 유지; APP_OK → **High 0** |
| C proof | 집중 계약 8/8; SLG 8 pass + 의도된 subtree 3 fail → **High 0** |
| GDM | §6.4 흡수 I (dashboards→measurement, 주문 surface→orders)와 일치 → **High 0** |

**Medium:** 0 (본 배치 범위 내).

## 5. 다음

- `SLG-B4` — Web absorption II (남은 extra `foms/web/*` 정렬).
