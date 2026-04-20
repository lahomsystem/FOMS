# Wave 4 Batch W4-B1 — Pilot contract freeze (`cs`)

> **batch ID:** W4-B1  
> **risk axis:** docs / contract  
> **pilot_context:** `cs` (FR20 key: `completion`)  
> **실행일:** 2026-04-13

## Scope lock

- **허용:** 본 run record만.  
- **금지:** runtime code, `foms/web/*`, `templates/*`, pilot 외 context.

## Inputs consumed

| # | 소스 | 메모 |
|---|------|------|
| 1 | `docs/plans/2026-04-13-wave4-batch0-readiness-gate-run-record.md` | pilot `cs`, parameter sheet |
| 2 | `apps/erp_completion_page.py` (pre-move) | live route·render |
| 3 | `templates/erp_completion_dashboard.html` | primary template |
| 4 | `templates/partials/erp_completion_styles.html`, `erp_completion_scripts.html` | partial family |

## Wave key normalization

| 키 | 값 |
|----|-----|
| registry lane | ERP HTML page — completion / CS pilot |
| spec domain | CS / completion (§2.3, §2.9) |
| FR20 context key | `completion` |

## Public contract table (routes)

| route path | methods | auth | blueprint (symbol / import name) | endpoint name | `render_template` target (post W4-B3) |
|------------|---------|------|-----------------------------------|---------------|----------------------------------------|
| `/erp/completion` | GET | `@login_required` | `erp_completion_page` / `erp_completion_page_bp` | `erp_completion_dashboard` | `cs/completion_dashboard.html` |

## Template / partial contract table

| 항목 | 경로 |
|------|------|
| primary template (canonical, W4-B3) | `templates/cs/completion_dashboard.html` |
| legacy primary wrapper (W4-B3) | `templates/erp_completion_dashboard.html` → `{% extends "cs/completion_dashboard.html" %}` |
| style partial | `templates/partials/erp_completion_styles.html` (include from canonical body; Wave 4에서 경로 유지 — giant split 금지) |
| script partial | `templates/partials/erp_completion_scripts.html` (동일) |
| `url_for` / static | `erp_construction_page.erp_construction_dashboard`, `order_pages.index`; 스크립트 내 API는 기존 `partials/erp_completion_scripts.html` 유지 |
| mobile/desktop shell | `layout.html` 확장; 조건부 `partials/erp_mobile_shell.html`; **이동 금지** |
| sub-nav | `{% include 'partials/erp_sub_nav.html' %}` + `erp_sub_nav_active='completion'` |

## New static directory decision

- **생성하지 않음** — dedicated `static/js/cs` 또는 `static/css/cs` 없음; 기존 partial·전역 static만 사용 (계획 §1.2.1 FR9).

## Hidden coupling inventory

| 유형 | 내용 |
|------|------|
| shared layout | `layout.html` |
| menu / navigation | `erp_sub_nav.html`, 모바일 셸의 completion 링크는 `erp_completion_page.erp_completion_dashboard` 유지 |
| API lane | `erp_completion_scripts.html`이 `/api/orders/*` 등 호출 — **Wave 4에서 API 변경 없음** |
| giant inline | scripts/styles는 partial에 분리됨; **추가 분해는 Wave 5** |

## FR19 decision

- **extend:** canonical `foms/web/cs/completion_dashboard.py` + canonical template namespace `templates/cs/`  
- **merge:** legacy `apps/erp_completion_page.py` → thin shim (Measurement와 동일)  
- **delete:** 없음 (동일 본문 이중 유지 금지 — thin wrapper만)

## Canonical target shape

- **single module:** `foms/web/cs/completion_dashboard.py` — Blueprint + 단일 뷰만 있어 package 분할 불필요.  
- **README:** FR20 미충족(단일 module) — `foms/web/cs/README.md` **생성 안 함**.

## Spec §4 delta summary (본 배치)

| 항목 | 값 |
|------|-----|
| product file delta | 0 (docs-only) |
| wrapper delta | 0 |
| test delta | 0 |
| canonical target | `foms/web/cs/completion_dashboard.py` + `templates/cs/completion_dashboard.html` (후속 배치) |

## Verification

| 검사 | 결과 |
|------|------|
| docs-only | ✅ |
| route/template fields | ✅ |
| new static dir explicit | ✅ 없음 |
| Direction Lock | ✅ 아래 |

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 공개 계약 고정으로 SoT 명확 |
| 2 | yes | W4-B0 parameter sheet와 live 코드 일치 |
| 3 | yes | 코드 변경 없음 |
| 4 | yes | 단일 context·단일 primary surface |
| 5 | yes | 파일 증가 없음 (본 배치) |
| 6 | N/A | — |
| 7 | N/A | README 미생성 결정 |
| 8 | yes | 표가 과도해지지 않도록 테이블로 구조화 |
| 9 | yes | 경계 명시 |
| 10 | yes | 문서만 |

## FR20 / README gate

- 단일 canonical module 예정 → **README 불필요**.

## Test footprint decision

- 본 배치 테스트 없음; W4-B2에서 import shim 테스트 추가.

## Next batch

- **W4-B2** — `foms/web/cs/completion_dashboard.py` + `apps/erp_completion_page.py` thin shim.
