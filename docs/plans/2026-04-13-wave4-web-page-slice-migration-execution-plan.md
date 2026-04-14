# Wave 4 Web / Page Slice Migration Execution Plan
> 작성일: 2026-04-13 | 상태: 검토 중
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `foms/platform/blueprints.py`
> 선행 wave: `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md`
> 구조 선례: `docs/plans/2026-04-10-step5-measurement-vertical-slice-plan.md`
> 보조 가드레일: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 4 — Web / page slice migration**을 바로 실행할 수 있는 LLM용 runbook이다.

Wave 4의 목적은 "ERP page도 언젠가 `foms/web/*`로 옮기자" 수준의 선언이 아니라, 아래 여섯 가지를 기계적으로 닫는 것이다.

1. `apps/erp_*_page.py`뿐 아니라 `blueprints.py`에 등록된 **HTML-oriented page owner 전체**의 route + template ownership을 context 기준으로 다시 잠근다.
2. Measurement precedent에서 검증한 `apps/*` thin page wrapper + `foms/web/<context>` canonical owner 패턴을 **page-first context부터** 확장한다.
3. `templates/` / `static/`의 root는 유지하되, 내부 namespace를 **context 기준**으로 정리하고 legacy path는 wrapper/mirror로 안정화한다.
4. giant template/inline JS를 "전부 지금 쪼개는 것"이 아니라, **public path와 owner만 먼저 정리**하고 large-file refactor는 Wave 5로 넘긴다.
5. Wave 3(API canonicalization), Wave 5(large front-end island), Wave 6(service namespace)로 책임이 새지 않도록 **page-only boundary**를 잠근다.
6. 새 page slice를 만들더라도 thin wrapper, template shell, micro JS 파일이 기하급수적으로 늘지 않게 **delta + removal target**을 같이 남긴다.

### 1.2 기능 요구사항
1. Wave 4의 authoritative truth는 항상 `foms/platform/blueprints.py`, controlling spec, Wave 3 closeout evidence다.
2. Wave 4는 page slice migration이다. API canonicalization을 다시 열거나 service/persistence rationalization을 본편으로 포함하면 안 된다.
3. 한 batch는 반드시 **한 context / 한 risk axis**만 다룬다.
4. `apps/*` legacy page module을 줄이더라도 route path, blueprint name, registration order, endpoint name, auth decorator는 기본 freeze다.
5. `templates/`와 `static/`는 root 유지가 절대 규칙이다. root 물리 이동은 Wave 4에서 금지한다.
6. template/static path가 바뀌더라도 caller가 보는 public path는 wrapper/mirror/include bridge로 안정화한다.
7. Wave 4의 canonical owner는 기본적으로 `foms/web/<context>`다. `foms/api`, `foms/persistence`, root `services/` 정리를 같이 하지 않는다. page owner extraction에 helper 이동이 필요하면 **API/다른 context가 소비하지 않는 page-local helper만** 같은 `foms/web/<context>` package 안에 둘 수 있고, shared helper라면 stop하고 Wave 3/6 선행조건으로 넘긴다.
8. page slice에 필요한 template namespace는 `templates/<context>/...`를 우선하고, legacy `templates/erp_*` 또는 `templates/partials/erp_*` path는 thin wrapper로 남긴다.
9. context가 dedicated static asset을 이미 가지고 있지 않다면, 빈 `static/js/<context>` / `static/css/<context>` 폴더를 억지로 만들지 않는다.
10. inline script/style partial이 현재 canonical asset이라면 먼저 `templates/<context>/partials/scripts.html`, `styles.html` 같은 **context partial namespace**로 잠근다.
11. 새 generic bucket(`templates/pages/`, `static/js/erp-beta/` 같은 포괄 폴더)은 금지한다. context 이름이 있으면 context 이름을 그대로 쓴다.
12. Wave 4에서 `layout.html`, `erp_dashboard.html`, `erp_beta_js.html`, `erp_sub_nav.html`, `erp_mobile_shell.html`, `regional_dashboard.html` 같은 shared shell / shared shell partial을 pilot으로 삼지 않는다.
13. `business_calendar`, `/calendar`, shared map shell, realtime/chat/channel lane은 Wave 4 mainline에 넣지 않는다.
14. `FR19` 기준으로 기본값은 `single canonical page module + thin legacy wrapper`다. package/file 수를 늘리려면 왜 단일 module로 끝낼 수 없는지 run record에 남겨야 한다.
15. `FR20` local `README.md`는 context package가 3개 이상 module 또는 2개 이상 layer를 가질 때만 허용한다.
16. 새 테스트는 기존 render/import/menu contract를 **확장**하는 것을 우선한다. 새 micro support/test pair는 기본값이 아니다.
17. giant template/inline JS를 context namespace로 옮기는 과정에서 800줄+ structural split이 필요해지면 Wave 4 code batch를 중단하고 Wave 5/large-file governance로 defer한다.
18. wrapper/test/product file delta가 증가하면 같은 batch run record에 반드시 `removal target / merge-back candidate / retirement wave`를 남긴다.
19. one-context batch 안에서도 blueprint/API/template/JS/CSS를 한꺼번에 크게 흔들지 않는다. page owner extraction과 asset namespace stabilization을 가능하면 별도 batch로 나눈다.
20. manual smoke 또는 equivalent regression evidence 없이 page slice 성공을 주장하면 안 된다.

### 1.2.1 FR shorthand definitions
- `FR19`: `delete -> merge -> extend -> add` 순서로 판단한다. 새 file을 만들기 전에 기존 owner를 줄이거나 합칠 수 없는지 먼저 적는다.
- `FR20`: local `README.md` gate다. 한 context에서 3개 이상 module 또는 2개 이상 layer가 생길 때만 README를 하나 만들고, `FR20 context key` 기준으로 owner/template/static 관계를 적는다.
- Measurement precedent에 이미 존재하는 README는 grandfathered reference다. Wave 4 신규 context가 같은 이유로 자동 허용되는 것은 아니다.

### 1.3 Out of scope / freeze
Wave 4에서는 아래를 건드리지 않는다.

- `foms/platform/blueprints.py`의 registration order, import entry path, root runtime binding
- `app.py`, `run.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `alembic.ini`
- `apps/api/*`, `foms/api/*`의 canonicalization 본편
- DB schema 변경, Alembic revision 추가, `models.py` 계약 수정
- JSONB mutation contract, `flag_modified`, persistence lifecycle 재설계
- WDCalculator front-end restructuring
- `templates/layout.html`, `templates/erp_dashboard.html`, `templates/partials/erp_beta_js.html`, `templates/partials/erp_sub_nav.html`, `templates/partials/erp_mobile_shell.html`
- `templates/regional_dashboard.html`, `templates/partials/erp_dashboard_styles.html`, regional dashboard giant template/CSS
- shared map shell 전체 이관
- chat/socketio/channel/webhook/realtime binding

Wave 4는 **page route owner 정리 + template/asset namespace stabilization + legacy wrapper/mirror 기록**까지만 담당한다. giant shared shell, giant inline JS chunk-first rebaseline, layout-level refactor는 Wave 5에서 다룬다.

## 2. Current Web Truth — 현재 page landscape

### 2.1 선행 handoff gate
Wave 4 actual execution은 Wave 3의 아래 산출물을 소비한 뒤에만 시작한다.

1. `W3-B6` closeout run record
2. `W3-B0` readiness gate queue lock
3. `docs/plans/2026-04-10-step5-batch66-closeout-run-record.md` 또는 equivalent Measurement closeout evidence
4. `foms/platform/blueprints.py`
5. Wave 2 truth map / adapter matrix / FR20 README evidence

추가 규칙:

- `W3-B6`가 없으면 `W4-B0`는 stop한다.
- Wave 3가 아직 실행 중이라면 이 문서는 **drafted plan**으로만 존재할 수 있다. 실제 code batch는 `W3-B6` 또는 equivalent closeout evidence 없이는 시작하지 않는다.
- Wave 3 closeout과 `blueprints.py`가 충돌하면 `blueprints.py`를 live truth로 두고, Wave 3 drift를 먼저 문서화한 뒤 queue를 다시 잠근다.
- Measurement precedent는 반드시 Step 5 closeout evidence로 재확인한다. `apps/erp_measurement_dashboard.py`만 읽고 선례를 해석하면 안 되고, canonical owner `foms/web/measurement/dashboard.py` 기준으로 본다.
- Wave 3 API defer register에 올라간 고위험 context라도 page lane이 작고 독립적이면 Wave 4 후보가 될 수 있다. 다만 API lane은 여전히 freeze다.
- `spec §2.9`의 예시 목록은 non-exhaustive다. 이 계획은 spec taxonomy의 `cs` lane을 현재 live surface `apps.erp_completion_page`로 구체화해 실행한다.

### 2.2 Page-tier 판정 규칙
Wave 4는 page surface를 아래 네 tier로만 다룬다.

| Tier | 기준 | 허용 방식 |
|------|------|------|
| `Tier 0 precedent` | Measurement처럼 이미 canonical page precedent가 검증된 surface | reference only |
| `Tier 1 low-coupling page` | 단일 page route cluster, 작은 template/partial family, shared shell 의존이 낮음 | early pilot |
| `Tier 2 dashboard family` | 단일 bounded context지만 partial family와 inline script가 크고 page module도 중간 이상 | one-context docs/code batches |
| `Tier 3 high-risk shell` | giant template, shared layout, shared shell, page+API coupling, settings dual-lane, global partial | defer or Wave 5 |

보조 판정 규칙:

1. page module이 짧더라도 shared shell·map·calendar·realtime·global script 의존이 크면 low-tier가 아니다.
2. dedicated `static/js/*` 자산이 있다고 해서 low-risk가 되지 않는다. owner 경계와 blast radius가 더 중요하다.
3. detail page와 dashboard page가 같이 붙어 있으면 하나의 context 안에서도 `single route cluster`인지 먼저 점검한다.
4. page move 도중 API/helper/service refactor가 필수처럼 보이면 higher tier로 올리거나 stop한다.

### 2.3 현재 queue snapshot
주의:

- 아래 표는 **Wave 4 초안 시점의 provisional queue snapshot**이다.
- authoritative queue는 `W4-B0` run record가 supersede한다.
- future LLM은 이 표를 inventory처럼 복사하지 말고 `W4-B0`에서 evidence를 다시 적어야 한다.

| Context lane | Representative surface | 현재 관찰 | 초기 tier | Wave 4 처리 원칙 | 미래 canonical target |
|------|------|------|------|------|------|
| Measurement | `apps.erp_measurement_dashboard` alias shim -> `foms/web/measurement/dashboard.py` | canonical precedent already exists | `Tier 0 precedent` | reference only | `foms/web/measurement` |
| CS (current live surface: completion) | `apps.erp_completion_page` | 단일 `/erp/completion` route, smallest CS-family live owner지만 `layout`/`erp_sub_nav`/mobile shell coupling 존재 | `Tier 1 low-coupling page` | default pilot for CS family | `foms/web/cs` |
| Production | `apps.erp_production_page` | 단일 dashboard route + partial family(필터/모달/scripts/styles/mobile) + `partials/erp_production_scripts.html` hotspot | `Tier 2 dashboard family` | second candidate family | `foms/web/production` |
| Construction | `apps.erp_construction_page` | 단일 dashboard route + partial family + `partials/erp_construction_scripts.html` hotspot, self-measurement/mine gating | `Tier 2 dashboard family` | production sibling candidate | `foms/web/construction` |
| Drawing | `apps.erp_drawing_workbench` | dashboard + detail 2 route cluster, shared `erp_dashboard_scripts_drawing.html` partial 연동 | `Tier 2 dashboard family` | after dashboard family; shell coupling 먼저 기록 | `foms/web/drawing` |
| Shipment | `apps.erp_shipment_page` dashboard + `apps.api.erp_shipment_settings` page/API lane | giant dashboard template + dedicated static js/css + `/erp/shipment-settings` dual-lane | `Tier 3 high-risk shell` | late or defer; settings/API lane 분리 필요 | `foms/web/shipment` dashboard + separate settings disposition |
| AS (same CS family) | `apps.erp_as_page` | huge dashboard template, richer editor/map/tab interaction | `Tier 3 high-risk shell` | late or defer | `foms/web/cs` follow-up lane |
| CS adjacent actions | dedicated standalone page 미확인 | completion/AS/main ERP shell에 흩어진 interaction lane | `Tier 3 high-risk shell` | standalone page owner 없음; W4 mainline pilot 금지 | `cs` follow-up |
| Main ERP shell | `apps.erp_dashboard`, `templates/layout.html`, `templates/erp_dashboard.html`, `templates/partials/erp_beta_js.html` | global shell + shared scripts/styles partial 집합 | `Tier 3 high-risk shell` | Wave 5 defer fixed | `foms/web/erp_shell` or separate shell decision |
| Regional dashboards | `apps.dashboards`, `templates/regional_dashboard.html` | legacy dashboard shell, separate lineage | `Tier 3 high-risk shell` | Wave 5 or dedicated later review | TBD |

### 2.3.1 Additional HTML registry coverage
`§2.3` 표는 pilot/major lane 위주다. `W4-B0` authoritative queue는 아래 HTML blueprints도 반드시 분류해야 한다.

| Additional registry lane | Current owner | Wave 4 기본 처리 |
|------|------|------|
| ERP history | `apps.erp_history_page` | support page lane로 기록, pilot 제외 |
| Storage dashboard | `apps.storage_dashboard` | operational UI lane, defer or out-of-scope |
| Order root UI | `apps.order_pages`, `apps.order_edit`, `apps.order_trash` | non-ERP root UI lane, out-of-scope 명시 |
| User/admin/import UI | `apps.user_pages`, `apps.admin`, `apps.excel_import` | non-ERP root UI lane, out-of-scope 명시 |
| Auth UI | `apps.auth` | auth root UI lane, out-of-scope 명시 |
| Calendar | `apps.calendar_page` | spec 고정 out-of-scope |
| WDPlanner | `apps.wdplanner_page` | separate track, out-of-scope 명시 |
| Channel WAM HTML | `apps.api.channel_wam` | HTML-emitting API-first lane, classify only and 변경 금지 |

추가 규칙:

- Wave 2에서 broader page/UI inventory로 분류한 root UI lane이라도, 이 plan의 mainline(`W4-B1`~`W4-B6`)은 **ERP page slice**만 다룬다.
- 위 additional registry lane은 `W4-B0`에서 반드시 분류하되, `W4-B1`~`W4-B6`의 code scope에 자동 포함되지 않는다.

### 2.4 Pilot tie-break rule
Wave 4의 first pilot은 아래 순서로 고른다.

1. `cs` (current live pilot surface = `apps.erp_completion_page`)
2. `production`
3. `construction`
4. `drawing`
5. `shipment`
6. `as`

잠금 규칙:

- `cs`가 `W4-B0` evidence에서 low-coupling 조건을 통과하면 pilot은 무조건 `cs`다. 단, current live pilot surface는 `apps.erp_completion_page`로 기록한다.
- `cs`가 shared shell 또는 hidden API coupling 때문에 실패하면 `production`으로 내려간다.
- `W4-B0`가 `production`을 pilot으로 잠갔다면, 이후 batch는 `production`을 다시 dashboard-family 후보로 재개방하지 않는다. `W4-B4` 이후의 remaining queue는 pilot을 제외한 미소비 context만 대상으로 다시 잠근다.
- `production`과 `construction`이 둘 다 후보면, **self-measurement / shared mine filter / cross-context partial 수가 더 적은 쪽**을 먼저 고른다.
- `production`이 이미 pilot이면, `W4-B4`는 `construction`을 next dashboard winner로 auto-lock하고 `drawing`을 대체 후보로 즉시 승격하지 않는다. `construction`까지 block되면 같은 wave 안에서 `drawing`으로 미끄러지지 말고 stop 후 `W4-B7`로 closeout한다.
- 이 runbook의 executable pilot outcome은 `cs` 또는 `production` 둘뿐이다. `construction` 이하 후보는 queue ordering reference이며, `production`마저 pilot으로 잠글 수 없으면 `W4-B0`에서 stop하고 revised plan이 필요하다고 기록한다.
- `drawing`은 detail/dashboard 2-route cluster라서 `cs`/`production`/`construction`보다 뒤다.
- `shipment`와 `as`는 giant template/API/settings/editor coupling 때문에 초기 pilot으로 올리지 않는다.
- `layout.html`, `erp_dashboard.html`, `erp_beta_js.html`, `regional_dashboard.html`은 Wave 4 pilot이 될 수 없다.

## 3. Fixed Execution Pipeline — 고정 실행 순서

Wave 4 **전체**는 아래 순서를 지킨다. 각 batch는 이 순서 중 자신에게 배정된 subset만 수행하며, 실제 batch 경계는 `§4`, `§5` runbook이 우선한다.

1. Wave 3 authoritative closeout evidence consume
2. 현재 page priority queue와 pilot context lock
3. pilot context public contract freeze
4. canonical page module shape 결정
5. `foms/web/<context>` owner extraction
6. template / partial / asset namespace stabilization
7. legacy wrapper / mirror preservation
8. verification + run record 작성
9. 다음 context 후보를 다시 lock하거나 defer

추가 규칙:

- 하나의 batch에서 두 context를 동시에 canonicalize하지 않는다.
- contract freeze 없이 code move를 시작하지 않는다.
- page module extraction과 giant template refactor를 한 batch에 섞지 않는다.
- context가 dedicated static asset이 없다면 template partial canonicalization만 수행하고, 빈 static directory를 만들지 않는다.
- Wave 4에서 새 generic shell folder를 만들지 않는다.
- route path와 endpoint name은 유지하되, source of truth는 한 경로에만 남겨야 한다.
- code batch 검증이 실패하면 현재 batch 안에서만 `fix-forward` 또는 `revert + documented defer`를 결정한다. 결정을 run record에 남기기 전에는 다음 batch로 넘어갈 수 없다.
- code batch가 `§8 Stop Conditions`로 중단되면 다음 legal batch는 `W4-B7` docs-only closeout이다. `W4-B7`은 partial wave closeout으로도 실행될 수 있다.

## 4. Wave 4 Batch Catalog — LLM 실행 순서

### 4.1 Batch table
| Batch ID | 이름 | Risk axis | 주 결과물 | 선행 조건 | 필수 run record |
|------|------|------|------|------|------|
| W4-B0 | Readiness gate + page queue lock | docs / truth | authoritative page queue, pilot context lock | W3-B6 | `docs/plans/2026-04-13-wave4-batch0-readiness-gate-run-record.md` |
| W4-B1 | Pilot contract freeze (`<pilot_context>`) | docs / contract | pilot context route/template/partial contract freeze | W4-B0 | `docs/plans/2026-04-13-wave4-batch1-pilot-contract-freeze-run-record.md` |
| W4-B2 | Pilot page owner canonicalization (`<pilot_context>`) | code / page owner | `foms/web/<pilot_context>` + legacy page wrapper | W4-B1 | `docs/plans/2026-04-13-wave4-batch2-pilot-page-owner-run-record.md` |
| W4-B3 | Pilot template namespace stabilization (`<pilot_context>`) | code / template | `templates/<pilot_context>/*` canonical path + legacy wrappers | W4-B2 | `docs/plans/2026-04-13-wave4-batch3-pilot-template-namespace-run-record.md` |
| W4-B4 | Dashboard family next lock | docs / truth | next dashboard candidate lock + shell coupling inventory | W4-B3 | `docs/plans/2026-04-13-wave4-batch4-dashboard-family-lock-run-record.md` |
| W4-B5 | Dashboard page owner canonicalization (winner only) | code / page owner | single dashboard context `foms/web/<winner>` + legacy wrapper | W4-B4 | `docs/plans/2026-04-13-wave4-batch5-dashboard-page-owner-run-record.md` |
| W4-B6 | Dashboard template namespace stabilization (winner only) | code / template | single dashboard context template/partial namespace stabilization | W4-B5 | `docs/plans/2026-04-13-wave4-batch6-dashboard-template-namespace-run-record.md` |
| W4-B7 | High-risk defer register + closeout | docs / handoff | drawing/shipment/as/shell defer register, Wave 5 boundary, next order | `W4-B6` or earlier stop-triggered closeout | `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` |

### 4.2 Batch별 기본 원칙
- 본 표에 적힌 batch run record 파일은 아직 scaffold하지 않는다. 해당 batch를 실제 시작할 때 정확한 파일명으로 하나씩 만든다.
- `W4-B0`, `W4-B1`, `W4-B4`, `W4-B7`는 docs-first다.
- `W4-B2`, `W4-B3`, `W4-B5`, `W4-B6`만 code-touch batch다.
- `W4-B2`와 `W4-B3`는 `W4-B0`에서 잠근 `pilot_context` 하나만 다룬다.
- `W4-B5`와 `W4-B6`는 `W4-B4`가 잠근 remaining dashboard winner 하나만 다룬다. 이미 pilot으로 소비한 context를 다시 열지 않는다.
- `drawing`, `shipment-dashboard`, `shipment-settings`, `as`, `main ERP shell`, `regional dashboards`는 `W4-B7` defer register에 먼저 잠그기 전까지 code batch에 넣지 않는다.
- giant template/inline JS split이 필요한 순간, Wave 4 batch는 stop하고 Wave 5 후보로 넘긴다.

## 5. Batch Runbooks — 각 배치의 실제 실행법

### 5.1 W4-B0 — Readiness gate + page queue lock
**목표**
- Wave 3 authoritative closeout, Measurement closeout, `blueprints.py`를 소비해 Wave 4 queue를 확정한다.
- pilot context를 기본값 `cs` 기준으로 lock하되, evidence가 다르면 같은 batch에서 override한다.

**허용 변경**
- `docs/plans/2026-04-13-wave4-batch0-readiness-gate-run-record.md`

**금지 변경**
- runtime code
- `foms/platform/blueprints.py`
- controlling spec의 normative 본문
- 이 문서 자체

**실행 단계**
1. `W3-B6` closeout run record와 Step 5 Measurement closeout evidence 존재 여부를 확인한다.
2. `blueprints.py`, Wave 2 truth map, Wave 3 closeout evidence, Measurement closeout evidence를 대조해 current page owner surface list를 다시 적는다.
3. 이때 queue는 `apps/*page*.py`에 한정하지 않고, `blueprints.py`에 등록된 HTML-oriented blueprints 전체를 대상으로 분류한다.
4. 각 surface에 대해 최소 아래 필드를 남긴다.
   - registry lane
   - spec domain
   - FR20 context key
   - module path
   - blueprint symbol
   - route cluster
   - current owner state
   - template roots
   - static/partial roots
   - hidden coupling 요약
   - provisional tier
   - canonical target
   - shipment 계열이면 `dashboard lane` / `settings lane` 분리 여부
5. `cs`(current live pilot surface=`apps.erp_completion_page`)가 low-coupling 조건을 충족하는지 explicit check를 남긴다.
6. 통과하면 pilot context를 `cs`로 lock하고, current live pilot surface를 `apps.erp_completion_page`로 적는다.
7. 실패하면 `왜 실패했는지 / 어떤 규칙을 위반했는지 / 다음 후보가 누구인지`를 남기고 `production`으로 내린다.
8. `production`마저 pilot으로 잠글 수 없으면 `construction` 이하로 즉시 승격하지 말고, 이 runbook branch가 invalid하다는 stop reason을 남긴다.
9. `queue snapshot vs this plan §2.3` 차이가 있으면 drift section에 남긴다.
10. `spec §2.9`에 예시로 나온 `shipment / drawing / production / construction / CS`의 disposition(`in-scope`, `deferred`, `next wave`)을 표로 남긴다.
   - `shipment`는 최소 `shipment-dashboard`와 `shipment-settings` 두 row(또는 parent row + child rows)로 남긴다.
11. `pilot parameter sheet`를 남긴다.
   - pilot_context
   - current live pilot surface
   - blueprint symbol/name
   - route cluster / primary route path
   - concrete legacy module path
   - canonical module path
   - canonical template roots
   - legacy template roots
   - FR20 context key
   - minimum automated checks
   - minimum manual smoke scope

**산출물**
- authoritative page queue table
- pilot lock decision
- pilot parameter sheet
- high-risk shell defer preview
- `this plan §2.3 snapshot 대비 변경 row`
- `shipment-dashboard` / `shipment-settings` disposition

**검증**
- docs-only batch인지 확인
- each surface row에 tier와 hidden coupling field가 있는지 확인
- `W3-B6`가 없으면 stop 기록이 있는지 확인
- `cs` pilot override가 있으면 근거가 있는지 확인
- Direction Lock 10문항 yes/no + 한 줄 근거가 있는지 확인

### 5.2 W4-B1 — Pilot contract freeze (`<pilot_context>`)
**목표**
- `W4-B0`에서 잠근 `pilot_context`의 page owner와 template/partial path public contract를 먼저 문서로 고정한다.

**허용 변경**
- `docs/plans/2026-04-13-wave4-batch1-pilot-contract-freeze-run-record.md`

**금지 변경**
- runtime code
- pilot 외 context page module
- `foms/web/*`
- `templates/*`

**실행 단계**
1. `W4-B0`의 `pilot parameter sheet`에서 concrete module/template path를 읽는다. `cs`는 default example일 뿐이며 override되면 모든 path를 같은 context로 치환한다.
2. 아래 public contract table을 남긴다.
   - route path
   - methods
   - auth decorator
   - blueprint symbol/name
   - endpoint name
   - `render_template` target
   - legacy partial include path
3. template contract table에는 아래를 남긴다.
   - current primary template path
   - current script/style partial path
   - `url_for` / static asset references
   - mobile/desktop shared shell 여부
4. hidden coupling table에는 최소 아래를 남긴다.
   - shared layout dependency
   - menu / navigation dependency
   - API lane coupling
   - giant inline script/style 여부
5. canonical target이 single module인지 package인지 결정하고, 왜 single module로 끝낼 수 있는지 또는 없는지 남긴다.

**산출물**
- `pilot_context` public contract table
- template/partial contract table
- hidden coupling inventory
- canonical target shape decision

**검증**
- docs-only batch인지 확인
- route/template/partial fields가 모두 채워졌는지 확인
- new static dir를 만들지 않는 결정이 explicit한지 확인
- Direction Lock 10문항 yes/no + 한 줄 근거가 있는지 확인

### 5.3 W4-B2 — Pilot page owner canonicalization (`<pilot_context>`)
**목표**
- `pilot_context` page source of truth를 `foms/web/<pilot_context>`로 이동하고, legacy page module은 thin page wrapper로 유지한다.

**허용 변경**
- `foms/web/<pilot_context>/__init__.py`
- `W4-B0`가 잠근 concrete canonical module path
- 필요 시 `foms/web/<pilot_context>/helpers.py` (page-local helper이고 single module로 흡수할 수 없을 때만)
- concrete legacy page module (`W4-B0`에서 잠근 module path)
- 필요 시 `foms/web/<pilot_context>/README.md` (FR20 조건 충족 시에만)
- `docs/plans/2026-04-13-wave4-batch2-pilot-page-owner-run-record.md`

**금지 변경**
- `foms/platform/blueprints.py`
- `apps/api/*`
- DB / migrations / services 대형 정리
- template/partial path 변경

**실행 단계**
1. `pilot_context`의 live route owner를 `W4-B0`가 잠근 concrete canonical module path로 이전한다.
2. Measurement precedent처럼 canonical entry file은 package 안의 concrete module(`dashboard.py`일 수 있음)로 잠근다. `__init__.py`는 re-export/namespace 역할을 넘지 않는다.
3. legacy module은 Measurement precedent와 같은 thin wrapper 또는 module alias shim으로 축소한다.
4. route path, blueprint symbol, endpoint name, auth decorator는 유지한다.
5. page owner extraction에 필요한 최소 import 이동만 허용한다. helper 이동이 필요하면 page-local helper만 같은 `foms/web/<pilot_context>` 안에서 처리하고, API/other-context shared helper라면 stop한다.
6. `FR20` 조건을 넘지 않으면 `README.md`를 만들지 않는다.
7. run record에 `product / wrapper / test delta`와 `removal target`을 남긴다.

**산출물**
- canonical pilot page module
- legacy thin wrapper
- delta / retirement metadata

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `tests/test_foms_namespace_imports.py` 또는 동급 import contract 확장
- `tests/test_menu_config.py` 또는 동급 route/menu contract 확인
- web+worker parity는 `app` import path / shared worker import module을 건드렸을 때만 수행하고, 아니면 run record에 `N/A with reason`을 남긴다.
- touched paths lint

### 5.4 W4-B3 — Pilot template namespace stabilization (`<pilot_context>`)
**목표**
- `pilot_context`의 primary template와 partial family canonical path를 `templates/<pilot_context>/*` 아래의 concrete locked path로 옮기고, legacy path는 thin wrapper include로 남긴다.

**허용 변경**
- `W4-B1`이 잠근 concrete canonical template path
- `templates/<pilot_context>/partials/*`
- concrete legacy primary template / partials (`W4-B1` contract table 기준)
- 필요 시 `pilot_context` 관련 focused test
- `docs/plans/2026-04-13-wave4-batch3-pilot-template-namespace-run-record.md`

**금지 변경**
- `static/js/*`, `static/css/*` 빈 폴더 생성
- giant script/style refactor
- layout/shared shell 재배치
- `templates/partials/erp_sub_nav.html`, `templates/partials/erp_mobile_shell.html`, `templates/partials/erp_beta_js.html` 이동
- API route / service namespace 변경

**실행 단계**
1. `W4-B1` contract table을 기준으로 concrete canonical template path를 만든다. `pilot_context=cs`라도 filename은 live surface에 맞춘 concrete path를 따르며, dashboard-shaped default를 가정하지 않는다.
2. legacy template/partial path는 thin wrapper include로 남긴다. 동일 본문을 두 경로에 복제하면 batch 실패다.
3. legacy wrapper는 가능하면 1~3줄 include/re-export만 허용한다.
4. 현재 context에 dedicated static asset이 없으면 새 `static/js/<pilot_context>`, `static/css/<pilot_context>` 디렉터리를 만들지 않는다.
5. `render_template`와 include path를 canonical 기준으로 재고정하되 public path는 wrapper로 흡수한다.
6. giant inline script/style 분해가 필요해지는 순간 stop하고 Wave 5 후보로 기록한다.

**산출물**
- canonical pilot template namespace
- legacy wrapper partials
- asset decision (`no new static dir` 또는 explicit single chunk move)

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `pilot_context` render contract / template path test
- at least one automated include/path assertion
- manual smoke checklist 또는 equivalent evidence
- web+worker parity는 `app` import path / shared worker import module을 건드렸을 때만 수행하고, 아니면 run record에 `N/A with reason`을 남긴다.
- touched paths lint

### 5.5 W4-B4 — Dashboard family next lock
**목표**
- already-consumed pilot을 제외한 remaining dashboard-family 후보 중 다음 context 하나만 고른다.
- shell coupling, inline script hotspot, shared partial family를 먼저 문서로 잠근다.

**허용 변경**
- `docs/plans/2026-04-13-wave4-batch4-dashboard-family-lock-run-record.md`

**금지 변경**
- runtime code
- templates
- `foms/platform/blueprints.py`
- 이 문서 자체

**실행 단계**
1. `W4-B0` run record에서 `pilot_context`를 먼저 읽고, 이미 pilot으로 소비한 context는 `W4-B4` 후보 집합에서 제외한다.
2. default candidate comparison은 `production` vs `construction`이다. 단, `pilot_context=production`이면 `construction`을 next dashboard winner로 auto-lock하고 `production`을 재개방하지 않는다.
3. `pilot_context=production` branch에서는 `construction`만 full inventory로 읽고, `drawing`은 why-not-yet row로만 남긴다. `construction`이 새로 block되면 같은 batch에서 `drawing`으로 대체하지 말고 stop 후 `W4-B7` closeout으로 이동한다.
4. 비교 대상 context(또는 auto-lock branch의 `construction`)를 line-by-line로 읽고 최소 아래 필드를 남긴다.
   - route path
   - page owner module size/shape
   - partial family list
   - inline script hotspot 존재 여부
   - self-measurement / mine filter / shared helper coupling
   - existing dedicated static asset 유무
   - candidate canonical target shape
5. tie-break table 또는 auto-lock rationale block을 작성한다. 비교 branch에서는 최소 아래 row를 동일 포맷으로 남긴다.
   - shared partial count
   - shared shell dependency count
   - API/page coupling count
   - dedicated static asset count
   - self-measurement / mine-filter special path count
   - winner reason
6. winner 하나만 lock하고 loser는 defer-to-next row로 남긴다. auto-lock branch에서는 `construction` winner reason을 explicit하게 남긴다.
7. `drawing` / `shipment` / `as` / main shell이 왜 아직 뒤인지 한 줄씩 남긴다.

**산출물**
- dashboard family comparison table 또는 auto-lock rationale block
- winner lock decision
- deferred-next order

**검증**
- docs-only batch인지 확인
- compare branch면 두 candidate가 같은 필드로 평가됐는지 확인하고, auto-lock branch면 왜 `drawing`이 즉시 대체되지 않았는지 근거가 있는지 확인
- winner 외 context를 code batch에 올리지 않았는지 확인
- Direction Lock 10문항 yes/no + 한 줄 근거가 있는지 확인

### 5.6 W4-B5 — Dashboard page owner canonicalization (winner only)
**목표**
- `W4-B4`에서 고른 dashboard context 하나의 page owner만 `foms/web/<winner>`로 이동한다.

**허용 변경**
- `foms/web/<winner>/__init__.py`
- `foms/web/<winner>/dashboard.py`
- 필요 시 `foms/web/<winner>/helpers.py` (page-local helper이고 single module로 흡수할 수 없을 때만)
- 해당 legacy page module (`apps/erp_production_page.py` 또는 `apps/erp_construction_page.py`)
- 필요 시 `foms/web/<winner>/README.md` (FR20 조건 충족 시에만)
- `docs/plans/2026-04-13-wave4-batch5-dashboard-page-owner-run-record.md`

**금지 변경**
- loser context
- template/partial path 변경
- `apps/api/*`
- `foms/platform/blueprints.py`
- giant service/helper restructuring

**실행 단계**
1. winner context page owner를 canonical page module로 이전한다.
2. legacy page module은 thin wrapper 또는 module alias shim으로 축소한다.
3. current partial/include/static path는 아직 유지한다.
4. helper import가 많더라도 page owner extraction에 필요한 최소 범위만 정리한다. page-local helper만 같은 `foms/web/<winner>` package 안에 둘 수 있고, shared helper는 stop/defer한다.
5. delta / retirement metadata를 남긴다.

**산출물**
- single dashboard canonical page owner
- legacy thin wrapper
- delta / retirement metadata

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `tests/test_foms_namespace_imports.py` 또는 동급 import contract 확장
- `tests/test_menu_config.py` 또는 동급 route/menu contract 확인
- context route/menu render smoke
- web+worker parity는 `app` import path / shared worker import module을 건드렸을 때만 수행하고, 아니면 run record에 `N/A with reason`을 남긴다.
- touched paths lint

### 5.7 W4-B6 — Dashboard template namespace stabilization (winner only)
**목표**
- `W4-B5` winner context 하나의 dashboard template/partial namespace를 `templates/<winner>/*` 기준으로 안정화한다.

**허용 변경**
- `templates/<winner>/dashboard.html`
- `templates/<winner>/partials/*`
- 해당 legacy dashboard template / partials
- winner context 관련 focused test
- `docs/plans/2026-04-13-wave4-batch6-dashboard-template-namespace-run-record.md`

**금지 변경**
- loser context template
- layout/shared shell/global partial
- `templates/partials/erp_sub_nav.html`, `templates/partials/erp_mobile_shell.html`, `templates/partials/erp_beta_js.html`
- giant inline JS 구조 재작성
- empty static dir 생성
- shared `erp_beta_js.html` 이동

**실행 단계**
1. winner context dashboard template와 partial family를 canonical namespace로 옮긴다.
2. legacy `templates/erp_*` / `templates/partials/erp_*` path는 thin wrapper include로 남긴다. 동일 본문을 두 경로에 유지하면 batch 실패다.
3. dedicated static asset이 이미 있는 context가 아니라면 template partial canonicalization만 수행한다.
4. inline JS가 너무 커서 chunk-first refactor가 필요해지면 stop하고 Wave 5 후보로 기록한다.
5. run record에 `wrapper path / canonical path / retirement wave / removal condition`을 남긴다.

**산출물**
- canonical dashboard template namespace
- legacy wrapper partials
- Wave 5 defer 여부

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- context template/render contract
- at least one automated include/path assertion
- manual smoke checklist 또는 equivalent evidence
- web+worker parity는 `app` import path / shared worker import module을 건드렸을 때만 수행하고, 아니면 run record에 `N/A with reason`을 남긴다.
- touched paths lint

### 5.8 W4-B7 — High-risk defer register + closeout
**목표**
- Wave 4 mainline에서 다루지 않은 `drawing`, `shipment-dashboard`, `shipment-settings`, `as`, `main ERP shell`, `regional dashboards`, shared giant template/js lane을 명시적으로 defer한다.
- Wave 5로 넘어갈 shell/large-file lane과 Wave 4 continuation lane을 분리한다.
- 필요하면 code batch early-stop 뒤의 partial wave closeout 역할도 수행한다.

**허용 변경**
- `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md`
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` reference section
- `docs/ARCHIVE_INDEX.md`

**금지 변경**
- runtime code
- `foms/platform/blueprints.py`
- page/API implementation
- 이 문서 자체

**실행 단계**
1. `W4-B7`가 normal closeout인지, 아니면 어느 code batch(`W4-B2/B3/B5/B6`)에서 stop-triggered로 들어왔는지 먼저 적는다.
2. `drawing`, `shipment-dashboard`, `shipment-settings`, `as`, `main ERP shell`, `regional dashboards`, 그리고 `W4-B4`가 실행됐다면 its loser context 각각에 대해 defer row를 남긴다.
3. 각 row마다 최소 아래 필드를 남긴다.
   - current owner
   - why not in Wave 4 mainline
   - next wave
   - unblock condition
   - shell/shared hotspot
4. `spec §2.9` 예시 context 기준 `shipment / drawing / production / construction / CS`의 disposition matrix를 남긴다. `shipment`는 dashboard/settings dual-lane이 같은 matrix 안에서 분리돼야 한다.
5. Wave 5로 넘어가야 할 항목(`layout.html`, `erp_beta_js.html`, `regional_dashboard.html`, giant inline scripts`)을 고정한다.
6. Wave 4 continuation order를 하나의 shortlist로 남긴다.
7. controlling spec은 `§5 참고 자료` 또는 동등한 reference section만 갱신하고, normative 요구사항 본문 / wave 정의 / FR 본문은 수정하지 않는다.
8. spec/archive reference를 연결한다.

**산출물**
- high-risk defer register
- loser context disposition (`W4-B4` 실행 시에만)
- spec §2.9 example-context disposition matrix
- Wave 4 continuation shortlist
- Wave 5 boundary note
- spec/archive reference update
- partial closeout reason (early stop branch인 경우)

**검증**
- docs-only batch인지 확인
- defer row마다 `next wave / unblock condition`이 있는지 확인
- Wave 5와 Wave 4 continuation이 섞이지 않았는지 확인
- Direction Lock 10문항 yes/no + 한 줄 근거가 있는지 확인

## 6. Verification Matrix — 배치별 최소 검증

| Batch | 최소 검증 |
|------|------|
| W4-B0 | docs-only, queue row completeness, Direction Lock answers |
| W4-B1 | docs-only, contract table completeness, Direction Lock answers |
| W4-B2 | `APP_OK`, `verify_result.py`, import/route contract, spec §4 applicable checks, lint |
| W4-B3 | `APP_OK`, `verify_result.py`, render/template contract, manual smoke or equivalent, spec §4 applicable checks, lint |
| W4-B4 | docs-only, comparison completeness, Direction Lock answers |
| W4-B5 | `APP_OK`, `verify_result.py`, import/route contract, spec §4 applicable checks, lint |
| W4-B6 | `APP_OK`, `verify_result.py`, render/template contract, manual smoke or equivalent, spec §4 applicable checks, lint |
| W4-B7 | docs-only, defer row completeness, reference wiring, Direction Lock answers |

추가 규칙:

- code batch는 최소 `python -c "import app; print('APP_OK')"`와 `python tools/harness/verify_result.py --json`를 포함한다.
- 테스트는 가능하면 기존 `tests/test_foms_namespace_imports.py`, `tests/test_menu_config.py`, context render contract를 확장한다.
- shipment/production/construction 등 dashboard page는 수동 스모크 또는 equivalent regression evidence를 남겨야 한다.
- template namespace batch는 manual smoke와 별도로 최소 1개의 automated include/path assertion을 남긴다.
- docs-only batch도 Direction Lock 10문항을 포함한다.
- code batch는 controlling spec §4에서 적용되는 항목을 같이 체크한다: root clutter 증가 여부, quarantine/non-product import 누수 여부, web+worker parity trigger 여부, Direction Lock answers completeness.

## 7. Run Record Contract — 모든 batch가 남겨야 하는 공통 항목

각 batch run record는 최소 아래 section을 포함한다.

1. **Scope lock**  
   - 무엇을 했는지 / 무엇을 하지 않았는지
2. **Inputs consumed**  
   - spec, `blueprints.py`, Wave 2/3 evidence, precedent
3. **Wave key normalization**  
   - registry lane
   - spec domain
   - FR20 context key
4. **Public contract table**  
   - route path, endpoint, blueprint name, `render_template`, include/static references
5. **Hidden coupling / side effect table**  
   - shared shell, API coupling, giant inline JS, settings dual-lane, map/calendar dependence
6. **FR19 decision**  
   - delete / merge / extend / add 중 무엇을 선택했는지
7. **Spec §4 delta summary**  
   - product file delta
   - wrapper file delta
   - test file delta
   - canonical target
   - removal or merge target
   - new shim retirement wave
   - local README update
8. **Verification**
9. **FR20 / README gate**
10. **Test footprint decision**
11. **Direction Lock answers**
   - `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.8.1의 10문항에 yes/no + 한 줄 근거
12. **Next step or defer**

추가 규칙:

- queue / inventory / defer / comparison 표는 **각 batch run record 안**에만 남긴다. 별도 sibling inventory 문서를 만들지 않는다.
- legacy wrapper와 canonical 본문이 동시에 real owner가 되면 해당 run record는 실패로 기록한다.

## 8. Stop Conditions — 중단해야 하는 순간

아래 중 하나라도 보이면 해당 batch는 즉시 중단하고 defer row를 남긴다.

1. schema/Alembic/model 변경이 필요해짐
2. JSONB mutation contract 또는 persistence lifecycle 조정이 필요해짐
3. page move 없이 API canonicalization이 먼저 필요해짐
4. `layout.html`, `erp_dashboard.html`, `erp_beta_js.html`, shared map shell 전체를 같이 만져야 함
5. giant inline JS/template를 context namespace 이동만으로 해결할 수 없고 structural split이 필요함
6. Wave 5 large-file / WDCalculator류와 같은 new micro JS file / host-bootstrap wrapper 증식이 해결책처럼 보임
7. canonical과 legacy wrapper가 동시에 real logic owner가 됨
8. `business_calendar`, `/calendar`, WDCalculator, regional shell이 본 batch에 끼어듦

## 9. W4-B0 Prompt Contract — 첫 실행 턴 고정 프롬프트

다른 LLM이 Wave 4를 시작할 때 첫 턴은 아래 contract를 만족해야 한다.

1. `docs/AI_STATUS.md`, controlling spec, 이 plan, `foms/platform/blueprints.py`, Wave 3 closeout evidence, Measurement closeout evidence, Wave 2 truth map / adapter matrix evidence를 먼저 읽는다.
2. `W4-B0`는 docs-only로 끝낸다.
3. `W3-B6`가 없으면 stop하고 readiness failure를 run record에 남긴다.
4. page queue는 `cs`(current live pilot surface=`apps.erp_completion_page`), `production`, `construction`, `drawing`, `shipment-dashboard`, `shipment-settings`, `as`, `main shell`, `regional dashboards`뿐 아니라 `blueprints.py`의 추가 HTML blueprints(`apps.erp_history_page`, `apps.storage_dashboard`, `apps.order_pages`, `apps.order_edit`, `apps.order_trash`, `apps.user_pages`, `apps.admin`, `apps.excel_import`, `apps.auth`, `apps.calendar_page`, `apps.wdplanner_page`, `apps.api.channel_wam`)도 모두 분류한다.
5. `cs` low-coupling 여부를 explicit check로 남긴다.
6. 각 surface row는 최소 `registry lane`, `spec domain`, `FR20 context key`, `module path`, `blueprint symbol`, `route cluster`, `current owner state`, `template roots`, `static/partial roots`, `hidden coupling 요약`, `provisional tier`, `canonical target`, `shipment lane split 여부`를 포함해야 한다.
7. `production`마저 pilot으로 잠글 수 없으면 `construction` 이하로 자동 승격하지 말고 stop reason을 명시한다.
8. output에는 최소 `drift section`, `spec §2.9 disposition matrix`, `pilot parameter sheet`, `Direction Lock answers`, `shipment-dashboard/settings disposition`, `high-risk shell defer preview`, `§2.3 snapshot 대비 변경 row`가 포함돼야 한다.
9. output은 `W4-B0` run record 하나만 수정한다.

## 10. Completion Criteria — 이 계획서가 batch-ready로 인정되는 기준

- Wave 4와 Wave 3/5/6 경계가 분명하다.
- pilot이 giant shell이 아니라 smaller page slice로 잠겨 있다.
- executable pilot outcome이 `cs` 또는 `production`으로 제한돼 later batch topology와 충돌하지 않는다.
- pilot이 override되더라도 `W4-B1`~`W4-B3` run record/file 규칙이 generic하게 유지된다.
- `production`이 pilot으로 승격돼도 later batches가 이미 소비한 pilot을 다시 열지 않는다.
- dedicated static asset이 없는 context에 빈 디렉터리를 강제하지 않는다.
- template namespace stabilization이 giant template refactor와 분리돼 있다.
- run record contract가 delta / retirement / README / defer를 모두 강제한다.
- `spec §2.9` example context인 `shipment / drawing / production / construction / CS` disposition이 명시돼 있다.
- stop conditions가 shell drift, API drift, large-file drift를 모두 잡는다.
- early-stop이 발생해도 `W4-B7`로 partial closeout할 수 있다.
