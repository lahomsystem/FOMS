# 워커 A 보고 원문 — 생산팀 STAFF(team PRODUCTION) 권한·라우트 전수 (2026-11-09)

> 원장 `2026-11-09-tablet-production-ui-ledger.md` §3.A 의 본문. 워커(Fable 5.1, effort high, 읽기 전용) 보고를 그대로 붙였다. 총괄 재확인 결과는 원장 §6 에.

**방법**: `PYTHONPATH=워크트리 DATABASE_URL=sqlite:///…wa.db FOMS_SKIP_DB_INIT=1 python -X utf8 dump_urlmap.py` 로 앱 import 성공(`APP_OK`), `app.app.url_map` 537 규칙을 스크래치패드 `urlmap.tsv` 에 덤프. 데코레이터는 소스 grep 으로 대조. 기준 커밋 `ea4376ea1`.

**권한 모델 핵심(확인됨)**
- `can_edit_erp` = ADMIN 또는 team∈("CS","SALES")(+회계 alias) — `foms/services/erp_permissions.py:18, :366-380`. 생산팀 → False.
- `can_edit_construction_schedule` = can_edit_erp 또는 SHIPMENT 팀 STAFF/MANAGER — `:383-399`. 생산팀 → False.
- 정책 엔진: STAFF 는 `team_has_capability(team, policy.teams)` 로만 통과 — `foms/services/orders/order_mutation_policy.py:416`. `PRODUCTION_EDIT` teams=(CS,SALES,PRODUCTION) `:180`, `SHIPMENT_EDIT`=(CS,SALES,SHIPMENT) `:199`, `STAFF_MUTATION` teams="*" `:176`.
- `role_required([...STAFF])` 는 STAFF 통과, 실패 시 403 아닌 flash+302 홈 — `foms/web/auth/routes.py:345-363`.
- 팀 전용 before_request 는 CONSTRUCTION 만 있다(`foms/platform/http.py:272-300`). 생산팀을 막는 전역 훅 없음.

## 표 1 — 화면 라우트 전수표

모집단: url_map 537 규칙 중 HTML GET 화면 49개(`/erp/*`·`/wdcalculator*`·`/notices`·`/brain*`·`/edit`·`/admin/notices*`·`/profile`·`/`·`/orders/`·`/trash`). 아래는 내비(레일·서브내비·모바일 셸·PC 상단)와 시트 fragment 로 닿는 전부.

| 경로 | 엔드포인트 | 권한 | 생산팀 STAFF 결과 | 근거 | 비고 |
|---|---|---|---|---|---|
| `/` | order_pages.index | login | 200(모바일 코호트면 302→/erp/dashboard) 확인됨 | foms/web/orders/listing.py:153-160 | 로그인 기본 착지(아래 4절) |
| `/orders/` | order_pages.orders_index_alias | login | 200 추정 | urlmap | |
| `/erp/dashboard` | erp_dashboard.erp_dashboard | login | 200 확인됨 | foms/web/orders/dashboard.py:154-156 | 레일·서브내비·모바일 1번 탭 |
| `/erp/dashboard/tablet-sheet/<id>` | erp_dashboard_tablet_sheet | login + **can_edit_erp(ERP 주문)** | **403 확인됨** | dashboard.py:627-629, :653-654 | 태블릿 전용. 컨트롤타워 행 탭의 시트 |
| `/erp/dashboard/field-ops` · `field-calendar` · `calendar-colors`(GET) | erp_dashboard.* | login | 200 확인됨 | dashboard.py:687-689, 734-736, 779-781 | |
| `/erp/orders/<id>/mobile` | erp_order_mobile_detail | login | 200 확인됨 | dashboard.py:828-830 | 모바일 상세 |
| `/erp/orders/<id>` | order_edit.redirect_legacy_erp_order_detail | login+role STAFF | 302→`/edit/<id>`→302 `/`(아래) 확인됨 | foms/web/orders/edit.py:203-206 | |
| `/edit/<id>` (ERP 주문) | order_edit.edit_order | login+role + can_edit_erp / 출고팀 예외 | **302 `/` + flash "수정 권한이 없습니다" 확인됨**(403 아님) | edit.py:237-239, :255-260 | 시트의 [ERP 편집]·첨부 링크가 여기로 감 |
| `/erp/measurement` | erp_measurement_dashboard | login | 200 확인됨 | foms/web/measurement/dashboard.py:192-194 | 시트 선택자에 없음 |
| `/erp/drawing-workbench` | erp_drawing_workbench_dashboard | login | 200 확인됨 | foms/web/drawing/workbench.py:639-641 | |
| `/erp/drawing-workbench/<id>` | …_detail | login | 200 확인됨 | workbench.py:1137-1139 | |
| `/erp/drawing-workbench/<id>/wizard` | …_wizard | login | 200(페이지) 확인됨 · 쓰기 API 는 DRAWING_ASSIGNED 403 | foms/web/drawing/wizard.py:52-54, manifest | |
| `/erp/drawing-workbench/tablet-sheet/<id>` | …_tablet_sheet | login | 200 확인됨 | foms/web/drawing/tablet_sheet.py:130-132 | 태블릿 전용. [시트 전달] 은 DRAWING_ASSIGNED 403 |
| `/erp/production/dashboard` | erp_production_dashboard | login | 200 확인됨 | foms/web/production/dashboard.py:93-95 | `can_act_production`=True(:239-241) |
| `/erp/production/tablet-sheet/<id>` | erp_production_tablet_sheet | login | 200 확인됨 | dashboard.py:408-410 | 태블릿 전용. 칸반 카드 시트 |
| `/erp/shipment` | erp_shipment_dashboard | login | 200 확인됨 | foms/web/shipment/dashboard.py:363-365 | |
| `/erp/shipment/tablet-sheet/<id>` | erp_shipment_tablet_sheet | login | 200(읽기 전용, `sheet_can_ack`=False) 확인됨 | shipment/dashboard.py:758-760, :784 | 태블릿 전용 |
| `/erp/shipment-settings` | erp_shipment.erp_shipment_settings | 미확인 | 미확인 | urlmap | 5절 |
| `/erp/as` | erp_as_dashboard | login | 200 확인됨 | foms/web/cs/as_dashboard.py:235-237 | 행 탭 → 기본 edit fragment → 403(H1) |
| `/erp/as/card-detail/<id>` · `/erp/as/timeline/<id>` | erp_as_page.* | login | 200 확인됨 | as_dashboard.py:153-155, 194-196 | |
| `/erp/construction/dashboard` | erp_construction_dashboard | login | 200 확인됨 | foms/web/construction/dashboard.py:68-70 | 작업모드 카드는 시트 선택자 밖 |
| `/erp/completion` | erp_completion_dashboard | login | 200 확인됨 | foms/web/cs/completion_dashboard.py:532-534 | 태블릿 그리드는 모바일 v2 셸이면 전 팀 렌더(:549-553) |
| `/erp/completion/tablet-sheet/<id>` | erp_completion_tablet_sheet | login | 200 확인됨 | completion_dashboard.py:583-585 | 태블릿 전용 |
| `/erp/completion/export.csv` | erp_completion_export | login | 200 추정 | completion_dashboard.py:601-603 | |
| `/erp/history/` | erp_history.history_dashboard | login | 200 확인됨 | foms/web/orders/history.py:163-165 | |
| `/erp/history/tablet-sheet/<id>` | history_tablet_sheet | login | 200 확인됨(404만) | history.py:384-386, :408 | 태블릿 전용 — H1 반례 |
| `/erp/settlement` | erp_settlement_dashboard | login + `can_view_settlement_dashboard`(회계·ADMIN) | **403 확인됨** | foms/web/cs/settlement_dashboard.py:90-92, :102-104 | 내비에서 `policy_can('SETTLEMENT_DASHBOARD_READ')` 로 숨김(erp_sub_nav.html:70, erp_mobile_shell.html:59) |
| `/erp/partner-statements*` | erp_partner_statements_page.* | login + `_guard`(can_manage_statements: CS·ADMIN) | **403 확인됨** | foms/web/cs/partner_statements.py:25-27, :30-34 | 내비 숨김(erp_sub_nav.html:78) |
| `/erp/my-commission` | sales_commission_web.my_commission | 프리랜서 전용 | 비노출·거부 추정 | erp_mobile_shell.html:67-69 | |
| `/wdcalculator` · `/wdcalculator/product-settings` | wdcalculator.* | login | 200 확인됨 | foms/api/wdcalculator/blueprint.py:485-487 | PC 상단·레일 '계산기' |
| `/notices` | notices_web.notice_list | login | 200 확인됨 | foms/web/notices.py:20-22 | PC 드롭다운(layout_nav.html:82) |
| `/admin/notices*` | notices_admin.* | role ADMIN/MANAGER | **302 홈 + flash 확인됨** | foms/web/admin/notices.py:25, :86-89 | 내비에 없음 |
| `/brain` | brain_web.index | login + `screen_viewer`(ADMIN·승인팀 MANAGER) | STAFF → 물어보기 열렸으면 302 `/brain/ask`, 아니면 **404** 확인됨 | foms/web/brain.py:120-131; foms/services/brain/access.py:28-42 | PC 드롭다운(layout_nav.html:88) |
| `/brain/ask` | brain_web.ask_page | 단계 설정(admin→leads→all) | 조건부(DB 설정) — 미확인 | foms/services/brain/chat_access.py:49-64 | |
| `/change-logs` | admin.change_logs | login | 200 추정 | foms/web/admin/audit.py:436-438 | PC 드롭다운(:79) |
| `/profile` | auth.profile | login(ACCOUNT_SELF) | 200 확인됨 | manifest | |
| `/api/foms/fragment/order/<id>/edit` | foms_fragment.order_edit_fragment | login+role + **can_edit_erp** | **403 확인됨** | foms/api/fragment.py:54, :70-72, :107 | 사이드 시트 기본 URL(H1) |
| `/api/foms/fragment/order/<id>/timeline` | order_timeline_fragment | login | 200 확인됨 | fragment.py:138-140 | |

**내비에 실제로 보이는 것(생산팀 STAFF)**
- PC 상단: ERP 대시보드·WDCalculator(시공팀만 숨김) — `templates/partials/shared/layout_nav.html:208-215`; 드롭다운 프로필·변경이력·공지·회사지식 `:76-88`; 관리자 메뉴 없음(`:100`).
- ERP 서브내비: 9탭 전부(`erp_sub_nav.html:4` 는 CONSTRUCTION 만 좁힘), 정산·명세서는 policy 로 숨김.
- 태블릿 레일: 9탭 + 계산기 — `foms/services/foms_split_view.py:129-170`(CONSTRUCTION 만 좁힘), 렌더 조건 `erp_mobile_v2_enabled ∧ /erp|/wdcalculator`(layout_nav.html:235-237).
- 모바일 셸 하단 탭: 기본 분기 `['dashboard','measurement','construction','shipment']` — `erp_mobile_shell.html:54-56`. **'생산'은 서랍에만 있고 하단 탭에 없다**(확인됨).

## 표 2 — 생산 관련 쓰기 API

| 경로 | 데코레이터 / 정책 id·팀 | 생산팀 결과 | 근거 |
|---|---|---|---|
| POST `/api/orders/<id>/production/start` | `_production_steps_edit_required`(ADMIN 또는 CS/SALES/PRODUCTION) + 매니페스트 PRODUCTION_EDIT | 200(권한 통과; 단계·보류·도면 게이트는 409) 확인됨 | foms/api/production/orders.py:70, :90-119, :745-747; manifest |
| POST `…/production/complete` | 같음 | 200 확인됨 | orders.py:908-910 |
| POST `…/production/rework` | 같음 | 200 확인됨 | :994-996 |
| POST `…/production/cancel` | 같음 | 200 확인됨 | :1148-1150 |
| POST `…/production/uncomplete` | 같음 | 200 확인됨 | :1249-1251 |
| POST `…/production/change-ack` | 같음 | 200 확인됨 | :1331-1333 |
| GET `…/production/steps` | login 만 | 200 확인됨 | :1398-1405 |
| POST `…/production/steps` | 같음(PRODUCTION_EDIT) | 200 확인됨 | :1436-1438 |
| POST `…/production/defect` | 같음 | 200 확인됨 | :1522-1524 |
| POST `…/production/hold` | 같음 | 200 확인됨 | :1655-1657 |
| POST `/api/orders/<id>/logistics` | login + 인라인 `evaluate_policy(SHIPMENT_EDIT)` | **403 확인됨** | :1729-1731, :1757-1759 |
| POST `/api/erp/shipment/update/<id>` | `@erp_edit_required`(can_edit_erp) + role | **403 확인됨** (매니페스트는 SHIPMENT_EDIT 지만 데코레이터가 CS/SALES 로 더 좁다 — 출고팀 STAFF 도 403, 부수 발견) | foms/api/shipment/settings.py:189-193; erp_permissions.py:424-440 |
| GET `/api/orders/<id>/attachments` | login | 200 확인됨 | foms/api/files/order_routes.py:299-301 |
| POST `/api/orders/<id>/attachments`(업로드) | login + STAFF_MUTATION(teams="*") | 200 확인됨 | order_routes.py:375-377; manifest |
| GET `/api/files/view/<key>`(도면 썸네일·첨부 보기) | login | 200 확인됨 | foms/api/files/routes.py:210-212 |
| GET `/api/orders/<id>/detail-payload` | login | 200 확인됨 | foms/api/erp_orders_structured.py:1042-1044 |
| POST `/erp/api/notifications/<id>/read`·`read-all`·`ack`·`archive` | MARK/ACK/ARCHIVE_OWN_NOTIFICATION(viewer 허용) | 200 확인됨 | manifest |
| POST `/erp/api/notifications/push/subscribe` | CREATE_OWN_PUSH_SUBSCRIPTION | 200 확인됨 | manifest |
| POST `/erp/api/urgent-call` | SEND_URGENT_CALL | 200 확인됨 | manifest |
| POST `/api/notices/<id>/read`·`/ack` | ACCOUNT_SELF | 200 확인됨 | manifest |
| POST `/api/orders/<id>/transfer-drawing`·`drawing-wizard/*` | DRAWING_ASSIGNED | **403 확인됨** | manifest |
| POST `/api/orders/<id>/construction-schedule` | CONSTRUCTION_SCHEDULE_EDIT(gate can_edit_construction_schedule) | **403 확인됨** | manifest; erp_permissions.py:383-399 |
| POST `/api/brain/chat/ask` | BRAIN_ASK(teams="*") | 정책 200, 라우트 단계 검사 조건부 | manifest; order_mutation_policy.py:150-153 |

## 3. 가설 판정

### H1 — 조건부(기전은 틀렸고 결과는 절반만 맞다)
- 기본 URL 폴백은 `tablet-side-sheet.js:93-105`(`resolveSheetUrl`: `data-foms-sheet-url` 없을 때만 `/api/foms/fragment/order/<id>/edit?open=erp-order`). 그 fragment 는 `fragment.py:70-72` 에서 ERP 주문이면 `can_edit_erp` 아니면 `abort(403)` → 생산팀 403 확인됨.
- 하지만 **컨트롤타워 행은 기본 fragment 로 떨어지지 않는다** — 자체 URL 을 준다. 그런데 그 라우트도 똑같이 403 이다(`dashboard.py:653-654`). 결과만 같다.
- **이력은 가설과 반대** — 자체 시트(권한 검사 없음) → 200.
- 403 때 시트 본문은 "내용을 불러오지 못했습니다 / 다시 시도" 만 보이고 권한 안내가 없다(`static/js/foms/fragment-loader.js:93-105`, `:124` 에서 status 무관 throw).

| 그리드(태블릿 가로) | 행 마크업 | 시트 URL | 생산팀 결과 |
|---|---|---|---|
| 컨트롤타워 PC 그리드 `#erp-grid` | `templates/orders/partials/dashboard_grid.html:72` | `/erp/dashboard/tablet-sheet/<id>` | **403**(dashboard.py:653) |
| 컨트롤타워 태블릿 작업큐 | `tablet_workqueue_grid.html:46-47` | 같음 | **403** |
| 이력 | `history_dashboard_body.html:229-233` | `/erp/history/tablet-sheet/<id>` | 200 |
| AS 대시보드 PC 표(`d-md-block`, 태블릿 가로에 보임) | `cs/partials/as_dashboard_body.html:244, :297`(URL 없음) + 선택자 `tablet-side-sheet.js:81` | **기본 edit fragment** | **403**(fragment.py:72) |
| 생산 칸반 카드 | `production/partials/tablet_kanban_body.html:172` | `/erp/production/tablet-sheet/<id>` | 200 |
| 생산 레거시 `#erp-grid` | `production/partials/filters_grid.html:20, :40`(URL 없음) | 기본 fragment 지만 태블릿 가로에서 CSS 로 숨김(`foms-tablet-production-kanban.css:64-69`) | 도달 불가 |
| 시공 레거시 `#erp-grid` | `construction/partials/filters_grid.html:40`(URL 없음) | 기본 fragment → 403 — 태블릿에서 보이는지는 미확인(5절) | 조건부 |
| 시공 작업모드 카드 | `tablet_workmode_body.html:26-27`(`button.foms-cwork-card`) | 선택자(`tablet-side-sheet.js:74-87`) 밖 → 시트 안 열림 | 해당 없음 |
| 완료 · 출고 · 도면 갤러리 | `tablet_completion_grid_body.html:114`, `shipment/partials/dashboard_main.html:497`·`tablet_ship_grid.html:104`, `drawing/partials/tablet_gallery_body.html:122` | 각자 전용 시트 | 200 |

### H3 — 뒤집힘
- `templates/production/partials/tablet_sheet.html:176-182`: `<button … data-tablet-sheet-action="production-hold" …>` 에 `disabled` 속성 없음. 라벨은 상태별 '보류'/'보류 해제'. 파일 머리 주석 `:6` 의 "보류 disabled" 는 옛 주석(코드와 불일치).
- 배선: `static/js/foms/tablet-domain-sheets.js:759` → 핸들러 `:204-245`, `fetch("/api/orders/<id>/production/hold")` `:241`. CSS `foms-tablet-production-kanban.css:1236` 은 `[disabled]` 가 있을 때만 적용.
- API 는 생산팀 200(표 2). 즉 시트에서 보류를 쓸 수 있다.

### H11 — 확인됨(취소 품목을 뺀다)
- `foms/web/production/dashboard.py:427` `items = active_items(sd)` → `:447-448` 에서 `_prod_sheet_total_units(items)`·`_prod_sheet_spec_rows_view(items)` 로 전달.
- `active_items` → `drop_cancelled` → `is_item_cancelled`(`items[].cancel` dict 여부) — `foms/services/orders/drawing_confirm_partial.py:74-96`.
- `_prod_item_total_w_mm`(`:331-345`)·`_prod_sheet_total_units`(`:363-368`) 자체는 거르지 않고 호출자가 거른 목록을 받는다. 칸반 카드 자수도 `active_items`(`:199`), 취소 수 배지 `:201-202` → `tablet_kanban_body.html:284-285`. 공용 표시 모듈도 `drop_cancelled`(`foms/services/production_dashboard_display.py:44`).

## 4. 놓치기 쉬운 것

1. **컨트롤타워 시트 403** — 생산팀이 태블릿에서 컨트롤타워·작업큐 행을 탭하면 시트가 "불러오지 못했습니다"만 보인다(dashboard.py:653-654). 권한 문구 없음(fragment-loader.js:93-105).
2. **AS 대시보드 행 탭 403** — 유일하게 기본 edit fragment 로 떨어지는 표면(as_dashboard_body.html:297, fragment.py:72).
3. **[ERP 편집]·[첨부 추가] 링크 → 302 `/` + flash** — 컨트롤타워 시트 `tablet_dashboard_sheet.html:65, :85`, 이력 시트 `history_tablet_sheet.html:77` 가 `/edit/<id>?open=erp-order` 로 가고, edit.py:255-260 이 생산팀을 `/`(레거시 주문 목록)로 튕긴다. 태블릿에서 레거시 PC 화면이 뜬다.
4. **출고 배정 API 403** — `/api/erp/shipment/update/<id>` 는 `@erp_edit_required`(CS/SALES) — 매니페스트 SHIPMENT_EDIT 보다 좁다(settings.py:191). 출고팀 STAFF 도 막힌다(부수 발견, 확인됨).
5. **물류 상태 API 403** — `/api/orders/<id>/logistics` 는 SHIPMENT_EDIT(orders.py:1757).
6. **도면 시트 [시트 전달]·마법사 쓰기 403** — DRAWING_ASSIGNED. 마법사 페이지 자체는 200(wizard.py:52-54) → 열 수는 있는데 저장은 전부 403.
7. **정산·협력사 명세서 직접 URL 403**, 내비에서는 숨김.
8. **회사 지식 `/brain` → 404 또는 `/brain/ask` 302**(brain.py:124-128). PC 드롭다운엔 링크가 보인다(layout_nav.html:88).
9. **모바일 하단 탭에 '생산' 없음** — 기본 분기 `erp_mobile_shell.html:55`. 생산팀 폰은 서랍을 열어야 생산 대시보드에 간다.
10. **로그인 첫 화면**: `routes.py:510` → `resolve_post_login_redirect` → `authenticated_home_url`(`foms/services/post_auth_navigation.py:31-44`): `wizard_new_order_enabled(uid)`(모바일 v2 코호트, feature_flags.py:512-530) **그리고** `prefers_mobile_wizard_client`(`?wizard=1` · `Sec-CH-UA-Mobile: ?1` · … feature_flags.py:533-548) 일 때만 `/erp/dashboard`, 아니면 `/`(레거시 목록; listing.py:159-160 도 같은 판정으로 재리다이렉트). 팀별 분기는 없다(CONSTRUCTION 만 switch_user 때 `routes.py:585-586`). 태블릿은 `Sec-CH-UA-Mobile` 이 `?0` 이거나 없는 경우가 많아 **`/` 레거시 목록에 착지할 가능성이 높다(추정)**.
11. 태블릿 표면(레일·칸반·시트) 전부가 `erp_mobile_v2_enabled`(코호트 `FOMS_V3_SHELL_COHORT`) ∧ `coarse_pointer_surfaces` 쿠키에 걸려 있다(production dashboard_body.html:154, feature_flags.py:140). 생산팀 계정이 코호트에 들어 있는지는 환경값이라 코드로 못 본다.

## 5. 확인 못 한 것

- `/erp/shipment-settings`(GET)·`/trash`·`/change-logs` 의 데코레이터 — 표 범위 밖이라 열지 않음.
- 시공 레거시 `#erp-grid` 가 태블릿 가로에서 CSS 로 숨겨지는지(`foms-tablet-construction.css` 미열람) — 보이면 행 탭이 기본 fragment 403.
- `prefers_mobile_wizard_client` 548행 이후(UA 정규식 유무) — 태블릿 착지 화면 판정이 여기에 달려 있다.
- `/brain/ask` 개방 단계는 DB 설정값(`chat_access.py`)이라 정적 판정 불가.
- 도면 태블릿 시트의 "원 주문 열기" `detail_url` 목적지(tablet_sheet_body.html:21) — 변수 조립부 미열람.
- 실제 HTTP 응답은 쏘지 않았다(읽기 전용·DB 없음). 모든 200/403 은 데코레이터·정책 코드 판독이다.
