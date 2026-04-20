# Wave 5 Batch W5-B0 — Readiness gate + island queue lock

> **batch ID:** W5-B0  
> **risk axis:** docs / truth  
> **실행일:** 2026-04-14  
> **live evidence snapshot:** repo root `C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS` (glob + line-count + spot-read templates)

## Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record만 생성/갱신 | product/runtime 코드 변경 |
| | `docs/ARCHIVE_INDEX.md`, controlling spec §5 reference wiring (W5-B9 전용) |
| | W5-B1~W9 run record 선제 스캐폴드 |

## Inputs consumed

| # | 문서 / 증거 | 상태 |
|---|-------------|------|
| 1 | `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` | Wave 3 closeout — 상위 handoff로 계획서 §2.1에 인용 (본 세션에서는 파일 본문 미재검, Wave 5는 front-end만) |
| 2 | `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` | **full closeout** — defer register·continuation shortlist 소비 |
| 3 | `docs/plans/2026-04-13-wave4-web-page-slice-migration-execution-plan.md` | Wave 4 선행 완료 전제 |
| 4 | `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md` | governance 규칙 |
| 5 | `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md` | Step 6 threshold baseline (2026-04-10 스냅샷) |
| 6 | `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md` | WDCalculator 선례·금지 패턴 |
| 7 | `docs/context/COMPACT_CHECKPOINT.md` | chunk-first·host-bootstrap 증식 금지 합의 |
| 8 | **Live** `templates/wdcalculator/partials/wdcalculator_scripts_config.html`, `wdcalculator_scripts.html` | 스크립트 태그·순서 증거 |
| 9 | **Live** `glob static/js/wdcalculator/*.js` | **56**개 모듈 파일 |
| 10 | **Live** `templates/partials/erp_beta_js.html`, `templates/layout.html` line count | 아래 drift 표 |

## Context normalization keys (queue rows)

| Island lane | Registry / surface (evidence) | Spec domain (controlling spec) | FR20 / note |
|-------------|-------------------------------|----------------------------------|-------------|
| WDCalculator | `wdcalculator_scripts_config.html` + `wdcalculator_scripts.html` + `static/js/wdcalculator/*` | Wave 5 §2.3 Tier 1 | Local README gate는 W5-B1 이후 |
| ERP Beta shared form | `erp_beta_js.html` + add/edit order templates | Wave 5 §2.3 Tier 2 | W5-B7~B8에서만 code |
| Main ERP shell | `layout.html` | Tier 3 | W5-B9 defer만 |
| ERP dashboard partials | `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html` | Tier 3 | W5-B9 defer만 |
| Regional dashboard | `regional_dashboard.html` | Tier 3 | W5-B9 defer만 |
| ERP design-system CSS | `static/css/erp-pro.css` + `static/css/erp-pro/*.css` | Tier 4 | W5-B9 defer (logical org) |
| Measurement JS | `static/js/measurement/dashboard.js` | §2.3.1 | classify only, mainline 자동 미포함 |
| WAM attachments | `static/js/wam/attachments.js` | §2.3.1 | classify only |
| Legacy global CSS | `static/css/style.css` | §2.3.1 | low priority defer |

## Drift — Step 6 inventory (2026-04-10) vs live (2026-04-14 evidence)

| Surface | Inventory (rows/lines) | Live evidence | Drift 요약 |
|---------|-------------------------|---------------|------------|
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | ~3493 lines | **262** lines (PowerShell `Measure-Object -Line`) | 인라인 거대 partial이 이미 정적 JS로 이전됨. Step6 표는 **과거 스냅샷**; Wave 5는 **config + thin partial + `static/js/wdcalculator/*`** 기준으로 재잠금. |
| `templates/partials/erp_beta_js.html` | ~2516 lines | **2300** lines | 여전히 Tier 2 giant monolith; 소폭 감소·편차 가능. |
| `templates/layout.html` | ~2196 lines | **2196** lines | 스냅샷과 일치 (Tier 3 shell). |
| `static/css/erp-pro.css` | ~3595 lines (monolith) | **11** lines (`@import`만) + `static/css/erp-pro/*.css` | 인벤토리는 단일 파일 기준; **live는 이미 logical slice entry**. Wave 5는 **selector rename 없이 org 유지** 원칙과 충돌 없음. |
| `static/js/wdcalculator/*.js` | (inventory는 JS threshold만 별도) | **56** 파일 | four-chunk **canonical 파일명** (`composition.js` 등)은 **아직 없음** — W5-B1에서 map 확정, W5-B2~B5에서 merge/extend로 생성·수렴. |

## Authoritative island queue (mainline vs defer)

| Lane | Tier | Wave 5 mainline? | 근거 (live + 계획서) |
|------|------|------------------|----------------------|
| **WDCalculator four-chunk** | 1 | **YES — first executable** | 56개 모듈 + `wdcalculator_scripts_config.html` 순서; `COMPACT_CHECKPOINT`와 계획 §2.5가 WDC first 고정. |
| **erp_beta_js shared-form** | 2 | **YES — WDC 이후 단일 pilot** | Wave 4 defer에 shell·beta 언급; bounded add/edit 공용. **Canonical static chunk map은 W5-B6~B8에서만 잠금** (본 batch는 pilot 순서·boundedness만). |
| **layout.html** | 3 | **NO — defer (W5-B9 register)** | 계획 §1.1·§2.5: global shell은 pilot 후보 아님. |
| **regional_dashboard.html** | 3 | **NO — defer** | 동일. |
| **erp_dashboard_styles / erp_dashboard_scripts\*** | 3 | **NO — defer** | dashboard shell family. |
| **erp-pro.css + erp-pro/** | 4 | **NO — defer** | logical org; W5 mainline code batch 제외. |
| **measurement/dashboard.js** | §2.3.1 | **NO — classify only** | 계획 §2.3.1 자동 mainline 금지. |
| **wam/attachments.js** | §2.3.1 | **NO — classify only** | 동일. |
| **style.css** | §2.3.1 | **NO — low defer** | 동일. |
| **Python backend hotspots** (orders.py, chat, etc.) | — | **OUT OF SCOPE** | Wave 3/백엔드 트랙; Wave 5 front-end island만. |

### Wave 4 closeout defer lanes — explicit mapping (front-end queue 밖)

Wave 4 `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md`에 나열된 **페이지 슬라이스·레인** 중 아래는 **Wave 5 front-end island mainline에 포함하지 않는다** (누락이 아니라 **범위 밖 명시**).

| Wave 4 언급 레인 | Wave 5 본 queue에서의 위치 |
|------------------|---------------------------|
| drawing | **OUT OF SCOPE** (별도 페이지/트랙; Wave 5 §2.3 front-end Tier 1–2와 무관) |
| shipment-* | 동일 |
| as (after-sales 등) | 동일 |
| construction | 동일 |
| main ERP shell, regional | 위 표 **Tier 3 defer** 행과 동일 |

→ “Verification”의 “Wave 4 defer 반영”은 **프론트 큐 + 범위 밖 표**로 추적 가능하도록 본 절에서 고정한다.

## Mainline ordering lock (authoritative)

Wave 5 **실행 순서**는 아래로 고정한다 (계획서 §2.5 + §4.1과 동일).

1. `wdcalculator-composition` → **W5-B2**
2. `wdcalculator-primary-form` → **W5-B3**
3. `wdcalculator-estimate-lifecycle` → **W5-B4**
4. `wdcalculator-pricing-core` → **W5-B5**
5. `erp-beta-shared-form` (pilot) → **W5-B6** (lock) → **W5-B7** (freeze) → **W5-B8** (rebaseline)
6. **Shell/CSS defer register + closeout** → **W5-B9**

**금지:** `layout` / regional / dashboard shell / `erp-pro.css` mainline을 WDCalculator 앞에 두는 것 (drift).

## WDCalculator provisional four-chunk disposition refresh (evidence-based)

> 아래는 **W5-B0**에서 live 파일 목록(56)과 `wdcalculator_scripts_config.html` 상단 순서를 근거로 한 **provisional** 수령 방향이다. **권위 있는 four-chunk map은 W5-B1**에서 전체 `*.js` sweep 후 supersede.
>
> **Overlap rule (provisional only):** 동일 모듈이 두 열에 예시로 등장할 수 있다(예: `primary-ui-bootstrap`). 이는 **아직 단일 chunk 소유권이 확정되지 않았음**을 뜻하며, **이중 로드·신규 wrapper 추가로 해결하지 않는다.** W5-B1 matrix에서 각 파일을 정확히 하나의 `keep` / `merge` / `retire-later`로만 분류하고, W5-B2~B5는 **delete → merge → extend → add**로 기존 `*host-bootstrap.js` 밴드를 **청산**하는 것이 목표다(신규 `*-host-bootstrap.js` 금지와 합치).

| Canonical chunk | Target file (provisional) | 대표 live merge 대상 (파일명 기준, 예시) |
|-----------------|---------------------------|----------------------------------------|
| **composition** | `static/js/wdcalculator/composition.js` (신규 또는 기존 확장) | `early-bootstrap`, `late-bootstrap`, `startup-init`, `terminal-init`, `sidebar-bootstrap`, `primary-ui-bootstrap`, `catalog-buttons-*`, `coupon-search-render-*`, `loading-database-*`, `notes-ui-*`, `post-mutation-ui-*`, `products-editing-*`, `estimates-early-*`, `totals-startup-terminal-*`, `*host-bootstrap.js` band |
| **primary-form** | `static/js/wdcalculator/primary-form.js` | `base-components-ui`, `notes-ui`, `coupon-display-helpers`, `additional-options-ui`, `product-catalog-ui`, `add-option-button`, `calculate-button`, `primary-ui-bootstrap` (일부는 composition과 경계 협상) |
| **estimate-lifecycle** | `static/js/wdcalculator/estimate-lifecycle.js` | `sidebar-estimates`, `search-results-load`, `render-estimates-list`, `order-match-ui`, `refresh-after-save`, `reset-input-form-keep-customer`, `load-estimate-to-input-form`, `load-saved-estimate-to-form`, `save-estimate`, `add-estimate`, `estimate-list-events`, `estimate-mutation-bridge`, `loading-state`, `current-database-estimate-id`, `products-state`, `editing-estimate-id`, `estimates-state`, `url-bootstrap` |
| **pricing-core** | `static/js/wdcalculator/pricing-core.js` | `current-estimate-math`, `estimate-totals`, `calculation-resolvers`, `total-estimates-display`, `current-estimate-orchestration`, `coupon-shipping-wiring` |

**Cross-cutting (four-chunk 전부와 맞닿음 — W5-B1 matrix에서 반드시 단일 disposition)**  
`shared.js`, `layout-sync-wiring.js`, `unsaved-exit-guard.js` — config에서 **최상단 로드**; chunk 소유권은 `keep` vs 한 chunk `merge` 중 하나로만 잠글 것.

## Shared shell / CSS backlog preview (W5-B9 전 — defer 대상만)

| Asset | Observed blast radius | why-not-now (Wave 5 mainline) |
|-------|----------------------|-------------------------------|
| `layout.html` | realtime, notification, global 스크립트 | Tier 3; WDC·erp_beta pilot과 동시에 열면 §8 stop 조건 |
| `regional_dashboard.html` | 대형 인라인 | 동일 |
| `erp_dashboard_styles.html` / `erp_dashboard_scripts*.html` | dashboard family | 동일 |
| `erp-pro.css` + `erp-pro/*` | 전역 스타일 | Tier 4; logical org는 별도 준비 |
| `style.css` | legacy global | 낮은 우선순위 |
| `measurement/dashboard.js`, `wam/attachments.js` | 다른 bounded context | Wave 5 queue classify만 |

## Stop / defer decision (W5-B0)

| 조건 (§8) | 결과 |
|-----------|------|
| WDCalculator-first executable island | **PASS** — queue에 Tier 1이 첫 mainline으로 고정됨 |
| Four-chunk mainline ordering | **PASS** — composition → primary-form → estimate-lifecycle → pricing-core → erp-beta 순서 명시 |
| shell/layout 수정 없이 WDC를 못 닫는다는 증거 | **NOT SEEN** — 현재 증거는 정적 JS·config 중심으로 국소 수령 가능 |
| `foms/platform/blueprints.py` 변경 필요 | **NOT TRIGGERED** (docs-only batch) |

→ **W5-B1 진행 가능.** W5-B0에서 **W5-B9 partial closeout으로 이어지는 stop은 발생하지 않음.**

## Direction Lock (10문항)

> **N/A 정의 (본 batch):** 해당 문항이 “코드/README 변경” 등 **후속 batch 전용**일 때 `N/A` — 의미는 “본 batch 범위에서 해당 검사 불적용”이다.

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | authoritative queue + mainline 순서로 SoT가 문서에 한 곳에 고정됨 |
| 2 | yes | split-brain을 늘리지 않음; 과거 inventory는 drift 표로만 구분 |
| 3 | yes | 코드/파일 추가 없음; 향후 batch는 FR19 순서 강제 |
| 4 | N/A | chunk 수령은 W5-B1~B5에서 수행; B0는 queue·drift·ordering만 |
| 5 | yes | product/wrapper/test 변경 0 |
| 6 | N/A | 코드 delta 없음; 순증가 검사는 code batch |
| 7 | N/A | README는 W5-B1에서 갱신 예정 |
| 8 | yes | 반복 시에도 queue·drift·defer가 쌓이는 구조 |
| 9 | yes | product vs defer shell 경계 명시 |
| 10 | yes | 구조·증거·문서만; 기능 변경 없음 |

## Verification

| 검사 | 결과 |
|------|------|
| docs-only consistency | 본 문서 내부 표·순서·실행 계획 `2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md` §2.5 mainline·defer 정합 |
| Wave 4 defer lane 누락 | drawing, shipment-*, as, construction → **§ Wave 4 closeout defer lanes** 표로 범위 밖 고정; main ERP shell, regional → Tier 3 defer 행 |
| APP_OK / verify_result | **N/A** (W5-B0 코드 변경 없음) |

## Changes made

- `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md` 생성 (본 파일)

## product / wrapper / test delta

| 구분 | delta |
|------|-------|
| product | 없음 |
| wrapper | 없음 |
| test | 없음 |

## README update 여부

- 없음 (W5-B1에서 `static/js/wdcalculator/README.md` 예정)

## Drift / stop / defer (summary)

- **Drift:** Step6 `wdcalculator_scripts.html` line count vs live — 대형 차이; authoritative는 live + config.
- **Stop:** 없음.
- **Defer:** shell/regional/dashboard/CSS/measurement/wam — W5-B9 또는 classify-only.
