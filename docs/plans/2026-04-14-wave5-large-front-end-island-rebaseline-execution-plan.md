# Wave 5 Large Front-End Island Rebaseline Execution Plan
> 작성일: 2026-04-14 | 상태: 검토 중
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
> 선행 wave: `docs/plans/2026-04-13-wave4-web-page-slice-migration-execution-plan.md`
> 보조 가드레일: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
> 핵심 선례: `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 5 — Large front-end island rebaseline**을 바로 실행할 수 있는 LLM용 runbook이다.

Wave 5의 목적은 "큰 프론트엔드 파일을 조금씩 쪼개자"가 아니라, 아래 여섯 가지를 기계적으로 닫는 것이다.

1. Step 6 inventory와 Wave 4 defer evidence를 기준으로 현재 남은 **대형 front-end island**를 authoritative queue로 다시 잠근다.
2. WDCalculator를 더 이상 thin host shell 증식 트랙으로 보지 않고, `composition`, `primary-form`, `estimate-lifecycle`, `pricing-core`의 **네 개 canonical chunk**로 재편한다.
3. `erp_beta_js.html`은 shared ERP form island로 보되, `layout.html`이나 global shell보다 앞서는 **bounded shared-form pilot**로 잠근다.
4. `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`는 giant shared shell/CSS lane으로 **분류하고**, mainline code batch가 아니라 defer register + required prep 대상으로 잠근다.
5. public path, include path, load order, DOM contract, `window.*` global, CDN/local asset order를 유지하면서도, source of truth는 더 큰 canonical chunk로 수렴시킨다.
6. 어떤 batch도 "새 wrapper file 추가"를 성과로 주장하지 못하게 하고, file/wrapper/test delta와 removal target을 같은 기록 안에서 강제한다.

### 1.2 기능 요구사항
1. Wave 5의 authoritative truth는 항상 `2026-04-10` large-file inventory, large-file governance spec, controlling spec, Wave 4 defer evidence, live template/static file state다.
2. Wave 5는 front-end island rebaseline이다. page owner relocation(Wave 4), API canonicalization(Wave 3), service namespace rationalization(Wave 6)을 본편으로 포함하면 안 된다.
3. 하나의 batch는 반드시 **한 island / 한 risk axis / 한 canonical target**만 다룬다.
4. `templates/`와 `static/`의 root는 유지한다. Wave 5에서 root physical move는 금지한다.
5. caller가 보는 public include path, static path, script load order, `window.*` global name, DOM id/class/data attribute는 기본 freeze다.
6. public path를 유지해야 하면 thin partial/loader bridge를 둘 수 있지만, bridge는 같은 batch run record 안에 retirement wave와 removal condition이 없으면 허용하지 않는다.
7. WDCalculator는 `*-host-bootstrap.js` 추가, wrapper-only batch, configure/init forwarding pair 증식을 절대 허용하지 않는다.
8. WDCalculator batch는 항상 `delete -> merge -> extend existing chunk -> add new file` 순서로 판단한다.
9. WDCalculator batch는 file count가 순감하거나 최소 동결이어야 하고, wrapper count는 반드시 줄어야 한다.
10. WDCalculator batch는 기존 micro contract pair 복제를 기본값으로 삼지 않는다. 가능하면 기존 chunk contract를 확장한다.
11. `static/js/wdcalculator/README.md` 또는 동등한 local entrypoint는 Wave 5의 WDCalculator code batch마다 최신 상태를 반영해야 한다.
12. `erp_beta_js.html` batch는 `ERP_BETA_ENABLED`, `ORDER_ID`, `USE_DIRECT_UPLOAD`, `window.__ERP_BETA_DRAFT_MODE`, `window.__ERP_DRAFT_ENDPOINT`, `window.__ERP_PAYMENT_ICON_URLS`를 contract freeze 대상으로 본다.
13. `layout.html` batch를 pilot으로 먼저 열지 않는다. global realtime/chat/notification/socket shell은 Wave 5 mainline의 후속 defer lane이다.
14. `regional_dashboard.html`과 `erp_dashboard_styles.html`은 giant shell/template/CSS lane으로 분류하고, first executable island로 승격하지 않는다.
15. `static/css/erp-pro.css`와 `static/css/erp-pro/*.css`는 selector rename 없이 **logical organization first**를 따른다.
16. `static/js/measurement/dashboard.js`, `static/js/wam/attachments.js`, `static/css/style.css`는 Wave 5 queue에서 분류는 하되 mainline code scope에 자동 포함하지 않는다.
17. 한 batch에서 template + JS + CSS + API payload를 동시에 크게 흔들지 않는다. island 내부에서도 boundary를 하나로 좁힌다.
18. automation gap이 큰 template/JS/CSS island는 batch별 manual smoke checklist 또는 equivalent regression evidence가 필수다.
19. giant shared shell/layout/CSS split 중 route, auth, realtime, upload, payment semantics 변경이 필요해지는 순간 batch를 중단하고 defer register로 넘긴다.
20. future LLM은 Wave 5 queue snapshot을 복사하지 말고, `W5-B0` run record에서 live evidence로 다시 잠가야 한다.

### 1.2.1 FR shorthand definitions
- `FR19`: `delete -> merge -> extend -> add` 순서로 판단한다. 새 canonical file을 추가하기 전에 기존 큰 chunk로 흡수할 수 없는지 먼저 적는다.
- `FR20`: local `README.md` gate다. 3개 이상 runtime module 또는 2개 이상 layer가 생기는 lane은 local entrypoint를 유지해야 한다.
- `LF-compat`: public include/static/global/DOM/load-order contract는 기본 유지다. 바뀌면 same-batch bridge + removal plan이 필수다.
- `LF-structure-first`: 첫 batch는 구조와 ownership만 정리하고 business rule/selector semantic change는 금지한다.

### 1.3 Out of scope / freeze
Wave 5에서는 아래를 건드리지 않는다.

- `foms/platform/blueprints.py` registration order, import entry path, runtime binding
- `app.py`, `run.py`, `start.sh`, `Procfile`, `Dockerfile`, `alembic.ini`, `railway*.toml`
- `apps/api/*`, `foms/api/*`의 canonicalization 본편
- DB schema 변경, Alembic revision 추가, `models.py` 계약 수정, WDCalculator DB lifecycle 변경
- page owner relocation 자체(`apps/*` -> `foms/web/*`) 본편
- chat/socketio/channel/webhook 플랫폼 구조 개편
- generated bundle(`static/wdplanner/assets/index-*.js`) hand edit
- `business_calendar` / `/calendar` 축
- CDN vendor switch나 third-party library major upgrade

Wave 5는 **front-end large-island의 canonical chunk 잠금 + structure-only rebaseline + shared shell/CSS defer register**까지만 담당한다.

추가 규칙:

- 어떤 Wave 5 batch라도 `foms/platform/blueprints.py` 수정이 필요해지는 순간 out-of-scope로 판단하고 즉시 stop/defer한다.

### 1.4 Scope reconciliation — 상위 spec / large-file governance와의 정합
이 계획은 controlling spec의 Wave 5 범위를 축소하는 문서가 아니다. 해석은 아래로 고정한다.

1. controlling spec의 Wave 5는 `WDCalculator`, `erp_beta_js.html`, `layout-level giant JS`, `regional dashboard giant template/CSS`를 모두 포함한다.
2. 다만 실행 순서는 blast radius에 따라 다르다. 이 runbook의 **실행 mainline**은 `WDCalculator four-chunk -> erp_beta shared-form pilot`까지 닫고, `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`는 **같은 Wave 5 안에서 queue classify + defer register**로 잠근다.
3. 따라서 `layout`/regional/dashboard shell/CSS를 mainline code batch에서 당장 실행하지 않는 것은 Wave 5 scope 축소가 아니라, 같은 Wave 안의 **why-not-now + required prep**를 남기는 순서 조정이다.
4. `2026-04-10` large-file governance spec의 §8 Wave Priority는 inventory/approval priority다. 이 계획은 그 규칙을 **front-end island subset**에 적용하며, API/Python hotspot(`apps/api/orders.py`, `apps/api/wdcalculator.py` 등)은 Wave 3 또는 별도 backend plan이 담당한다.
5. large-file governance §9 approval gate는 그대로 적용한다. inventory-first, contract freeze, structure-only, post-audit, status update 순서는 Wave 5에서도 유지한다.

## 2. Current Large Front-End Truth — 현재 island landscape

### 2.1 선행 handoff gate
Wave 5 actual execution은 아래 산출물을 소비한 뒤에만 시작한다.

1. `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` 또는 equivalent Wave 3 closeout evidence
2. `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` 또는 equivalent Wave 4 closeout evidence
3. `docs/plans/2026-04-13-wave4-web-page-slice-migration-execution-plan.md`
4. `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
5. `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
6. `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`
7. `docs/context/COMPACT_CHECKPOINT.md`

추가 규칙:

- Wave 5 code batch는 canonical closeout file 또는 아래 equivalent 정의를 충족한 closeout evidence가 있을 때만 시작한다.
- `equivalent closeout evidence`를 쓰려면 최소 아래를 포함해야 한다.
  - 단일 markdown closeout 문서 1개 또는 참조 가능한 run-record 묶음 1세트
  - 실제 완료된 batch와 미실행 batch 목록
  - defer register
  - `why-not-now`, `required prep`, `suggested next wave/batch`
  - 다음 wave로 넘어오는 handoff note
- `W4-B7`이 없더라도 본 문서는 drafted plan으로 존재할 수 있다.
- Wave 4 defer evidence와 live template/static state가 충돌하면 live file을 truth로 두고, drift를 `W5-B0` run record에 먼저 적는다.
- WDCalculator는 Wave 4 defer register가 없어도 queue상 mainline 후보지만, shared shell/global lane과 섞어 실행하지 않는다.
- `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`는 Wave 4에서 page-only scope 밖으로 defer된 shell/CSS lane으로 다시 잠근다.

### 2.2 Island-tier 판정 규칙
Wave 5는 front-end hotspot을 아래 네 tier로만 다룬다.

| Tier | 기준 | 허용 방식 |
|------|------|------|
| `Tier 1 chunk-first local island` | 한 bounded context 안에서 load order와 DOM/API coupling이 크지만 source of truth를 local chunk로 다시 묶을 수 있는 lane | mainline first |
| `Tier 2 bounded shared-form island` | 2개 이하 page/template family가 공유하는 giant inline JS/template island | mainline second |
| `Tier 3 shared shell / dashboard island` | layout, shared partial, dashboard script/style, realtime/global notification처럼 cross-context blast radius가 큰 lane | defer by default |
| `Tier 4 global CSS design-system island` | global design token/layout/component/page CSS monolith | logical split only, late defer |

보조 판정 규칙:

1. giant 파일이라고 해도 local chunk target이 명확하면 `Tier 1`이 될 수 있다.
2. shared shell/layout/realtime/socket dependency가 보이면 `Tier 1`이 아니다.
3. CSS first split은 selector rename 없이 file organization만 허용한다.
4. API payload, DB persistence, route owner 재설계가 필수로 보이면 Wave 5 mainline candidate가 아니다.

### 2.3 현재 queue snapshot
주의:

- 아래 표는 **Wave 5 초안 시점의 provisional island snapshot**이다.
- authoritative queue는 `W5-B0` run record가 supersede한다.
- future LLM은 이 표를 inventory처럼 복사하지 말고 `W5-B0`에서 evidence를 다시 적어야 한다.

| Island lane | Representative surface | 현재 관찰 | 초기 tier | Wave 5 처리 원칙 | 미래 canonical direction |
|------|------|------|------|------|------|
| WDCalculator | `templates/wdcalculator/partials/wdcalculator_scripts_config.html` + `wdcalculator_scripts.html` + `static/js/wdcalculator/*` | 50+ script tags, host/bootstrap/state shard가 누적된 과분해 island | `Tier 1 chunk-first local island` | mainline first, four canonical chunk 고정 | `composition`, `primary-form`, `estimate-lifecycle`, `pricing-core` |
| ERP Beta shared form | `templates/partials/erp_beta_js.html` + `templates/add_order.html` + `templates/edit_order.html` + `static/js/erp/beta-shared.js` | add/edit 공용 giant inline JS, payment/upload/item-row/draft logic 집중 | `Tier 2 bounded shared-form island` | mainline second, one pilot only | `static/js/erp/beta/*` + thin include |
| Main ERP shell | `templates/layout.html` | global shell, inline style, realtime/socket, notification, upload/global script 동시 보유 | `Tier 3 shared shell / dashboard island` | Wave 5 defer mainline | `foms/web/erp_shell` follow-up decision + split subpartials/static JS |
| ERP dashboard shell partial family | `templates/partials/erp_dashboard_styles.html` + `templates/partials/erp_dashboard_scripts.html` + `erp_dashboard_scripts_*.html` | dashboard grid/UI style + 6-way inline script partial family | `Tier 3 shared shell / dashboard island` | queue classify only, mainline defer | dashboard shell follow-up lane |
| Regional dashboard | `templates/regional_dashboard.html` | giant template + inline style + inline fetch/update script 결합 | `Tier 3 shared shell / dashboard island` | queue classify only, mainline defer | dedicated regional/dashboard follow-up lane |
| ERP design-system CSS | `static/css/erp-pro.css` + `static/css/erp-pro/*.css` | monolith entry + already split subfiles 공존, import/order/specifity contract 큼 | `Tier 4 global CSS design-system island` | logical-split defer | `static/css/erp-pro/*` authoritative family |

### 2.3.1 Additional non-mainline front-end coverage
`§2.3` 표는 mainline large island 위주다. `W5-B0` authoritative queue는 아래 hotspot도 반드시 분류해야 한다.

| Additional hotspot | Current owner | Wave 5 기본 처리 |
|------|------|------|
| `static/js/measurement/dashboard.js` | measurement canonical JS | classify only, mainline 자동 포함 금지 |
| `static/js/wam/attachments.js` | WAM attachment UI JS | classify only, mainline 자동 포함 금지 |
| `static/css/style.css` | legacy global style | classify only, 낮은 우선순위 defer |
| `templates/wdcalculator/calculator.html` | WDCalculator include root | WDCalculator lane support file로 추적 |
| `templates/wdcalculator/partials/wdcalculator_body.html` | WDCalculator DOM contract root | WDCalculator lane support file로 추적 |

추가 규칙:

- 위 hotspot은 `W5-B0`에서 분류하되, `W5-B2`~`W5-B8` code scope에 자동 포함되지 않는다.
- `layout.html` defer가 존재한다고 해서 `erp_beta_js.html` batch에 layout refactor를 끼워 넣으면 안 된다.

### 2.4 WDCalculator provisional chunk map
Wave 5는 WDCalculator를 아래 네 canonical chunk 기준으로 잠그고 시작한다.

| Canonical chunk | Preferred target | 대표 범위 | 1차 merge/remove target 예시 |
|------|------|------|------|
| `composition` | `static/js/wdcalculator/composition.js` | startup/bootstrap/order/load-order/lifecycle band | `startup-init.js`, `terminal-init.js`, `early-bootstrap.js`, `late-bootstrap.js`, `sidebar-bootstrap.js`, `primary-ui-bootstrap.js`, `catalog-buttons-bootstrap.js`, `catalog-buttons-host-bootstrap.js`, `coupon-search-render-bootstrap.js`, `coupon-search-render-host-bootstrap.js`, `loading-database-bootstrap.js`, `loading-database-host-bootstrap.js`, `notes-ui-bootstrap.js`, `notes-ui-host-bootstrap.js`, `post-mutation-ui-bootstrap.js`, `post-mutation-ui-host-bootstrap.js`, `products-editing-bootstrap.js`, `products-editing-host-bootstrap.js`, `estimates-early-bootstrap.js`, `estimates-early-host-bootstrap.js`, `totals-startup-terminal-bootstrap.js`, `totals-startup-terminal-host-bootstrap.js` |
| `primary-form` | `static/js/wdcalculator/primary-form.js` | base-components, notes, coupon, additional options, product catalog, direct user-input UI | `base-components-ui.js`, `notes-ui.js`, `coupon-display-helpers.js`, `additional-options-ui.js`, `product-catalog-ui.js`, `add-option-button.js`, `calculate-button.js` |
| `estimate-lifecycle` | `static/js/wdcalculator/estimate-lifecycle.js` | list/search/load/edit/save/refresh/sidebar/url/local state/order match | `sidebar-estimates.js`, `search-results-load.js`, `render-estimates-list.js`, `order-match-ui.js`, `refresh-after-save.js`, `reset-input-form-keep-customer.js`, `load-estimate-to-input-form.js`, `load-saved-estimate-to-form.js`, `save-estimate.js`, `add-estimate.js`, `estimate-list-events.js`, `estimate-mutation-bridge.js`, `loading-state.js`, `current-database-estimate-id.js`, `products-state.js`, `editing-estimate-id.js`, `estimates-state.js`, `url-bootstrap.js` |
| `pricing-core` | `static/js/wdcalculator/pricing-core.js` | current estimate math, aggregate totals, calculation resolvers, total display, coupon/shipping math | `current-estimate-math.js`, `estimate-totals.js`, `calculation-resolvers.js`, `total-estimates-display.js`, `current-estimate-orchestration.js`, `coupon-shipping-wiring.js` |

추가 규칙:

- 위 preferred target은 provisional이다. `W5-B1` run record가 authoritative chunk map으로 supersede한다.
- `§2.4`의 merge/remove target은 **예시**이지 완전한 inventory가 아니다. `W5-B1`은 `static/js/wdcalculator/*.js` 전체를 다시 훑어 disposition matrix를 만들고, 표에 없던 cross-cutting file도 반드시 `keep`/`merge`/`retire-later` 중 하나로 분류한다.
- 최소한 `shared.js`, `layout-sync-wiring.js`, `unsaved-exit-guard.js`처럼 표 밖에서 남아 있는 cross-cutting file은 `W5-B1`에서 누락 없이 disposition matrix에 들어가야 한다.
- 새 canonical file을 추가할 때는 같은 batch에서 어떤 micro file이 retire target이 되는지 반드시 적는다.
- `WdCalculator*` 글로벌 이름을 바꿀 필요가 있으면 same-batch bridge + removal plan이 없으면 stop한다.
- `composition`의 bootstrap 예시는 `2026-04-12` WDCalculator plan의 host/non-host pair 선례를 그대로 따른다. `W5-B1`에서 의도적으로 다르게 잠글 경우 drift reason을 명시해야 한다.

### 2.5 Mainline ordering rule
Wave 5 mainline은 아래 고정 순서를 따른다.

1. `wdcalculator-composition`
2. `wdcalculator-primary-form`
3. `wdcalculator-estimate-lifecycle`
4. `wdcalculator-pricing-core`
5. `erp-beta-shared-form`

잠금 규칙:

- `W5-B0`에서 first executable island는 무조건 WDCalculator lane이다.
- `W5-B1`이 `composition`을 lock하지 못하면 mainline은 즉시 stop하고 revised plan 필요로 기록한다.
- `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`는 Wave 5 first executable island로 승격하지 않는다.
- `erp_beta_js.html`도 WDCalculator four-chunk mainline보다 앞설 수 없다.
- shared shell/CSS lane을 먼저 열고 싶어지는 순간 그것은 Wave 5 drift로 본다.

### 2.6 Direction Lock Questions
모든 batch run record는 아래 10문항에 대해 yes/no + 한 줄 근거를 남긴다.

1. 이번 batch는 single source of truth를 더 선명하게 만드는가
2. split-brain을 줄이는가, 아니면 임시로 늘린다면 언제 다시 줄일 것인가
3. 새 파일 추가 전에 delete/merge/extend를 실제로 검토했는가
4. 새 파일이 있다면 그것이 **가장 큰 유지보수 가능 chunk**인가
5. product/wrapper/test file 수는 순감 또는 최소 동결인가
6. 순증가라면 어떤 파일을 언제 없앨지 이미 적혀 있는가
7. local `README.md` 또는 동등한 AI entrypoint가 이번 변경 범위를 반영하는가
8. 이 패턴이 10번 반복돼도 FOMS 폴더가 더 깔끔해질 것 같은가
9. product / bridge / tooling / docs / quarantine 경계가 더 선명해졌는가
10. 지금 이 batch가 구조 작업인지, 아니면 슬쩍 기능 변경을 섞고 있는지 명확한가

## 3. Fixed Execution Pipeline — 고정 실행 순서

Wave 5 **전체**는 아래 순서를 지킨다. 각 batch는 이 순서 중 자신에게 배정된 subset만 수행하며, 실제 batch 경계는 `§4`, `§5` runbook이 우선한다.

1. Wave 4 defer evidence + large-file inventory consume
2. 현재 large front-end island queue와 mainline ordering lock
3. WDCalculator contract freeze + chunk map lock
4. WDCalculator chunk별 structure-only rebaseline
5. shared ERP inline form island 후보 lock
6. `erp_beta_js.html` contract freeze
7. `erp_beta_js.html` structure-only pilot rebaseline
8. high-risk shell/CSS lane defer register 정리
9. closeout + next continuation order 고정

추가 규칙:

- 하나의 batch에서 두 island를 동시에 canonicalize하지 않는다.
- load order freeze 없이 script/template move를 시작하지 않는다.
- chunk rebaseline과 giant shared shell refactor를 한 batch에 섞지 않는다.
- mainline code batch는 항상 `APP_OK`와 `verify_result`를 요구한다.
- code batch 검증이 실패하면 현재 batch 안에서만 `fix-forward` 또는 `revert + documented defer`를 결정한다.
- code batch가 `§8 Stop Conditions`로 중단되면 다음 legal batch는 `W5-B9` docs-only closeout이다.

## 4. Wave 5 Batch Catalog — LLM 실행 순서

### 4.1 Batch table
| Batch ID | 이름 | Risk axis | 주 결과물 | 선행 조건 | 필수 run record |
|------|------|------|------|------|------|
| W5-B0 | Readiness gate + island queue lock | docs / truth | authoritative island queue, mainline ordering lock | `W4-B7` 또는 `§2.1 equivalent closeout evidence` | `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md` |
| W5-B1 | WDCalculator contract freeze + chunk map lock | docs / contract | WDCalculator public/runtime freeze, four-chunk authoritative map, README gate | W5-B0 | `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md` |
| W5-B2 | WDCalculator composition canonicalization | code / local island | `composition` canonical target + wrapper retirement map | W5-B1 | `docs/plans/2026-04-14-wave5-batch2-wdcalculator-composition-run-record.md` |
| W5-B3 | WDCalculator primary-form canonicalization | code / local island | `primary-form` canonical target + wrapper retirement map | W5-B2 | `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md` |
| W5-B4 | WDCalculator estimate-lifecycle canonicalization | code / local island | `estimate-lifecycle` canonical target + state shard retirement map | W5-B3 | `docs/plans/2026-04-14-wave5-batch4-wdcalculator-estimate-lifecycle-run-record.md` |
| W5-B5 | WDCalculator pricing-core canonicalization | code / local island | `pricing-core` canonical target + math/orchestration retirement map | W5-B4 | `docs/plans/2026-04-14-wave5-batch5-wdcalculator-pricing-core-run-record.md` |
| W5-B6 | Shared ERP front-end island lock | docs / truth | `erp_beta_js.html` pilot lock + shell/CSS backlog ordering | W5-B5 | `docs/plans/2026-04-14-wave5-batch6-shared-erp-island-lock-run-record.md` |
| W5-B7 | ERP Beta contract freeze | docs / contract | `erp_beta_js.html` globals/DOM/load-order/API contract freeze | W5-B6 | `docs/plans/2026-04-14-wave5-batch7-erp-beta-contract-freeze-run-record.md` |
| W5-B8 | ERP Beta shared-form pilot rebaseline | code / shared-form island | `erp_beta_js.html` thin include + canonical static chunk target | W5-B7 | `docs/plans/2026-04-14-wave5-batch8-erp-beta-rebaseline-run-record.md` |
| W5-B9 | High-risk shell/CSS defer register + closeout | docs / handoff | layout/regional/dashboard shell/CSS defer register, continuation order, closeout | `W5-B8` or earlier stop-triggered closeout | `docs/plans/2026-04-14-wave5-batch9-closeout-run-record.md` |

### 4.2 Batch별 기본 원칙
- 본 표에 적힌 batch run record 파일은 아직 scaffold하지 않는다. 해당 batch를 실제 시작할 때 정확한 파일명으로 하나씩 만든다.
- 이미 placeholder/stub run record가 존재하면 새 sibling 파일을 만들지 말고 그 파일을 재사용한다.
- `W5-B0`, `W5-B1`, `W5-B6`, `W5-B7`, `W5-B9`는 docs-first다.
- `W5-B2`, `W5-B3`, `W5-B4`, `W5-B5`, `W5-B8`만 code-touch batch다.
- `W5-B2`~`W5-B5`는 WDCalculator lane만 다룬다.
- `W5-B8`은 `erp_beta_js.html` shared-form island 하나만 다룬다.
- `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`는 `W5-B9` defer register로 먼저 잠그기 전까지 code batch에 넣지 않는다.
- giant shared shell 또는 CSS split에서 route/auth/realtime/API semantics 변경이 필요해지는 순간 Wave 5 batch는 stop한다.

## 5. Batch Runbooks — 각 배치의 실제 실행법

### 5.1 W5-B0 — Readiness gate + island queue lock
**목표**
- Wave 4 defer evidence, large-file inventory, live file state를 소비해 Wave 5 queue를 authoritative하게 잠근다.
- mainline ordering을 `WDCalculator four-chunk -> erp_beta shared-form -> defer register`로 고정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md`

**금지 변경**
- product/runtime code
- spec/archive reference wiring
- future batch run record scaffold

**실행 단계**
1. Wave 4 defer evidence와 large-file inventory의 Wave 5 후보를 표로 재정리한다.
2. live file state와 inventory row가 어긋나는 lane이 있으면 drift로 먼저 기록한다.
3. `§2.3`, `§2.3.1`의 모든 lane에 대해 `mainline`, `defer`, `out-of-scope`를 다시 판정한다.
4. mainline ordering이 WDCalculator-first인지, shared shell/CSS가 pilot로 미끄러지지 않았는지 확인한다.
5. `composition`, `primary-form`, `estimate-lifecycle`, `pricing-core`의 provisional chunk 방향과 merge/remove candidate를 evidence로 다시 적는다.
6. WDCalculator four-chunk work가 `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css` 수정 없이는 닫히지 않는다는 evidence가 나오면 stop reason을 적고 `W5-B9` partial closeout 경로로 넘긴다.
7. WDCalculator-first executable **island** 또는 four-chunk mainline ordering을 lock하지 못하면 stop reason을 적고 `W5-B9` partial closeout 경로로 넘긴다.

추가 규칙:

- `W5-B0`은 drift와 queue lock을 run record에만 적는다. `docs/ARCHIVE_INDEX.md`와 controlling spec reference wiring은 `W5-B9` 전용이며, 상위 프로토콜이 명시적으로 요구할 때만 예외를 허용한다.

**필수 산출물**
- authoritative island queue table
- drift section
- mainline ordering lock
- `shared shell/CSS` backlog preview
- Direction Lock 10문항 yes/no + 한 줄 근거

**검증**
- docs-only consistency check
- Wave 4 defer lane이 queue에 누락되지 않았는지 수동 확인

### 5.2 W5-B1 — WDCalculator contract freeze + chunk map lock
**목표**
- WDCalculator public/runtime contract를 freeze한다.
- four-chunk authoritative map과 local `README.md` gate를 잠근다.

**허용 변경**
- `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md`
- `static/js/wdcalculator/README.md` (존재하지 않으면 생성 가능)

**금지 변경**
- `apps/api/wdcalculator.py` behavior change
- pricing rule/API payload change
- new `*-host-bootstrap.js`
- new micro contract pair proliferation

**실행 단계**
1. `wdcalculator_scripts_config.html`, `wdcalculator_scripts.html`, existing `static/js/wdcalculator/*`, WDCalculator plan을 근거로 load order, globals, DOM/API contract를 freeze한다.
2. current files를 `keep`, `merge-into-composition`, `merge-into-primary-form`, `merge-into-estimate-lifecycle`, `merge-into-pricing-core`, `retire-later`로 분류한다.
3. 위 분류는 `static/js/wdcalculator/*.js` 전체 sweep 기준이어야 하며, `§2.4` 표의 예시 목록만 복사해서 끝내면 안 된다. 표 밖 cross-cutting file도 모두 disposition matrix에 포함한다.
4. `static/js/wdcalculator/README.md`에 최소한 chunk map, 읽기 순서, merge/remove target, anti-pattern 금지 규칙을 적는다.
5. `composition`을 first executable chunk로 lock하고, 이 chunk 안에서 retire target이 될 host/bootstrap band를 명시한다.

**필수 산출물**
- load order contract table
- Jinja global contract
- DOM/API/query-param contract snapshot
- authoritative four-chunk map
- current file disposition matrix
- local README coverage note

**검증**
- docs/README consistency check
- README가 chunk map과 removal target을 담는지 수동 확인

### 5.3 W5-B2 — WDCalculator composition canonicalization
**목표**
- WDCalculator top-level orchestration을 `composition` canonical target으로 수렴시킨다.
- host/bootstrap/state-orchestration inflation을 줄인다.

**허용 변경**
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `static/js/wdcalculator/composition.js`
- `static/js/wdcalculator/README.md`
- `static/js/wdcalculator/*` 중 `W5-B1`에서 `composition` merge/remove target으로 잠근 파일
- WDCalculator existing contract tests / smoke helpers
- `docs/plans/2026-04-14-wave5-batch2-wdcalculator-composition-run-record.md`

**금지 변경**
- new `*-host-bootstrap.js`
- new standalone wrapper-only file
- pricing rule change
- WDCalculator API endpoint/payload change
- persistence separation 변경

**실행 단계**
1. `W5-B1`의 disposition matrix를 기준으로 `composition` merge set을 다시 확인한다.
2. `delete -> merge -> extend -> add` 순서로 `composition.js`를 canonical owner로 만든다.
3. `wdcalculator_scripts_config.html`의 script order를 단순화하되 public load order contract는 유지한다.
4. `wdcalculator_scripts.html`의 inline orchestration은 `composition`이 먹을 수 있는 범위까지만 줄인다.
5. retire target file이 남아야 한다면 bridge 이유와 retirement wave를 같은 run record에 적는다.
6. local README를 업데이트한다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- WDCalculator render/import contract subset
- composition 관련 existing focused contract subset
- `/wdcalculator` manual smoke: initial render, load order 오류 없음, sidebar/list 초기화, query-param auto-load smoke

### 5.4 W5-B3 — WDCalculator primary-form canonicalization
**목표**
- 입력 폼 UI cluster를 `primary-form` canonical target으로 수렴시킨다.
- notes/coupon/additional-options/product-catalog band를 더 큰 owner chunk로 재편한다.

**허용 변경**
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `static/js/wdcalculator/primary-form.js`
- `static/js/wdcalculator/README.md`
- `static/js/wdcalculator/*` 중 `primary-form` merge/remove target
- existing WDCalculator chunk contract tests
- `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md`

**금지 변경**
- DOM selector rename
- new micro UI helper proliferation
- add/save API contract change

**실행 단계**
1. `primary-form` merge set을 확정한다.
2. base-components/notes/coupon/additional-options/product-catalog/버튼 wiring을 가능한 한 한 owner 아래로 수렴시킨다.
3. direct input row, notes roundtrip, coupon display helper, additional option row contract가 유지되는지 chunk 기준으로 재고정한다.
4. bridge가 남으면 retirement wave를 기록한다.
5. README의 primary-form section을 최신화한다.

**검증**
- `APP_OK`
- `verify_result.py --json`
- primary-form 관련 focused contract subset
- `/wdcalculator` manual smoke: input row 편집, notes load/save, coupon display, additional options, catalog button flow

### 5.5 W5-B4 — WDCalculator estimate-lifecycle canonicalization
**목표**
- save/load/list/search/sidebar/url/state shard band를 `estimate-lifecycle` canonical target으로 수렴시킨다.
- state shard와 mutation bridge의 split-brain을 줄인다.

**허용 변경**
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `static/js/wdcalculator/estimate-lifecycle.js`
- `static/js/wdcalculator/README.md`
- `static/js/wdcalculator/*` 중 `estimate-lifecycle` merge/remove target
- existing WDCalculator lifecycle contracts
- `docs/plans/2026-04-14-wave5-batch4-wdcalculator-estimate-lifecycle-run-record.md`

**금지 변경**
- save/load API payload change
- query parameter semantic change
- hidden persistence lifecycle change

**실행 단계**
1. lifecycle merge set과 retire target을 확정한다.
2. save/load/list/search/sidebar/url/local-state 흐름을 single lifecycle owner로 수렴시킨다.
3. `refresh-after-save`, `estimate-mutation-bridge`, `loading-state`, id/state shard가 split-brain을 남기지 않는지 확인한다.
4. query param auto-load 및 order match flow contract를 유지한다.
5. README의 lifecycle section을 최신화한다.

**검증**
- `APP_OK`
- `verify_result.py --json`
- lifecycle 관련 focused contract subset
- `/wdcalculator` manual smoke: save, load, search, delete/refresh, estimate_id/order_id flow

### 5.6 W5-B5 — WDCalculator pricing-core canonicalization
**목표**
- math/totals/resolver/orchestration band를 `pricing-core` canonical target으로 수렴시킨다.
- aggregate total drift와 pricing split-brain을 줄인다.

**허용 변경**
- `templates/wdcalculator/partials/wdcalculator_scripts_config.html`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `static/js/wdcalculator/pricing-core.js`
- `static/js/wdcalculator/README.md`
- `static/js/wdcalculator/*` 중 `pricing-core` merge/remove target
- existing pricing/totals/current-estimate contracts
- `docs/plans/2026-04-14-wave5-batch5-wdcalculator-pricing-core-run-record.md`

**금지 변경**
- pricing business rule change
- coupon/shipping semantic change
- save payload meaning change

**실행 단계**
1. pricing-core merge set과 retire target을 확정한다.
2. `current-estimate-math`, `estimate-totals`, `calculation-resolvers`, `total-estimates-display`, `current-estimate-orchestration`, `coupon-shipping-wiring`를 가능한 한 single owner로 수렴시킨다.
3. aggregate totals와 current estimate math가 여전히 같은 source of truth를 사용하는지 확인한다.
4. README의 pricing-core section을 최신화한다.

**검증**
- `APP_OK`
- `verify_result.py --json`
- pricing/totals/current estimate contract subset
- `/wdcalculator` manual smoke: calculate, total panel, coupon/shipping, edit mode summary

### 5.7 W5-B6 — Shared ERP front-end island lock
**목표**
- WDCalculator mainline 이후 shared ERP giant front-end island를 다시 잠근다.
- `erp_beta_js.html`을 Wave 5의 only executable shared-form pilot로 확정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave5-batch6-shared-erp-island-lock-run-record.md`

**금지 변경**
- `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css` code touch
- spec/archive reference wiring

**실행 단계**
1. `erp_beta_js.html`, `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`의 current blast radius를 다시 비교한다.
2. `erp_beta_js.html`이 bounded shared-form island인지, `layout`/regional/dashboard shell보다 먼저 실행 가능한지 근거를 적는다.
3. `layout`, regional, dashboard shell partials, CSS monolith는 why-not-now와 required prep을 defer register preview로 남긴다.
4. `erp_beta_js.html`을 executable pilot으로 lock하지 못하면 stop reason을 적고 `W5-B9` partial closeout 경로로 넘긴다.

**필수 산출물**
- shared ERP island queue table
- `erp_beta_js.html` pilot lock
- shared shell/CSS backlog ordering
- Direction Lock 10문항 yes/no + 한 줄 근거

**검증**
- docs-only consistency check

### 5.8 W5-B7 — ERP Beta contract freeze
**목표**
- `erp_beta_js.html` shared-form island의 globals/DOM/API/load-order contract를 freeze한다.

**허용 변경**
- `docs/plans/2026-04-14-wave5-batch7-erp-beta-contract-freeze-run-record.md`

**금지 변경**
- runtime code
- add/edit order behavior change

**실행 단계**
1. `templates/partials/erp_beta_js.html`, `templates/add_order.html`, `templates/edit_order.html`, `static/js/erp/beta-shared.js`를 기준으로 globals/load order를 freeze한다.
2. add/edit shared behavior, direct upload path, item row DOM, payment icon globals, draft endpoint contract를 표로 고정한다.
3. `erp_beta` pilot의 preferred canonical shape를 잡는다.
   - 기본값: one thin include partial + one large static entry file
   - 내부 분리가 꼭 필요하면 최대 2개의 large helper만 허용하고, FR19 justification을 남긴다.
4. `static/js/erp/beta/*`가 3개 이상 runtime module 또는 2개 이상 layer가 되면 `static/js/erp/beta/README.md`를 local entrypoint로 요구한다고 명시한다.

**필수 산출물**
- globals/load-order contract table
- DOM selector/data-attribute contract
- API/fetch contract snapshot
- preferred canonical file shape
- manual smoke checklist

**검증**
- docs-only consistency check

### 5.9 W5-B8 — ERP Beta shared-form pilot rebaseline
**목표**
- `erp_beta_js.html`을 thin include로 축소하고, canonical shared-form logic를 더 큰 static chunk로 이동시킨다.
- add/edit shared form island의 split-brain을 줄인다.

**허용 변경**
- `templates/partials/erp_beta_js.html`
- `templates/add_order.html`
- `templates/edit_order.html`
- `static/js/erp/beta-shared.js`
- `static/js/erp/beta/*` (W5-B7 preferred shape 범위 안에서만)
- `static/js/erp/beta/README.md` (FR20 gate가 켜질 때만)
- existing order-form focused tests/smokes
- `docs/plans/2026-04-14-wave5-batch8-erp-beta-rebaseline-run-record.md`

**금지 변경**
- `layout.html` refactor
- upload/payment business semantic change
- page route/submit endpoint semantic change
- arbitrary micro-file proliferation

**실행 단계**
1. `W5-B7`의 preferred canonical shape에 따라 static entry owner를 만든다.
2. `erp_beta_js.html`은 thin include/bridge로 줄이되, globals injection과 legacy caller path는 유지한다.
3. item-row/payment/upload/draft/shared helper를 canonical owner 아래로 이동한다.
4. if add/edit divergence is uncovered, same batch 안에서 shared contract를 우선 기록하고 behavior drift 없이 정리한다.
5. retire target과 removal condition을 run record에 남긴다.
6. FR20 gate가 켜지면 `static/js/erp/beta/README.md`를 만들고 chunk map/entrypoint/retirement target을 적는다.

**검증**
- `APP_OK`
- `verify_result.py --json`
- order form focused smoke / existing tests
- manual smoke: add_order, edit_order, item add/remove, payment icon/remaining calc, direct upload toggle, draft/save path

### 5.10 W5-B9 — High-risk shell/CSS defer register + closeout
**목표**
- Wave 5 mainline에서 다루지 않은 shared shell/CSS lane을 authoritative defer register로 잠근다.
- 다음 continuation order와 stop/defer reasons를 남긴다.

**허용 변경**
- `docs/plans/2026-04-14-wave5-batch9-closeout-run-record.md`
- controlling spec의 참고 자료 섹션 보강
- `docs/ARCHIVE_INDEX.md`

**금지 변경**
- runtime code
- new decomposition batch 시작

**실행 단계**
1. `layout.html`, `regional_dashboard.html`, `erp_dashboard_styles.html`, `erp_dashboard_scripts*.html`, `erp-pro.css`, `style.css`, `measurement/dashboard.js`, `wam/attachments.js`를 defer register에 적는다.
2. `W5-B6`~`W5-B8`에 도달하지 못했거나 partial 상태로 멈춘 경우, `erp_beta_js.html` lane을 별도 row로 적고 `not started` / `partial` / `completed` 상태를 명시한다.
3. 각 lane에 대해 `why not now`, `required prep`, `suggested next batch type`, `canonical direction`을 남긴다.
4. Wave 5 완료 범위와 미완 범위를 분명히 적는다.
5. controlling spec 참고 자료와 archive index를 보강한다.

**검증**
- docs-only closeout
- defer register completeness
- Direction Lock 10문항 yes/no + 한 줄 근거

## 6. Verification Matrix — 배치별 필수 검증

| Batch | APP_OK | verify_result | focused automated | manual smoke | README/update | Direction Lock |
|------|------|------|------|------|------|------|
| W5-B0 | N/A | N/A | docs-only | N/A | N/A | 필수 |
| W5-B1 | N/A | N/A | docs-only | N/A | 필수 | 필수 |
| W5-B2 | 필수 | 필수 | WDCalculator composition subset | 필수 | 필수 | 필수 |
| W5-B3 | 필수 | 필수 | WDCalculator primary-form subset | 필수 | 필수 | 필수 |
| W5-B4 | 필수 | 필수 | WDCalculator lifecycle subset | 필수 | 필수 | 필수 |
| W5-B5 | 필수 | 필수 | WDCalculator pricing subset | 필수 | 필수 | 필수 |
| W5-B6 | N/A | N/A | docs-only | N/A | N/A | 필수 |
| W5-B7 | N/A | N/A | docs-only | checklist 준비 | N/A | 필수 |
| W5-B8 | 필수 | 필수 | order-form focused subset | 필수 | FR20 해당 시 필수 | 필수 |
| W5-B9 | N/A | N/A | docs-only | N/A | N/A | 필수 |

추가 규칙:

- WDCalculator code batch는 가능한 한 기존 chunk contract suite를 확장하고, 신규 micro pair는 기본 금지다.
- `focused automated`는 설명용 라벨이지 자동으로 해석되는 명령 이름이 아니다. 모든 code batch run record는 실제로 실행할 `pytest`/`python`/`node` 명령 또는 대상 파일 집합을 명시해야 한다.
- 기존 granular contract test가 현재 file명 기준으로만 남아 있어도, run record에는 `이번 batch에서 유지/확장할 concrete automated subset`을 적어야 한다. 적합한 기존 subset이 없으면 가장 가까운 상위 suite와 보완 이유를 같이 적는다.
- `W5-B8`은 automation gap이 크므로 manual smoke checklist가 없으면 성공 주장 금지다.
- touched file diagnostics/lint는 모든 code batch에 필수다.

## 7. Run Record Minimum Contract — 각 batch 기록 최소 항목

모든 run record는 최소 아래 항목을 가져야 한다.

1. `Scope lock`
2. `Inputs consumed`
3. `context normalization keys` (`registry lane`, `spec domain`, `FR20 context key` 또는 equivalent)
4. `Contract table`
5. `FR19 decision`
6. `Changes made`
7. `Verification`
8. `Direction Lock answers`
9. `product / wrapper / test delta`
10. `canonical target`
11. `removal / merge target`
12. `retirement wave / removal condition`
13. `README update 여부`
14. `drift / stop / defer decision`

추가 규칙:

- WDCalculator batch는 current file disposition matrix 또는 equivalent delta table이 필수다.
- `W5-B8`은 globals/load-order/API/DOM contract 유지 여부를 별도 표로 남긴다.
- docs-only batch도 Direction Lock 10문항 yes/no + 한 줄 근거를 남긴다.

## 8. Stop Conditions — 중단 조건

다음 중 하나라도 발생하면 해당 batch를 즉시 중단하고 `W5-B9` closeout으로 넘어간다.

1. page owner relocation 또는 API canonicalization이 먼저 필요해짐
2. DB schema, persistence lifecycle, WDCalculator DB separation 변경이 필요해짐
3. public include path/static path/global name/DOM contract를 bridge 없이 깨야 함
4. WDCalculator batch가 file count와 wrapper count를 함께 늘리는 방향으로만 수렴함
5. 새 `*-host-bootstrap.js` 또는 wrapper-only file을 추가해야만 한다는 결론이 나옴
6. shared shell/layout/realtime/socket dependency 때문에 local island로 닫을 수 없음
7. CSS split이 selector rename/semantic change 없이는 불가능함
8. automation/manual evidence 없이 behavior drift가 불가피함
9. 한 batch 안에서 두 island 이상을 동시에 건드리게 됨
10. `W5-B0`에서 WDCalculator-first executable island 또는 four-chunk mainline ordering을 lock하지 못함
11. `W5-B6`에서 `erp_beta_js.html`을 layout/regional/dashboard shell보다 먼저 실행 가능한 bounded shared-form pilot으로 lock하지 못함
12. `W5-B1`에서 WDCalculator authoritative four-chunk map 또는 `composition` first executable chunk contract freeze를 lock하지 못함
13. 어떤 batch라도 `foms/platform/blueprints.py` 변경이 필요해짐

## 9. Prompt Contract — Wave 5 실행 첫 프롬프트 규약

### 9.1 W5-B0 Prompt Contract
future LLM이 Wave 5를 실제로 시작할 때 첫 프롬프트는 최소 아래 요구를 만족해야 한다.

1. 입력 문서:
   - `@docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
   - `@docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
   - `@docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
   - `@docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
   - `@docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` 또는 equivalent Wave 3 closeout evidence
   - `@docs/plans/2026-04-13-wave4-web-page-slice-migration-execution-plan.md`
   - `@docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` 또는 equivalent Wave 4 closeout evidence
   - `@docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`
   - `@docs/context/COMPACT_CHECKPOINT.md`
2. batch order를 임의 변경하지 않는다고 선언한다.
3. `W5-B0`에서 island queue와 mainline ordering을 live evidence로 다시 잠그겠다고 명시한다.
4. WDCalculator first, shared shell/CSS defer 원칙을 어기지 않겠다고 명시한다.
5. future batch run record를 미리 만들지 않겠다고 명시한다.

### 9.2 W5-B0 Expected Output
`W5-B0` 결과에는 최소 아래가 있어야 한다.

- authoritative island queue
- drift table
- WDCalculator provisional chunk disposition refresh
- mainline ordering lock
- shared shell/CSS backlog preview
- Direction Lock 10문항 yes/no + 한 줄 근거

### 9.3 Batch Restart Minimum Input Set
세션이 batch 중간에 끊기거나 다른 LLM이 이어받을 때는 최소 아래 입력을 다시 준다.

| Batch range | 최소 입력 |
|------|------|
| `W5-B1` | 본 계획서 + `W5-B0` run record + WDCalculator plan + compact checkpoint |
| `W5-B2`~`W5-B5` | 본 계획서 + `W5-B1` run record + 직전 WDCalculator batch run record + `static/js/wdcalculator/README.md` |
| `W5-B6` | 본 계획서 + `W5-B0` run record + `W5-B1` run record + `W5-B5` run record + Wave 4 closeout evidence + large-file inventory |
| `W5-B7` | 본 계획서 + `W5-B6` run record + `erp_beta_js.html` 관련 live files |
| `W5-B8` | 본 계획서 + `W5-B6` run record + `W5-B7` run record + relevant order-form templates/static files |
| `W5-B9` | 본 계획서 + `W5-B0`부터 마지막 completed batch까지의 run records + all defer/stop evidence |

추가 규칙:

- 각 재시작 프롬프트는 current batch 이전 배치가 정상 종료됐는지 먼저 확인한다고 명시한다.
- current batch 범위 밖 파일을 열어야 하면 이유를 같은 프롬프트에 적는다.
- stop-triggered closeout이면 `partial closeout`이라고 명시한다.

## 10. Completion Criteria — Wave 5 완료 판단

Wave 5는 아래 둘 중 하나일 때만 닫는다.

1. `W5-B0`~`W5-B9`가 순서대로 완료되고, `W5-B9` closeout이 끝난 경우
2. 중간 batch(code/docs gate 포함)가 `§8 Stop Conditions`에 걸려 중단됐고, `W5-B9` partial closeout이 끝난 경우

### 10.1 Full closeout 추가 기준
아래는 `W5-B0`~`W5-B9`를 모두 완료한 **full closeout**에만 적용한다.

- WDCalculator mainline four-chunk run record가 모두 존재해야 한다.
- `W5-B8` run record가 존재해야 한다.
- shared shell/CSS lane은 최소 defer register로 잠겨 있어야 한다.
- spec reference와 archive index가 Wave 5 plan/closeout을 가리켜야 한다.

### 10.2 Partial / stop-triggered closeout 추가 기준
아래는 중간 batch(code/docs gate 포함) stop 이후 `W5-B9`로 닫는 **partial closeout**에 적용한다.

- stop 시점까지 완료된 batch run record만 존재하면 된다. 미실행 WDCalculator chunk나 `erp_beta` lane은 `W5-B9`에 `not started` 또는 `partial`로 남기면 된다.
- 실행하지 못한 WDCalculator chunk와 `erp_beta_js.html` lane에는 `why-not-now`, `required prep`, `suggested restart batch`가 남아야 한다.
- shared shell/CSS lane은 최소 defer register로 잠겨 있어야 한다.
- spec reference와 archive index가 Wave 5 plan/closeout을 가리켜야 한다.

## 11. Suggested Review Loop — 감리 반복 규약

이 계획은 아래 반복을 전제로 한다.

1. 초안 작성
2. `code-reviewer` 감리
3. `evolution-architect` 감리
4. `grand-develop-master` 감리
5. HIGH/MEDIUM finding 제거
6. finding이 사라질 때까지 반복

최종 기준:

- 세 감리 모두 HIGH/MEDIUM 없음
- spec drift 없음
- Wave 5 mainline order와 defer register가 동시에 선명함
