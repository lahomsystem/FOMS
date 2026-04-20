# SLG-B2 — Template shell / error remediation (run record)

> 배치: `SLG-B2` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` §6.3)  
> 실행일: 2026-04-15

## 1. Scope / acceptance

- `templates/shared/layout.html` **retire** → `templates/partials/shared/{layout_head,layout_nav,layout_flash,layout_scripts}.html`로 분리.
- 각 활성 컨텍스트에 **`templates/<context>/layout.html`** 소유 (11개 컨텍스트).
- 모든 `{% extends "shared/layout.html" %}` → `{% extends "<context>/layout.html" %}`.
- `templates/errors/` **retire** → `templates/partials/http_errors/{error_404,error_500}.html`.
- `foms/platform/http.py`: `render_template("errors/...")` **금지** → `partials/http_errors/...`; `__build` 진단 문자열 동기화.

## 2. 증거

| 검증 | 결과 |
|------|------|
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k slg_literal_gap` | **8 passed, 3 failed** (실패 3 = §4.2–§4.4 foms subtree만; templates 게이트 전부 green) |
| `python -c "import app; print('APP_OK')"` | **APP_OK** |

## 3. 변경 요약

- 신규: `templates/partials/shared/layout_head.html`, `layout_nav.html`, `layout_flash.html`, `layout_scripts.html` (기존 `shared/layout.html`에서 기계적 분할).
- 신규: `templates/<ctx>/layout.html` — `ctx` ∈ admin, auth, channel, construction, cs, drawing, measurement, orders, production, shipment, wdcalculator.
- 신규: `templates/partials/http_errors/error_404.html`, `error_500.html`.
- 삭제: `templates/shared/layout.html`, `templates/shared/`, `templates/errors/` 전체.
- 수정: `foms/platform/http.py` (에러 템플릿 경로, `/__build` template 힌트).
- 수정: `templates/**/*.html` 중 기존 `extends shared/layout` 전부 컨텍스트별 경로로 갱신.

## 4. 3축 + GDM 감리 (요약)

| 축 | 결과 |
|----|------|
| A literal | `templates/shared|errors` 없음, `extends shared/layout` 없음, `render_template('errors/')` 없음 → **High 0** |
| B runtime | 레이아웃 include 체인 동일 의미; APP_OK → **High 0** |
| C proof | pytest slg 8/11 pass (의도된 foms drift 3건 제외 전부 green) → **High 0** |
| GDM | 계획 §6.3 shell retire + HTTP error 경로 정리와 일치 → **High 0** |

**Medium:** 0 (본 배치 범위 내).

## 5. 다음

- `SLG-B3` — `foms/web/*` 흡수 I (closed-set `foms/web` 정렬).
