# ERP 본공정 파이프라인 지도 (정찰 원문, 2026-09-17, base origin/deploy 0eb9e10a3)

정찰 에이전트가 읽기 전용으로 만든 지도. 페르소나 검수·CEO 설계의 뼈대다. 경로:행은 `C:\tmp\foms-s-confirm-flow` 기준.

## 정본 파일

| 역할 | 경로 |
|---|---|
| 파이프라인 코드·순위·override | `foms/services/orders/stage_override.py:24-51` |
| 전이 엔진 + 명령 레지스트리 | `foms/services/orders/order_transition_service.py:183-211` (기본 5 명령; 하위 모듈이 `setdefault` 로 추가 등록) |
| quest→stage 오케스트레이션 | `foms/services/orders/quest_transition_service.py:71-77` (`_STAGE_ADVANCE`, `_COMMAND_REQUIRED_STAGES`) |
| quest 템플릿·승인 | `foms/services/orders/erp_policy_quests.py:111-215`, `data/erp_quest_templates.json` |
| 승인 권한 술어 | `foms/services/orders/quest_approve_authz.py:83-138` |
| 버튼 문구 SSOT | `foms/services/orders/quest_approve_cta.py:24-37` |
| stage 라벨·배지 | `foms/services/orders/erp_policy_constants.py:14-57`, `foms/services/erp_mobile_order_display.py:497-533` |

등록된 본공정 명령(전부 `AXIS_MAIN`): `REQUEST_MEASUREMENT`(`order_transition_service.py:186`), `COMPLETE_MEASUREMENT`(`:191`),
`PRODUCTION_START/COMPLETE/CANCEL/UNCOMPLETE`(`foms/api/production/orders.py:253-275`), `CONSTRUCTION_COMPLETE`(`foms/api/construction/orders.py:69-80`),
`CS_COMPLETE`(`foms/api/cs/complete.py:48-59`), 범용 `SET_MAIN_STAGE`(`foms/api/orders/status.py:76-87`). **DRAWING→CONFIRM 명령은 없다.**

## 전이 표 (7 화살표)

| # | 전이 | PC 액션 | 모바일/태블릿 액션 | 엔드포인트 → 서비스 | 게이트 | 다음 stage quest 생성 | 승인 모드 + 필수 팀 |
|---|---|---|---|---|---|---|---|
| 1 | RECEIVED→MEASURE | 대시보드 quest 패널 팀별 "승인" `static/js/orders/dashboard/erp-dashboard-quest.js:115`(fetch `:14`); `erp-dashboard-detail-dom.js:897`; `templates/orders/object.html:276` | 큐 카드 "접수 확인" `erp_mobile_queue_card_v2.html:298-307`; 상세 `order_detail_mobile_v2.html:284/:305`; `erp-quest-approve.js:150` | `POST /api/orders/<id>/quest/approve` → `foms/api/quest.py:265` → `advance_stage_on_quest_completion` `quest_transition_service.py:167` → `transition_order(REQUEST_MEASUREMENT)` | 팀 승인 전원(`_stage_quest_complete:115`, `check_quest_approvals_complete:42`); authz `quest_approve_authz.py:83`(ADMIN bypass `:118`, MANAGER+사유 `:110-115`); 폼 저장의 `schedule.measurement.date` 로도 자동 전이(`erp_orders_structured.py:388-430`) | **예** `make_next_quest=True`(`:72`), `_append_next_stage_quest:142` | team, `["CS"]`(`erp_quest_templates.json:15-17`) |
| 2 | MEASURE→DRAWING | "도면 전달" 매크로 `status_select_options.html:105-113`(실측 보드 5곳), JS `drawing-transfer-btn.js:33`; 범용 승인 패널 | 큐 카드 "실측 완료"; 상세 sticky `order_detail_mobile_v2.html:387-392`; 태블릿 `tablet_split_body.html:160` → `tablet-measure-form.js:1643` | 같은 엔드포인트 → `transition_order(COMPLETE_MEASUREMENT)`(`:73`) | 담당자 1인(`:133`); 실측 보드 CTA 는 `drawing_transfer_cta.py:96-143`(AS 열림 `:112`·팀 모드 `:137` 억제) | 아니오(`:73`; DRAWING quest 는 의도적으로 비활성 `quest.py:83-90,144-145`) | assignee, `["CS","SALES"]`; 라홈은 owner_team→CS 만 |
| 3 | DRAWING→CONFIRM | "수령 확정" `workbench_detail_body.html:1495`(fetch `:2750`); `erp-dashboard-detail-dom.js:369`; `erp-dashboard-drawing.js:378` | 모바일 `workbench_mobile_handoff.html:239`; 태블릿 `tablet-drawing-review.js:240→:382` | `POST /api/orders/<id>/confirm-drawing-receipt` → `erp_orders_draftsman.py:314/:317`; **stage 직접 쓰기 `:383-392`**(transition_order·레지스트리 없음) | quest 미사용(DRAWING command-required); `drawing_status=='TRANSFERRED'` `:339-344`(ADMIN bypass 없음); `can_modify_domain(SALES_DOMAIN)`+담당/관리자 `:346-380` | **아니오** — CONFIRM quest 는 GET/approve(`quest.py:112,:310`)·표시 합성(`erp_quest_display.py:88`)으로만 생긴다 | assignee, `["CS","SALES"]` |
| 4 | CONFIRM→PRODUCTION | "제작 시작" `filters_grid.html:86-89` → `scripts.html:271-274`; 칸반 `tablet_kanban_body.html:26`; 시트 `tablet_sheet.html:179` | 모바일 큐 `mobile_queue.html:45`(미승인이면 '고객 컨펌 전' `:47`) | `POST /api/orders/<id>/production/start` → `production/orders.py:652/:655` → `transition_order(PRODUCTION_START)` `:690` | 404 → 팀 게이트 `:85` → stage∈{고객컨펌,CONFIRM} → 보류 → `_stage_quest_block(sd,"CONFIRM","고객컨펌")`(`:377`) | 아니오 | PRODUCTION: team, `["PRODUCTION"]` |
| 5 | PRODUCTION→CONSTRUCTION | "제작 완료" `scripts.html:684,:276-279`; 칸반 `:27`; 시트 `tablet-domain-sheets.js:127`; `tablet-production-kanban.js:56` | 모바일 큐 `mobile_queue.html:49` | `POST .../production/complete` → `:709/:712` → `transition_order(PRODUCTION_COMPLETE)` `:739` | 같은 5 게이트 `:727-736` + `_stage_quest_block(sd,"PRODUCTION","생산")` | 아니오 | CONSTRUCTION: team, `["CONSTRUCTION"]` |
| 6 | CONSTRUCTION→CS | "시공 완료" `construction/partials/filters_grid.html:79` → `static/js/construction/dashboard.js:542`; 모달 `modals.html:25-37` | 모바일 큐 `mobile_queue.html:93`; 게이트 시트 `complete_gate_sheet.html:89` → `foms-complete-gate.js:269`; 태블릿 `tablet_workmode_body.html:132` | `POST .../construction/complete` → `construction/orders.py:325/:328` → `transition_order(CONSTRUCTION_COMPLETE)` `:369` | `erp_construction_edit_required` → 증빙 게이트(`FOMS_CONSTRUCTION_GATE_ENABLED` 기본 off `:346-355`) → stage 409 `:364`. **quest 게이트 없음** | 아니오 | CS: team, `["CS"]` |
| 7 | CS→COMPLETED | **없음**(템플릿·JS 에 `cs/complete` 참조 0) | **없음** | `POST .../cs/complete` → `cs/complete.py:159/:161` → `transition_order(CS_COMPLETE)` `:224` | `erp_edit_required` → stage==CS → `_cs_gate_block:103`(quest `_cs_quest_block:80`·보류·AS) | 종결 | COMPLETED 템플릿 `["CS"]`, terminal |

주문 유형별 override 는 하나뿐: 라홈 발주사 → 실측/고객컨펌 `owner_team="CS"`(`erp_policy_quests.py:106-108,174-179`) — 표시·배정 축. 필수 승인 팀은 유형 무관하게 같고
`resolve_required_approval_teams`(`:111-154`)가 좁게 저장된 옛 값을 정책으로 넓힌다. 하우드/지방 차이는 초기 stage(`initial_workflow_stage.py:24-43`)와 폼 주도 RECEIVED→MEASURE(`erp_orders_structured.py:388-433`).

## 생산 보드 명령 (`foms/api/production/orders.py`)

| 라우트 | 행 | 효과 |
|---|---|---|
| `production/start` | `:652` | PRODUCTION_START: CONFIRM→PRODUCTION; IN_PROGRESS run 발급(`_apply_start_side_effects:506`) |
| `production/complete` | `:709` | PRODUCTION_COMPLETE: PRODUCTION→CONSTRUCTION; run 종결, rework 해제(`:522`) |
| `production/rework` | `:773` | CONSTRUCTION→PRODUCTION(재제작 회차) |
| `production/cancel` | `:895` | PRODUCTION_CANCEL: PRODUCTION→CONFIRM; 보류 게이트 없음; rework/hold 해제 |
| `production/uncomplete` | `:963` | CONSTRUCTION→PRODUCTION; rework 복원 |
| `production/hold` | `:1346` | stage 무변경(`workflow.hold`↔`production.hold` 미러 `:1305`) |
| steps `:1089/:1127`, defect `:1213`, change-ack `:1022`, logistics `:1420` | | stage 무변경(`test_state_prod_actions.py:232`) |

## 시공·CS

| 라우트 | 행 | 효과 |
|---|---|---|
| `construction/start` | `construction/orders.py:180` | stage 무변경; attempt 발급(IN_PROGRESS, is_current); 열린 attempt 있으면 409 |
| `construction/complete` | `:325` | CONSTRUCTION→CS; attempt READY |
| `construction/evidence` | `:387` | 증빙 업로드 |
| `construction/fail` | `:497` | attempt REWORKED + `_REWORK_STAGE_MAP[reason]` 로 **stage 후퇴**(직접 쓰기, transition_order 아님) |
| `cs/complete` | `cs/complete.py:159` | CS→COMPLETED(quest·보류·AS 게이트) |

## 파이프라인 종단 테스트

한 주문을 끝까지 걷는 테스트는 없다. 화살표별: `test_state_quest.py:136,184,212,241,271,298,325`; `test_state_prod.py:100`; `test_production_transition_guard_api.py:112,160`;
`test_state_const_cs.py:141,160,227-282`; `tests/postgres/test_state_const_cs.py:76,144,173`; `test_state_prod_actions.py:232`.

## 의도 문서

`docs/specs/2026-08-19-measure-quest-stage-transition_SPEC.md`, `docs/specs/2026-09-13-measure-approval-teams_SPEC.md`, `docs/specs/2026-03-04-erp-add-orderer-workflow-default.md`,
`docs/plans/2026-07-15-workflow-stage-override_SPEC.md`, `docs/plans/2026-09-09-confirm-quest-and-drawing-attachment-plan.md`, `docs/plans/2026-06-11-mobile-quest-deeplink-stage-sync-plan.md`,
`docs/plans/2026-03-03-remove-happycall-stage-plan.md`, `docs/plans/2026-07-22-foms-full-system-bug-audit-report.md`, `docs/plans/2026-03-02-construction-completion-*.md`,
`docs/harness/foms_state_writer_inventory.json`, `docs/harness/foms_state_writer_allowlist.json`.

## 정찰이 적은 불일치 16건

**UI 액션 없는 단계**
1. CS→COMPLETED 는 UI 호출자 0(`cs/complete.py:159`).
2. COMPLETED 로 가는 유일한 길은 `field_update status=COMPLETED`(`field_update.py:532-561` → SET_MAIN_STAGE, 실측/지방/자가 보드 `complete_order_control`) — CS quest·보류·AS 게이트를 **우회**한다.
3. CONFIRM 완료 버튼이 모바일에 없다(`quest_approve_cta.py:24-31` 라벨 없음 → 큐 카드 `:250`·상세 `:272` 숨김, 카드는 상세 링크 `:322-328`, 상세는 편집만). PC 는 `erp-dashboard-quest.js:115` 가 라벨 무시하고 승인 버튼.

**quest 생명주기**
4. 다음 단계 quest 를 만드는 전이는 RECEIVED→MEASURE 뿐(`_STAGE_ADVANCE:72`). DRAWING/CONFIRM/PRODUCTION/CONSTRUCTION/CS quest 는 GET(`quest.py:108-112`)·approve(`:308-316`)·표시 합성(`erp_quest_display.py:88`)으로만 생긴다.
5. 그래서 `_stage_quest_block`(`production/orders.py:377`)·`_cs_quest_block`(`cs/complete.py:80`)은 quest 가 한 번도 만들어지지 않은 주문에서 no-op — 게이트가 "UI 가 먼저 quest 를 건드렸는가" 에 달려 있다.
6. CONSTRUCTION→CS 는 quest 게이트가 없다(이웃 두 전이는 있다). 유일한 게이트는 env 로 기본 off.

**전이 엔진**
7. DRAWING→CONFIRM 만 `transition_order` 를 안 탄다(`erp_orders_draftsman.py:383-392` 직접 쓰기 — mutation_version·receipt·STAGE_NOTIFICATION·expected_from 검사 없음). `construction/fail` 의 후퇴(`:553-560`)도 같다.
8. `complete_confirm_quest`(`quest_transition_service.py:253`)는 "CUSTOMER_CONFIRM command adapter" 라 적혀 있지만 레지스트리에 그 명령이 없고 호출자도 테스트뿐(`quest.py:193-197` 이 기록).
9. "고객 컨펌" 엔드포인트가 둘: `cs/confirm.py:24` 는 `blueprint.customer_confirmed` 만 쓰고 quest 를 안 닫는다; `quest.py:426-433` 은 quest 종결 + 같은 blueprint 키. 생산 게이트는 quest 를 읽으므로 `confirm/customer` 만으로는 제작 시작이 안 풀린다.
10. `quest.py:198` `{DRAWING}` vs `quest_transition_service.py:77` `{DRAWING, CONFIRM}` — 두 목록, 두 답. `:201 _NO_AUTO_ADVANCE_STAGES` 로만 봉합.

**PC vs 모바일**
11. MEASURE→DRAWING 은 PC 실측 보드에 서버 게이트 CTA(`drawing_transfer_cta.py`, AS 열림·팀 모드 억제)가 있지만 모바일/태블릿은 범용 승인 버튼(`can_assignee_approve` 만) — AS 열림 억제(`:112`) 미적용.
12. `production/rework`·`cancel`·`uncomplete` 는 PC/태블릿 전용(`tablet_kanban_body.html:28`, `tablet-domain-sheets.js:132,154`); 모바일 큐는 start/complete 만(`mobile_queue.html:44-51`).
13. `construction/fail`(시공 불가, stage 후퇴)은 모바일 큐에 버튼이 없다.

**라벨**
14. `stage_badge_label` 은 CS→"AS"(`erp_mobile_order_display.py:531`), `STAGE_LABELS` 는 CS→"CS"(`erp_policy_constants.py:21`).
15. `templates/orders/object.html:155` 의 STAGE_LABELS JS 하드코딩이 CONSTRUCTION 에서 끝난다 — CS/COMPLETED 는 코드 원문 노출.
16. 생산 보드 어휘(제작대기/제작중/제작완료)는 CONFIRM/PRODUCTION/CONSTRUCTION 위의 세 번째 이름 축(`tablet_kanban_body.html:26-28`).
