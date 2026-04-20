# Wave 4 Batch W4-B0 — Readiness gate + authoritative page queue lock

> **batch ID:** W4-B0  
> **risk axis:** docs / truth  
> **live truth source:** `foms/platform/blueprints.py` (검증 시점: 2026-04-13, `register_blueprints` 등록 순서)  
> **실행일:** 2026-04-13

## Scope lock

- **허용:** 본 run record만 생성/갱신.  
- **금지:** 런타임 코드, `foms/platform/blueprints.py`, controlling spec normative 본문, Wave 4 plan 원문.

## Inputs consumed (handoff gate)

| # | 산출물 | 상태 |
|---|--------|------|
| 1 | `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` (W3-B6) | ✅ 존재·소비 |
| 2 | W3-B0 readiness queue (W3 증거) | ✅ W3-B6에 요약 반영됨 |
| 3 | `docs/plans/2026-04-10-step5-batch66-closeout-run-record.md` (Measurement closeout) | ✅ 존재·소비 — canonical `foms/web/measurement/dashboard.py` 선례 확정 |
| 4 | `foms/platform/blueprints.py` | ✅ live registry — 본 배치 권위 큐의 유일한 순서 기준 |
| 5 | `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` | ✅ 레인·도메인·FR20 교차 참조 |
| 6 | `docs/plans/2026-04-13-wave2-batch6-closeout-run-record.md` | ✅ Wave 2 종료 맥락 |

## Wave 2 key normalization

| 항목 | 값 |
|------|-----|
| registry lane | `foms/platform/blueprints.py`의 `app.register_blueprint` 등록 단위(Seq) |
| spec domain | `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.3·§2.9 맥락 |
| FR20 context key | bounded context / 페이지 슬라이스 식별자(예: `completion`, `production`, `shipment`) |

## Drift — `this plan §2.3` snapshot 대비 변경 row

| 항목 | §2.3 스냅샷(illustrative) | W4-B0 live 판정 | 사유 |
|------|---------------------------|-----------------|------|
| 큐 완전성 | 주요 lane 위주 표 | **55개 등록 BP 전부** 분류 | 실행 계획 §2.3.1 — additional registry lane 전부 포함 |
| `erp_completion` | CS family로 서술 | **`completion` FR20 키 + pilot `cs`** | live surface `apps.erp_completion_page`; §2.4에서 `cs`가 pilot 표면 |
| Shipment | 단일 `Shipment` 행 | **`shipment-dashboard` + `shipment-settings` 2행** | 계획 §5.1.10 — dashboard vs settings 분리 |
| Channel WAM | 표에 없음 | **3 BP (`channel_shortlink_bp`, `channel_wam_bp`, `channel_wam_api_bp`)** | 동일 모듈 `apps.api.channel_wam` — HTML-emitting API-first |
| `apps.auth` | 표에 없음 | **Auth UI lane** | §2.3.1 additional — 반드시 분류 |

## spec §2.9 disposition matrix (예시 context — Wave 4 본 배치 관점)

| Context / lane | disposition | 메모 |
|------------------|---------------|------|
| **CS (completion)** | **in-scope Wave 4 pilot** | `pilot_context=cs`, live surface `apps.erp_completion_page` |
| **production** | in-scope — **pilot 이후 dashboard family 후보 1순위** | W4-B4에서 `construction`과 비교 |
| **construction** | in-scope — dashboard family 후보 | W4-B4 비교 대상 |
| **drawing** | **deferred** (Wave 4 mainline code batch 후속) | 2-route cluster + shared drawing partials — §4.2.9 |
| **shipment-dashboard** | **deferred** | `apps.erp_shipment_page` — Tier 3 · giant template + dedicated static |
| **shipment-settings** | **deferred** | `apps.api.erp_shipment_settings` — `/erp/shipment-settings` HTML + API dual-lane |
| Measurement | **Tier 0 precedent** (reference only) | Step 5 closeout — `foms/web/measurement` |
| AS / main ERP shell / regional | **deferred** | high-risk shell — Wave 5/별도 |

## Pilot low-coupling explicit check (`cs` → `apps.erp_completion_page`)

| 검사 | 결과 |
|------|------|
| 단일 page module | ✅ `apps.erp_completion_page` 단일 BP |
| 단일 primary route cluster | ✅ `GET /erp/completion` (단일 뷰 함수) |
| dashboard vs detail split | ✅ 동일 cluster 내 detail 라우트 없음 |
| shared shell | ⚠️ `layout.html`, `erp_sub_nav`, 조건부 `erp_mobile_shell` — **Wave 4에서 이동 금지(하드 프리즈)** |
| giant inline 전용 템플릿 | ⚠️ `partials/erp_completion_scripts.html` 등 — **본 Wave에서는 namespace·owner만 정리, 대형 분해는 Wave 5** |
| **판정** | ✅ 계획 §2.3 **Tier 1 low-coupling page** 정의 및 §2.4 step 1에 따라 **pilot은 `cs`로 고정** (executable outcome = `cs`만 해당; `production`은 폴백 불필요) |

## Executable pilot outcome lock

| 항목 | 값 |
|------|-----|
| **pilot_context** | **`cs`** |
| **current live pilot surface** | **`apps.erp_completion_page`** |
| **Executable pilot outcome** | **`cs`** (`production`으로 폴백하지 않음 — low-coupling 통과) |
| **Stop (revised plan)** | **해당 없음** — `production`을 pilot으로 잠글 수 없는 상황 **아님** |

## Pilot parameter sheet

| 필드 | 값 |
|------|-----|
| pilot_context | `cs` |
| current live pilot surface | `apps.erp_completion_page` |
| blueprint symbol / name | `erp_completion_page_bp` / `erp_completion_page` |
| route cluster / primary path | `GET /erp/completion` |
| legacy module path | `apps/erp_completion_page.py` |
| canonical module path (W4-B2 대상) | `foms/web/cs/completion_dashboard.py` (Measurement의 `dashboard.py`와 동일 패턴: 단일 엔트리 파일명) |
| canonical template root (W4-B3 대상) | `templates/cs/completion_dashboard.html` |
| legacy template root | `templates/erp_completion_dashboard.html` → thin `{% extends "cs/completion_dashboard.html" %}` (Measurement `erp_measurement_dashboard.html` 선례) |
| FR20 context key | `completion` (CS family; spec·W2-B1과 정합) |
| minimum automated checks | `APP_OK`, `verify_result.py`; `tests/test_foms_namespace_imports.py`에 **cs shim** 검증 추가(배치 내) |
| minimum manual smoke | `/erp/completion` 로드·서브네비·모달 존재 확인(체크리스트는 W4-B3 run record에 이행) |

## Direction Lock (10문항, docs-only)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 단일 권위 큐·pilot 잠금으로 SoT 명확화 |
| 2 | yes | 스냅샷 복붙이 아닌 `blueprints.py` 기준 재작성 |
| 3 | yes | 새 코드 없음 — 문서만 |
| 4 | yes | 큐 행은 유지보수 가능한 chunk 단위 분류 |
| 5 | yes | 파일 수 증가 없음 |
| 6 | N/A | 순증가 없음 |
| 7 | N/A | README는 Wave 4 코드 배치에서 FR20 충족 시만 |
| 8 | yes | 반복 시 표만 비대해지지 않도록 레인·defer로 구분 |
| 9 | yes | 페이지/API/쉘 경계 문서화 |
| 10 | yes | 구조 문서만 — 기능 변경 없음 |

## High-risk shell defer preview (Wave 4 mainline code에 넣지 않음)

- `templates/layout.html`, `erp_dashboard.html`, `partials/erp_beta_js.html`, `erp_sub_nav.html`, `erp_mobile_shell.html`, `regional_dashboard.html` — 계획 하드 프리즈  
- `business_calendar`, `/calendar`, shared map shell, chat/socket/channel realtime  
- `shipment-dashboard` giant template + static, `shipment-settings` HTML+API  
- `erp_as_page` (AS), `erp_drawing_workbench` (detail+dashboard), main ERP shell  

## Authoritative page queue — `register_blueprint` 순서 (55)

> 각 행: **registry lane | spec domain | FR20 | module | blueprint | route cluster(요약) | owner | template/static | coupling | tier | canonical target | shipment split**  
> API-only JSON: template roots = `N/A (JSON)`; static = `N/A` unless noted.

| Seq | registry lane | spec domain | FR20 | module | blueprint | route cluster | owner | template / static·partial roots | hidden coupling | tier | canonical target | shipment / notes |
|-----|---------------|-------------|------|--------|-----------|---------------|-------|--------------------------------|-----------------|------|-------------------|------------------|
| 1 | Auth UI | Auth/session | `auth` | `apps.auth` | `auth_bp` | 로그인·세션 등 | legacy | `templates` auth 계열 | 세션 | T2 | `foms/web/auth` | — |
| 2 | ERP shell | ERP landing | `erp` | `apps.erp` | `erp_bp` | 허브 | legacy | `templates/erp_*` | shell | T3 | `foms/web/erp_shell` | — |
| 3 | ERP pages | ERP shell | `erp` | `apps.erp_dashboard` | `erp_dashboard_bp` | `/erp` 대시보드 | legacy | `erp_dashboard.html` 등 | layout·beta | T3 | `foms/web/erp_shell` | — |
| 4 | ERP pages | history | `erp` | `apps.erp_history_page` | `erp_history_bp` | `/erp/history` | legacy | `erp_history*.html` | shell | T2 | `foms/web/history` | support |
| 5 | Drawing pages | Drawing | `drawing` | `apps.erp_drawing_workbench` | `erp_drawing_workbench_bp` | dashboard+detail | legacy | `erp_drawing_*` | shared drawing scripts | T2 | `foms/web/drawing` | — |
| 6 | Measurement pages | Measurement | `measurement` | `apps.erp_measurement_dashboard` | `erp_measurement_dashboard_bp` | `/erp/measurement` | **canonical shim** | `measurement/dashboard.html` + legacy extend | map | T0 | `foms/web/measurement` | — |
| 7 | **shipment-dashboard** | Shipment | `shipment` | `apps.erp_shipment_page` | `erp_shipment_page_bp` | `/erp/shipment` | legacy | `erp_shipment*.html`, `static/js/erp/shipment*` | dashboard+static | T3 | `foms/web/shipment` | **dashboard lane only** |
| 8 | AS / CS pages | CS/AS | `cs` | `apps.erp_as_page` | `erp_as_page_bp` | `/erp/as` | legacy | giant AS template | editor | T3 | `foms/web/cs` | — |
| 9 | Production pages | Production | `production` | `apps.erp_production_page` | `erp_production_page_bp` | `/erp/production/dashboard` | legacy | `erp_production_dashboard.html` + partials | sub_nav·filters | T2 | `foms/web/production` | — |
| 10 | Construction pages | Construction | `construction` | `apps.erp_construction_page` | `erp_construction_page_bp` | `/erp/construction/dashboard` | legacy | `erp_construction_dashboard.html` + partials | mine·self_measurement | T2 | `foms/web/construction` | — |
| 11 | **Completion / CS pilot** | CS / completion | `completion` | `apps.erp_completion_page` | `erp_completion_page_bp` | `/erp/completion` | **Wave 4 pilot** | `erp_completion_dashboard.html`, `partials/erp_completion_*` | sub_nav·mobile | T1 | **`foms/web/cs`** | — |
| 12 | Files API | Files/storage | `files` | `apps.api.files` | `files_bp` | `/api/files`… | thin/API | N/A | storage | API | `foms/api/files` | — |
| 13 | Address API | Orders/address | `orders` | `apps.api.address` | `address_bp` | `/api/address`… | thin/API | N/A | API | API | `foms/api/address` | — |
| 14 | Orders API | Orders | `orders` | `apps.api.orders` | `orders_bp` | `/api/orders`… | thin adapter | N/A | API | API | `foms/api/orders` | — |
| 15 | Notifications API | Notifications | `notifications` | `apps.api.notifications` | `notifications_bp` | JSON | legacy | N/A | API | API | `foms/api/notifications` | — |
| 16 | **shipment-settings** | Shipment | `shipment` | `apps.api.erp_shipment_settings` | `erp_shipment_bp` | `/erp/shipment-settings` + `/api/erp/shipment-settings` | legacy | **HTML** `erp_shipment_settings.html` + API | dual-lane | T3 | `foms/web/shipment` + API | **settings lane** |
| 17 | Measurement API | Measurement | `measurement` | `apps.api.erp_measurement` | `erp_measurement_bp` | JSON | shim | N/A | API | API | `foms/api/measurement` | — |
| 18 | Map API | Measurement map | `measurement` | `apps.api.erp_map` | `erp_map_bp` | map JSON | legacy | N/A | API | API | `foms/api/measurement` | — |
| 19–28 | ERP stage APIs | Orders stages | mixed | `apps.api.erp_orders_*` | `erp_orders_*_bp` | JSON | legacy | N/A | API | API | `foms/api/orders` | — |
| 27 | Personal board API | ERP aux | `erp` | `apps.api.personal_board` | `personal_board_bp` | JSON | thin | N/A | API | API | `foms/api/personal_board` | — |
| 29 | Storage dashboard UI | Files/storage UI | `files` | `apps.storage_dashboard` | `storage_dashboard_bp` | storage UI | legacy | storage templates | ops | T2 | `foms/web/storage` | out-of-mainline |
| 30 | Chat | Chat | `chat` | `apps.api.chat` | `chat_bp` | + socket | legacy | N/A | realtime | T3 | defer | — |
| 31 | WDCalculator | WDCalculator | `wdcalculator` | `apps.api.wdcalculator` | `wdcalculator_bp` | — | legacy | templates wdcalculator | giant FE | T3 | Wave 5 | — |
| 32 | Backup API | Admin/ops | `admin` | `apps.api.backup` | `backup_bp` | JSON | legacy | N/A | API | API | defer | — |
| 33 | Admin pages | Admin | `admin` | `apps.admin` | `admin_bp` | admin UI | legacy | admin templates | — | T2 | `foms/web/admin` | non-ERP root |
| 34 | User pages | Auth | `auth` | `apps.user_pages` | `user_pages_bp` | user UI | legacy | user templates | — | T2 | `foms/web/auth` | non-ERP root |
| 35 | Regional dashboards | ERP shell | `erp` | `apps.dashboards` | `dashboards_bp` | regional | legacy | `regional_dashboard.html` | giant | T3 | defer | — |
| 36–41 | Aux APIs | Files/orders/admin | mixed | `apps.api.*` | `attachments_bp`… | JSON | mixed | N/A | API | API | `foms/api/*` | — |
| 42–44 | Order pages | Orders | `orders` | `apps.order_*` | `order_*_bp` | 주문 UI | legacy | order templates | — | T2 | `foms/web/orders` | non-ERP root |
| 45 | Excel import | Orders | `orders` | `apps.excel_import` | `excel_bp` | import UI | legacy | templates | — | T2 | `foms/web/orders` | — |
| 46 | Calendar | Calendar | `orders` | `apps.calendar_page` | `calendar_bp` | calendar | legacy | calendar | business_calendar | out | defer | spec out |
| 47 | WDPlanner | Planner | `wdcalculator` | `apps.wdplanner_page` | `wdplanner_bp` | planner | legacy | — | separate | out | defer | separate track |
| 48–50 | Channel | Channel | `channel` | `apps.api.channel_*` | `channel_*_bp` | JSON/webhook | legacy | N/A | API | API | `foms/api/channel` | — |
| 51–53 | **Channel WAM HTML** | Channel | `channel` | `apps.api.channel_wam` | `channel_shortlink_bp`, `channel_wam_bp`, `channel_wam_api_bp` | HTML+redirect | legacy | `channel_wam*.html` | HTML-emitting | T3 | `foms/api/channel` | **classify only** |
| 54 | ERP estimates API | Orders | `orders` | `apps.api.erp_estimates` | `erp_estimates_bp` | JSON | legacy | N/A | API | API | defer | W3 backlog |
| 55 | Debug API | Admin | `admin` | `apps.api.debug` | `debug_bp` | JSON | legacy | N/A | API | API | defer | — |

> **Seq 12–55 요약 압축:** 본 표는 Wave 4 **ERP page slice mainline**에 직접 들어가는 행(Seq 3–11, 16, 29 등)을 상세화했고, 나머지 API·주문 루트 UI는 W2-B1 Seq 12–55와 동일 순서·모듈 경로로 **정합**한다. 상세 55행 전개가 필요하면 `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` §3 테이블을 **등록 순서 동일**로 병기한다.

## Verification (W4-B0)

| 검사 | 결과 |
|------|------|
| docs-only | ✅ |
| W3-B6 존재 | ✅ |
| `cs` pilot explicit check | ✅ 통과 → **pilot `cs` lock** |
| executable outcome ∈ {`cs`,`production`} | ✅ **`cs`** |
| `production` 폴백 필요 | ❌ 불필요 |
| Direction Lock 10문항 | ✅ |
| shipment 2-row split | ✅ |
| §2.9 matrix + drift | ✅ |

## Next batch

- **W4-B1** — `docs/plans/2026-04-13-wave4-batch1-pilot-contract-freeze-run-record.md` — pilot `cs` public contract freeze.
