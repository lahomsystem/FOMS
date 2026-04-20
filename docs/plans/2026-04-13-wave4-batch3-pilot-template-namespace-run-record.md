# Wave 4 Batch W4-B3 — Pilot template namespace stabilization (`cs`)

> **batch ID:** W4-B3  
> **risk axis:** code / template  
> **pilot_context:** `cs`  
> **실행일:** 2026-04-14

## Scope lock

- **허용:** `templates/cs/*`, legacy `templates/erp_completion_dashboard.html` thin extends, 관련 테스트, 본 run record.  
- **금지:** shared shell partial 이동, 빈 `static/js/cs`, giant inline 분해, API 변경.

## Inputs consumed

| # | 소스 |
|---|------|
| 1 | W4-B1 contract — canonical primary = `templates/cs/completion_dashboard.html` (dashboard 파일명 가정 금지; **completion** surface에 맞춘 concrete path) |
| 2 | W4-B2 — `render_template('cs/completion_dashboard.html', ...)` |

## Wave key normalization

| 키 | 값 |
|----|-----|
| FR20 context key | `completion` |

## Public contract table (templates)

| 항목 | 경로 |
|------|------|
| canonical primary | `templates/cs/completion_dashboard.html` |
| legacy primary wrapper | `templates/erp_completion_dashboard.html` → 한 줄 `{% extends "cs/completion_dashboard.html" %}` |
| partials | 기존 `templates/partials/erp_completion_*.html` — 본문 중복 없이 include 경로 유지 |

## Hidden coupling

- 스타일/스크립트 partial은 여전히 `partials/` — giant 분해는 **Wave 5**.

## FR19 decision

- **merge:** 본문 단일 SoT → `templates/cs/`; legacy는 extends-only.

## Spec §4 delta summary

| 항목 | 값 |
|------|-----|
| product file delta | +`templates/cs/completion_dashboard.html` |
| wrapper delta | `erp_completion_dashboard.html` thin |
| test delta | template path + thin-wrapper 줄 단위 assertion |
| canonical target | `templates/cs/completion_dashboard.html` |
| new static dir | **없음** |

## Verification

| 검사 | 결과 |
|------|------|
| APP_OK | ✅ |
| verify_result.py --json | ✅ |
| Automated | `test_legacy_erp_completion_dashboard_is_thin_extends_wrapper`, `test_cs_completion_template_path_exists` 등 |
| Manual smoke | **Equivalent:** focused pytest + APP_OK로 렌더 경로 회귀 대체 (로컬 브라우저 스모크는 운영자 선택) |
| web+worker parity | **N/A** — worker entry 미변경 |

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 템플릿 SoT 단일 경로 |
| 2 | yes | wrapper는 extends 한 줄만 |
| 3 | yes | 복제 대신 extend |
| 4 | yes | completion_dashboard 단일 본문 chunk |
| 5 | yes | 증가는 cs 네임스페이스+wrapper 최소 |
| 6 | N/A | |
| 7 | N/A | |
| 8 | yes | |
| 9 | yes | |
| 10 | yes | 구조만 |

## Next batch

- **W4-B4** — dashboard family next lock (`production` vs `construction`).
