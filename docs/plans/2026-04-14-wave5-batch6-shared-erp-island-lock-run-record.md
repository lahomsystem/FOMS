# Wave 5 Batch W5-B6 — Shared ERP front-end island lock

> **batch ID:** W5-B6  
> **risk axis:** docs / truth  
> **실행일:** 2026-04-14  
> **attempt:** 1 — completed  
> **live evidence snapshot:** `templates/partials/erp_beta_js.html`, `templates/add_order.html`, `templates/edit_order.html`, `static/js/erp/beta-shared.js`, `templates/layout.html`, `templates/regional_dashboard.html`, `templates/partials/erp_dashboard_styles.html`, `templates/partials/erp_dashboard_scripts.html`

## Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record 생성 | runtime code edit |
| shared ERP island queue / pilot lock 문서화 | `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css` code touch |
| backlog ordering·why-not-now 명시 | spec/archive reference wiring 수정 |

## Inputs consumed

1. `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md` §5.7
2. `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md`
3. `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md`
4. `docs/plans/2026-04-14-wave5-batch5-wdcalculator-pricing-core-run-record.md`
5. `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md`
6. `templates/add_order.html` — `erp_beta_js.html` include + add-order globals injection
7. `templates/edit_order.html` — `erp_beta_js.html` include + edit-order globals injection
8. `templates/partials/erp_beta_js.html` — shared form partial live body
9. `static/js/erp/beta-shared.js` — extracted shared helper surface
10. `templates/layout.html`, `templates/regional_dashboard.html`, `templates/partials/erp_dashboard_styles.html`, `templates/partials/erp_dashboard_scripts.html` — blast-radius comparison

## Current blast radius comparison

| Surface | Current live shape | Blast radius | W5 verdict |
|---------|--------------------|--------------|------------|
| `templates/partials/erp_beta_js.html` | add/edit order에서만 include; 상단에서 `static/js/erp/beta-shared.js` 1회 로드 후 shared inline logic 실행 | **bounded** — order form island only | **pilot lock** |
| `static/js/erp/beta-shared.js` | ERP Beta helper globals를 단일 static file에 노출 | bounded helper support | pilot dependency |
| `templates/partials/erp_dashboard_scripts.html` | `core/gateway/attachments/drawing/quest/detail_dom` 6 partial fan-out | dashboard family 전체 | defer |
| `templates/partials/erp_dashboard_styles.html` | 대형 inline style block | dashboard family 전체 | defer |
| `templates/regional_dashboard.html` | `layout.html` 확장 + 자체 대형 inline style/script/page markup | regional page 전체 | defer |
| `templates/layout.html` | 다수 페이지 공통 shell + global CSS/JS 로딩 | **global shell** | defer |
| `static/css/erp-pro.css` + `static/css/erp-pro/*` | global ERP design-system entry | cross-page CSS | defer |

## Shared ERP island queue table

| Lane | Evidence | Bounded before shell? | Why / note |
|------|----------|------------------------|------------|
| `erp_beta_js.html` shared-form island | `add_order.html` line 771 include, `edit_order.html` line 1424 include, `beta-shared.js` static helper | **YES** | add/edit order 2개 surface에만 결합. live shape가 이미 “shared partial + one static helper”로 수렴 중 |
| dashboard partial family | `erp_dashboard_scripts.html` 6-partial include, `erp_dashboard_styles.html` large inline style | **NO** | ERP dashboard 전체와 attachments/drawing/detail DOM을 함께 물고 있음 |
| regional dashboard | `regional_dashboard.html` extends `layout.html` | **NO** | page-local이지만 여전히 layout/global nav shell에 얹힌 대형 page |
| main layout shell | `layout.html` | **NO** | 최고 blast radius. Wave 5 pilot보다 앞세우면 stop risk 상승 |
| ERP CSS system | `erp-pro.css` entry + slice folder | **NO** | selector / shared visual contract 범위가 넓어 pilot 선행이 필요 |

## Pilot lock

**결론:** Wave 5의 only executable shared-form pilot은 **`templates/partials/erp_beta_js.html`** 이다.

### Lock 근거

1. `erp_beta_js.html`은 **`add_order.html` / `edit_order.html` 두 템플릿에서만** include 된다.
2. add/edit 양쪽 모두 partial include 직전에 `ORDER_ID`, `ERP_BETA_ENABLED`, `USE_DIRECT_UPLOAD`, `window.__ERP_BETA_DRAFT_MODE`, `window.__ERP_DRAFT_ENDPOINT`를 주입하는 구조라서 pilot 경계가 명확하다.
3. partial 상단은 이미 `static/js/erp/beta-shared.js`를 로드하므로, future canonical shape를 향한 진입점이 존재한다.
4. 반대로 `layout.html`, dashboard partial family, `regional_dashboard.html`, CSS system은 page-global 또는 dashboard-family blast radius를 갖기 때문에 Wave 5 mainline pilot보다 먼저 열 수 없다.

## Shared shell / CSS backlog ordering

> `erp_beta` pilot 성공 이후에도 **Wave 5 mainline 안에서 code-touch 하지 않는다**. 아래 순서는 defer register/후속 continuation 설계를 위한 ordering only.

1. **dashboard partial family** — `erp_dashboard_styles.html` + `erp_dashboard_scripts*.html`
2. **regional dashboard** — `regional_dashboard.html`
3. **main layout shell** — `layout.html`
4. **ERP design-system CSS** — `erp-pro.css` + `erp-pro/*`
5. **legacy global CSS** — `style.css`

### Why this order

- dashboard partial family가 shell보다 bounded하고, future continuation 시 dashboard-only slice로 먼저 고립하기 쉽다.
- `regional_dashboard.html`은 large page지만 still single-page lane이라 `layout.html` global shell보다는 국소적이다.
- `layout.html`은 global nav/realtime/header contract를 먹는 최고 blast radius라 가장 뒤로 미룬다.
- CSS system은 selector rename / visual regression risk 때문에 shell/page truth가 잠긴 뒤 다루는 편이 안전하다.

## Why-not-now / required prep preview

| Lane | why not now | required prep | suggested next batch type |
|------|-------------|---------------|----------------------------|
| `erp_beta_js.html` | not deferred; Wave 5 mainline pilot | W5-B7 contract freeze | docs-first → code |
| dashboard partial family | family blast radius가 크고 attachments/drawing/detail DOM이 얽혀 있음 | family contract map + page usage inventory | docs-first continuation |
| `regional_dashboard.html` | layout dependency + page-local giant inline | page-only contract inventory | docs-first continuation |
| `layout.html` | global shell / realtime / notification coupling | shell contract ADR 수준 prep | separate high-risk track |
| `erp-pro.css` / `style.css` | global selector/visual regression risk | selector inventory + visual regression strategy | CSS-only continuation |

## Stop / partial-closeout check

| 조건 | 결과 |
|------|------|
| `erp_beta_js.html`을 bounded shared-form island로 lock 가능한가 | **PASS** |
| shell/layout을 pilot보다 먼저 열어야 한다는 증거가 있는가 | **NO** |
| W5-B9 partial closeout 강제 사유가 발생했는가 | **NO** |

→ **W5-B7 진행 가능.**

## Verification

| 검사 | 결과 |
|------|------|
| docs-only consistency | 통과 — 계획서 §5.7 요구 산출물 3종(queue table, pilot lock, backlog ordering) 모두 기록 |
| live include/use-site check | 통과 — `erp_beta_js.html` include는 add/edit only |
| shell backlog comparison | 통과 — layout/regional/dashboard/CSS family가 pilot보다 넓은 blast radius로 분리됨 |
| APP_OK / verify_result | N/A (docs-only batch) |

## Direction Lock (10문항)

| # | Y/N | 한 줄 근거 |
|---|-----|------------|
| 1 | **Y** | shared ERP pilot SoT를 `erp_beta_js.html`로 잠갔다 |
| 2 | **Y** | shell/CSS backlog를 pilot과 분리해 split-brain을 줄였다 |
| 3 | **Y** | docs-only; runtime/code 증가 없음 |
| 4 | **Y** | `erp_beta_js.html`만 executable pilot로 boundedness를 명시했다 |
| 5 | **Y** | global shell을 앞당기지 않았다 |
| 6 | **Y** | backlog ordering이 why-not-now와 함께 기록됐다 |
| 7 | **Y** | add/edit 양쪽 include 및 globals injection 근거를 남겼다 |
| 8 | **Y** | `beta-shared.js` existing static helper를 pilot dependency로 인정했다 |
| 9 | **Y** | partial-closeout stop reason은 발생하지 않았다 |
| 10 | **Y** | 다음 legal batch를 W5-B7로 명확히 넘겼다 |

## Changes made

- `docs/plans/2026-04-14-wave5-batch6-shared-erp-island-lock-run-record.md` 생성 (본 파일)

## product / wrapper / test delta

| 구분 | delta |
|------|-------|
| product | 없음 |
| wrapper | 없음 |
| test | 없음 |

## README update 여부

- 없음 (docs-only batch)

## Outcome

**PASS — W5-B6 complete. `erp_beta_js.html` is locked as the only executable shared-form pilot.**
