# Wave 2 Batch W2-B1 — Blueprint truth extraction + bounded context map v1

> **batch ID:** W2-B1  
> **risk axis:** docs / owner mapping  
> **live truth source:** `foms/platform/blueprints.py` (snapshot 2026-04-13)  
> **실행일:** 2026-04-13

## 1. 요약

- `register_blueprints(app)`의 **`app.register_blueprint` 호출 순서**와 **non-blueprint runtime binding**을 line 기준으로 추출했다.
- 각 surface에 **registry lane → spec §2.3 domain → FR20 context key → owner state**를 부여하고, **evidence** 한 줄 이상을 남겼다.
- **canonical alias shim**은 `importlib` + `sys.modules` 교체가 확인된 **2개**(`apps.erp_measurement_dashboard`, `apps.api.erp_measurement`)만으로 고정했다.
- **thin adapter** 선례로 **`apps.api.orders`** 패키지만 명시적으로 분류했다(Orders boundary plan과 정합).

## 2. Runtime binding (non-blueprint)

`BlueprintBindings` 반환값. `app.register_blueprint`가 아님.

| 순서 | symbol | import module | evidence |
|------|--------|---------------|----------|
| R1 | `get_user_by_id` | `apps.auth` | `apps.auth`에서 함께 import; 세션/사용자 해석에 사용되는 root contract |
| R2 | `register_chat_socketio_handlers` | `apps.api.chat` | `chat_bp`와 동일 모듈에서 import; Socket.IO 핸들러 등록 콜백 |

## 3. `app.register_blueprint` 호출 순서 (authoritative)

`foms/platform/blueprints.py` 기준. **아래 seq는 등록 순서**다.

| Seq | blueprint symbol | module path (import) | registry lane | spec domain | FR20 context key | owner state | future canonical target (요약) | evidence |
|-----|------------------|----------------------|---------------|-------------|------------------|-------------|----------------------------------|----------|
| 1 | `auth_bp` | `apps.auth` | Auth / session | Auth / session bootstrap | `auth` | legacy owner | `foms/web/auth`, `foms/api/auth`, `foms/services/auth` | `Blueprint`·`login_required` 등 로직이 `apps.auth`에 존재 |
| 2 | `erp_bp` | `apps.erp` | ERP shell | ERP shell / landing | `erp` | legacy owner | `foms/web/*` matching | 허브 blueprint, `foms.services.*` re-export만 일부 |
| 3 | `erp_dashboard_bp` | `apps.erp_dashboard` | ERP pages | ERP shell / landing | `erp` | legacy owner | `foms/web/*` | page slice 미이전 |
| 4 | `erp_history_bp` | `apps.erp_history_page` | ERP pages | ERP shell / history | `erp` | legacy owner | `foms/web/*` | page slice 미이전 |
| 5 | `erp_drawing_workbench_bp` | `apps.erp_drawing_workbench` | Drawing pages | Drawing | `drawing` | legacy owner | `foms/web/drawing` | registry가 `apps.*` import |
| 6 | `erp_measurement_dashboard_bp` | `apps.erp_measurement_dashboard` | Measurement pages | Measurement | `measurement` | **canonical alias shim** | `foms/web/measurement` | docstring + `importlib.import_module('foms.web.measurement.dashboard')` + `sys.modules` 교체 |
| 7 | `erp_shipment_page_bp` | `apps.erp_shipment_page` | Shipment pages | Shipment | `shipment` | legacy owner | `foms/web/shipment` | page owner `apps` |
| 8 | `erp_as_page_bp` | `apps.erp_as_page` | AS / CS pages | Production / Construction / CS | `cs` | legacy owner | `foms/web/cs` | page owner `apps` |
| 9 | `erp_production_page_bp` | `apps.erp_production_page` | Production pages | Production | `production` | legacy owner | `foms/web/production` | page owner `apps` |
| 10 | `erp_construction_page_bp` | `apps.erp_construction_page` | Construction pages | Construction | `construction` | legacy owner | `foms/web/construction` | page owner `apps` |
| 11 | `erp_completion_page_bp` | `apps.erp_completion_page` | Completion pages | Production / Construction / CS | `completion` | legacy owner | `foms/web/*` | page owner `apps` |
| 12 | `files_bp` | `apps.api.files` | Files / storage API | Files / Storage | `files` | legacy owner | `foms/api/files`, `foms/services/files` | API contract owner `apps.api.*` |
| 13 | `address_bp` | `apps.api.address` | Address API | Files / Storage (address) | `orders` | legacy owner | `foms/api/address` | 주문/지역 주소 API; spec 표는 address를 별도 셀로 묶을 수 있음 |
| 14 | `orders_bp` | `apps.api.orders` | Orders API | Orders | `orders` | **thin adapter** | `foms/api/orders` | `from foms.api.orders import ... response` 위임; route shell만 `apps` |
| 15 | `notifications_bp` | `apps.api.notifications` | Notifications API | Channel / Notifications | `notifications` | legacy owner | `foms/api/notifications` | overlay owner |
| 16 | `erp_shipment_bp` | `apps.api.erp_shipment_settings` | Shipment API | Shipment | `shipment` | legacy owner | `foms/api/shipment` | `apps.api.*` blueprint |
| 17 | `erp_measurement_bp` | `apps.api.erp_measurement` | Measurement API | Measurement | `measurement` | **canonical alias shim** | `foms/api/measurement` | docstring + `importlib.import_module('foms.api.measurement')` |
| 18 | `erp_map_bp` | `apps.api.erp_map` | Map companion | Measurement map companion | `measurement` | legacy owner | `foms/api/measurement` family | 대형 로직·`Blueprint`가 `apps.api.erp_map`에 잔존 |
| 19 | `erp_orders_drawing_bp` | `apps.api.erp_orders_drawing` | ERP stage APIs | Orders (stage) | `orders` | legacy owner | `foms/api/orders` | `apps.api.erp_orders_*` 패턴 |
| 20 | `erp_orders_revision_bp` | `apps.api.erp_orders_revision` | ERP stage APIs | Orders (stage) | `orders` | legacy owner | `foms/api/orders` | 동일 |
| 21 | `erp_orders_draftsman_bp` | `apps.api.erp_orders_draftsman` | ERP stage APIs | Drawing / Orders | `drawing` | legacy owner | `foms/api/drawing` | 동일 |
| 22 | `erp_orders_production_bp` | `apps.api.erp_orders_production` | ERP stage APIs | Production | `production` | legacy owner | `foms/api/production` | 동일 |
| 23 | `erp_orders_construction_bp` | `apps.api.erp_orders_construction` | ERP stage APIs | Construction | `construction` | legacy owner | `foms/api/construction` | 동일 |
| 24 | `erp_orders_cs_bp` | `apps.api.erp_orders_cs` | ERP stage APIs | CS | `cs` | legacy owner | `foms/api/cs` | 동일 |
| 25 | `erp_orders_as_bp` | `apps.api.erp_orders_as` | ERP stage APIs | AS | `cs` | legacy owner | `foms/api/*` | 동일 |
| 26 | `erp_orders_completion_bp` | `apps.api.erp_orders_completion` | ERP stage APIs | Completion | `completion` | legacy owner | `foms/api/*` | 동일 |
| 27 | `personal_board_bp` | `apps.api.personal_board` | ERP aux API | ERP stage | `erp` | legacy owner | `foms/api/*` | overlay |
| 28 | `erp_orders_confirm_bp` | `apps.api.erp_orders_confirm` | ERP stage APIs | Orders | `orders` | legacy owner | `foms/api/orders` | overlay |
| 29 | `storage_dashboard_bp` | `apps.storage_dashboard` | Admin / storage UI | Files / Storage | `files` | legacy owner | `foms/web/*` | page owner `apps` |
| 30 | `chat_bp` | `apps.api.chat` | Chat + realtime | Chat + realtime | `chat` | legacy owner | `foms/api/chat` | HTTP + `register_chat_socketio_handlers` binding 동일 모듈 |
| 31 | `wdcalculator_bp` | `apps.api.wdcalculator` | WDCalculator | WDCalculator | `wdcalculator` | legacy owner | `foms/web/wdcalculator`, `foms/api/wdcalculator` | Wave 5 전 owner 고정 |
| 32 | `backup_bp` | `apps.api.backup` | Ops / backup API | Admin / ops | `admin` | legacy owner | `foms/api/admin` | overlay |
| 33 | `admin_bp` | `apps.admin` | Admin pages | Auth / Admin | `admin` | legacy owner | `foms/web/admin` | overlay |
| 34 | `user_pages_bp` | `apps.user_pages` | User pages | Auth / Admin | `auth` | legacy owner | `foms/web/auth` | overlay |
| 35 | `dashboards_bp` | `apps.dashboards` | Dashboards | ERP shell | `erp` | legacy owner | `foms/web/*` | overlay |
| 36 | `attachments_bp` | `apps.api.attachments` | Attachments API | Files / Storage | `files` | mixed owner | `foms/api/files` | 서비스 위임 가능하나 blueprint owner는 `apps` (plan §2.3 스냅샷과 정합) |
| 37 | `tasks_bp` | `apps.api.tasks` | Tasks API | Admin / ops | `admin` | legacy owner | `foms/api/*` | overlay |
| 38 | `events_bp` | `apps.api.events` | Events API | Admin / ops | `admin` | legacy owner | `foms/api/*` | overlay |
| 39 | `quest_bp` | `apps.api.quest` | Quest API | Admin / ops | `admin` | legacy owner | `foms/api/*` | overlay |
| 40 | `erp_orders_blueprint_bp` | `apps.api.erp_orders_blueprint` | Orders structured API | Orders | `orders` | legacy owner | `foms/api/orders` | `erp_orders_blueprint` / `structured` 물리 모듈 분리 |
| 41 | `erp_orders_structured_bp` | `apps.api.erp_orders_structured` | Orders structured API | Orders | `orders` | legacy owner | `foms/api/orders` | 동일 |
| 42 | `order_pages_bp` | `apps.order_pages` | Orders pages | Orders | `orders` | legacy owner | `foms/web/orders` | page owner `apps` |
| 43 | `order_edit_bp` | `apps.order_edit` | Orders pages | Orders | `orders` | legacy owner | `foms/web/orders` | 동일 |
| 44 | `order_trash_bp` | `apps.order_trash` | Orders pages | Orders | `orders` | legacy owner | `foms/web/orders` | 동일 |
| 45 | `excel_bp` | `apps.excel_import` | Orders / excel | Orders | `orders` | legacy owner | `foms/web/orders` | 동일 |
| 46 | `calendar_bp` | `apps.calendar_page` | Calendar | Orders / calendar | `orders` | legacy owner | `foms/web/orders` | spec: business_calendar 축은 별도 승인 전 정리 범위 밖 — **구조 변경 없이 owner만 기록** |
| 47 | `wdplanner_bp` | `apps.wdplanner_page` | Planner | WDCalculator / planner | `wdcalculator` | legacy owner | `foms/web/wdcalculator` | overlay |
| 48 | `channel_integration_bp` | `apps.api.channel_integration` | Channel | Channel / Notifications | `channel` | legacy owner | `foms/api/channel` | overlay |
| 49 | `channel_functions_bp` | `apps.api.channel_functions` | Channel | Channel | `channel` | legacy owner | `foms/api/channel` | overlay |
| 50 | `channel_webhooks_bp` | `apps.api.channel_webhooks` | Channel | Channel | `channel` | legacy owner | `foms/api/channel` | overlay |
| 51 | `channel_shortlink_bp` | `apps.api.channel_wam` | Channel WAM | Channel | `channel` | legacy owner | `foms/api/channel` | 동일 모듈에서 3개 BP export |
| 52 | `channel_wam_bp` | `apps.api.channel_wam` | Channel WAM | Channel | `channel` | legacy owner | `foms/api/channel` | 동일 |
| 53 | `channel_wam_api_bp` | `apps.api.channel_wam` | Channel WAM | Channel | `channel` | legacy owner | `foms/api/channel` | 동일 |
| 54 | `erp_estimates_bp` | `apps.api.erp_estimates` | ERP estimates API | ERP stage / Orders | `orders` | legacy owner | `foms/api/orders` | overlay |
| 55 | `debug_bp` | `apps.api.debug` | Debug API | Admin / ops | `admin` | legacy owner | `foms/api/admin` | 개발/디버그 surface |

**등록 개수:** 55.

## 4. Precedent lanes (Wave 3 확장 기준)

| lane | surface | role |
|------|---------|------|
| Measurement | `erp_measurement_dashboard_bp`, `erp_measurement_bp` | canonical alias shim (양쪽 모듈에서 `foms.*`로 치환) |
| Orders API | `orders_bp` | thin adapter (`foms.api.orders` response helper 위임) |

## 5. `this plan §2.3` illustrative snapshot 대비 변경된 row

> 상위 실행 계획서 `§2.3` 표는 **illustrative**이며 본 run record가 supersede한다.

| 항목 | §2.3 스냅샷 | W2-B1 판정 | 사유 |
|------|-------------|------------|------|
| `apps.api.erp_map` | Measurement map companion · legacy owner | 동일 유지 | 스냅샷과 일치 |
| `apps.api.attachments` | mixed / legacy 혼재 표현 | **mixed owner**로 명시 | 서비스 분리 흔적 가능하나 blueprint 관점 owner는 `apps` |
| Orders domain | `apps.api.orders` thin adapter만 강조 | **동일 + 구체 모듈 추가** | `erp_orders_*`, `erp_orders_blueprint`, `erp_orders_structured`, `order_*`, `excel_import`, `calendar_page` 등 **별도 행**으로 풀어 기록 |
| Channel | 4 modules / 6 registers | **확정:** `channel_wam` 한 모듈에서 **3 blueprint** (seq 51–53) | 스냅샷 서술과 수치 일치 |
| `address_bp` | Files / notifications 행에 묶여 있음 | **별도 lane**으로 분리(주소 API) | registry 상 독립 모듈 |
| Calendar | (스냅샷에 명시 없음) | `calendar_bp`는 Orders lane **단,** spec §1.2 FR16 business_calendar 축은 별도 승인 전 | owner만 `orders` 맵에 연결; **동작/스코프 변경 없음** |

## 6. W2-B2에서 reconcile할 spec drift (입력)

1. §2.3 Orders 행은 **domain 요약**이며, surface-level 목록은 **본 run record 표**가 우선이다.
2. “`apps/` thin wrapper” 표현은 **모든** `apps.*`가 이미 thin이 아님 — **대부분 legacy owner**다.
3. Measurement **외** surface를 thin adapter로 잘못 일반화하지 않도록 spec 문구 보강 필요.

## 7. Unresolved / residual risk

| topic | 상태 |
|-------|------|
| 일부 `apps.api.*` 파일 내부 위임 비율 | 파일별 deep audit는 Wave 3 범위; B1에서는 **blueprint owner** 기준만 고정 |
| `mixed owner` vs `legacy owner` 경계 | attachments 등 소수만 mixed; 나머지는 보수적으로 legacy |

## 8. Direction Lock (§7.2 요약)

1. `foms/platform/blueprints.py`를 live truth로 사용했는가? **예**  
2. live owner를 thin adapter로 과장하지 않았는가? **예** (thin은 `orders`만 명시)  
3. `apps/`에 새 장기 route logic을 추가하지 않았는가? **예 (docs-only)**  
4. blueprint name / url_prefix / order / binding 변경 없음? **예**  
5. spec 충돌 시 code보다 docs 우선? **해당 없음 (B1)**  
6. canonical target 명명이 §2.3과 충돌? **없음 (요약 수준)**  
7–8. README / defer? **B1 해당 없음**  
9. 다음 LLM 오해 방지? **표 + evidence로 고정**  
10. Wave 3 준비? **예 — 선례 lane 분리**

## 9. Verification (W2-B1)

| 검사 | 결과 |
|------|------|
| docs-only | ✅ |
| 모든 surface 4분류 중 하나 | ✅ |
| evidence 필드 존재 | ✅ |
| Measurement/Orders 외 thin adapter 오인 승격 없음 | ✅ |

## 10. 산출물

- 본 파일: `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md`

---

**touched files:** `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md`  
**canonical target (batch):** bounded context map v1 고정  
**retirement / reopen wave:** 해당 없음  
**verification result:** PASS  
**residual risk:** §7
