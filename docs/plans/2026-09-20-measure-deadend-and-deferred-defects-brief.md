# 브리프(초안 — CEO 가 계약을 확정한다): 실측 완료 뒤 도면으로 안 넘어가는 막다른 길 + 컨펌→생산 배치가 미룬 결함 (2026-09-20)

작업 트리 `C:\tmp\foms-s-measure-deadend`(브랜치 `session/measure-deadend`, base origin/deploy `a89243fee`).
`C:\DEV\FOMS` 는 321 커밋 뒤라 **읽지도 편집하지도 않는다**. 워커는 **git 명령 금지**(커밋·push 는 총괄).
직전 원장 `docs/plans/2026-09-17-confirm-to-production-workflow-ledger.md`(§5b·§6), 검수 `2026-09-20-pipeline-persona-audit.md`(F1~F9),
지도 `2026-09-17-pipeline-map-scout.md`(불일치 16건).

## 0. 원인 확정(총괄이 스테이징 HTTP 로 읽음, 2026-09-20)

스테이징 주문 #4382(이영아) `OrderEvent` 원문:
- 09-14 14:39:39 `QUEST_APPROVAL_CHANGED`(QUEST_ASSIGNEE_APPROVED, claude_master) + `MEASUREMENT_COMPLETED`(command COMPLETE_MEASUREMENT, MEASURE→DRAWING)
- 09-14 14:39:50 `STAGE_OVERRIDE`(mode regress, DRAWING→MEASURE, reason "스테이징 도면 전달 버튼 검증 후 원상 복구(claude_master)")
- 지금: `workflow.stage=MEASURE`, `workflow.stage_override={stage:MEASURE, at:09-14T05:39:50}`, quests=[{stage MEASURE, status **COMPLETED**, assignee_approval approved_by 58}]

→ 후보 ① **관리자 강제 단계 변경(regress)이 quest 를 안 되돌린다**(`stage_override.py:217-224` 문서화된 의도: "퀘스트 부수효과 호출 안 함").
직전 배치가 COMPLETED quest 를 `is_done` 배지로 그리게 하면서(`erp_quest_display.py:82-92`) 승인 버튼이 사라져 막다른 길이 됐다(그 전엔 "-" 였고 PC 는 `can_edit_erp` 로 [승인] 을 그렸다).

**같은 모양 건수(읽기 전용, 사용자 1회 승인)**: 스테이징 4건(#2921·#3338·#3610·#4382, 전부 MEASURE) · **운영 5건**(전부 MEASURE, stage_updated 03-31~08-16).
`PRODUCTION 인데 current run 없음` = 스테이징 0 · 운영 0. `CONFIRM 인데 CONFIRM quest 없음` = 운영 **1건**(T3 이 409 로 바꾸면 이 주문은 화면 승인 버튼으로 quest 가 생긴 뒤 제작 시작 가능 — 막다른 길 아님을 T3 테스트로 못박는다).

## 1. 사용자 결정 (2026-09-20, AskUserQuestion)

- D1 막다른 길: **둘 다** — ① 완료 배지 옆 재전이 액션(3표면) ② 강제 단계 변경 regress 시 그 단계 quest 를 다시 OPEN.
- D2 F2: **CONFIRM 호환 경로에서 quest 없음 = 409**. 기존 테스트 픽스처에 CONFIRM quest 시드.
- D3 F4: `POST /quest`·`PUT /quest/status` 저장 버그 수정 + **수동 COMPLETED 는 ADMIN/MANAGER 만**.
- D4 운영 DB 읽기 1회 승인(완료) · **모바일 팀 승인 버튼(접수·생산·시공·CS) 추가** · **타임라인 P2(엔진 전이 읽기 + 라벨 6종) 이번에**.
- 범위 밖으로 남기는 것: F8(v3 모바일 생산 큐 카드 제작 시작/완료 — 코호트 측정 먼저), 지도 #1·#2·#6·#7(construction/fail)·#9·#11·#13·#14·#15. 원장에 "다음 배치" 로 적는다.

## 2. 앵커(이 트리 기준, 열어서 확인)

### 표시 SSOT
- `foms/services/erp_quest_display.py`(484줄): `resolve_current_quest` L48-110(COMPLETED fallback → `{**done[0], "is_done": True}` L82-92; DRAWING/CONSTRUCTION 은 None L65-66; 템플릿 합성 경로 L94-110 은 `is_done` 없음 — **합성 quest 표식이 없다**), `_compute_can_assignee_approve` L316-365(`approval_mode != "assignee"` → False L331-333 = F5 의 뿌리; 팀 술어 L349-355; SALES_DOMAIN True L361), `build_current_quest_payload` L369-424(반환 키 L404-421).
- `foms/services/orders/quest_approve_cta.py`(107줄): `_QUEST_APPROVE_LABELS` L25-33, `_QUEST_APPROVE_CONFIRM_HEADS` L36-40, `build_approve_cta` L62-107(`done_label` 항상, `advances_stage`, `next_stage_label`).
- `foms/services/orders/quest_approve_authz.py`(138줄): `authorize_quest_approve` L83-138 — override L110-116, ADMIN bypass L118-120, CONSTRUCTION 배정 L122-132, 팀 술어 L134-138(`team_has_capability(actor_team, required_teams)`).
- `foms/services/orders/quest_transition_service.py`(265줄): `_STAGE_ADVANCE` L75-79(RECEIVED→MEASURE·MEASURE→DRAWING·CONFIRM→PRODUCTION), `stage_advance_target` L85-96, `_find_stage_quest` L107-123, `_stage_quest_complete` L126-144(quest 없음 = True), `advance_stage_on_quest_completion` L172-260.
- 뷰모델 배선: PC 그리드 `foms/services/orders/dashboard_dto.py:59-66`, 모바일 카드·상세 `foms/services/erp_mobile_order_display.py:834-841` — 둘 다 `build_current_quest_payload`.

### 3표면
- PC `templates/orders/partials/dashboard_grid.html`(508줄): 퀘스트 셀 L103-200. `is_done` 배지 L106-107·L137-139; 담당자 버튼 게이트 **L163** `can_edit_erp or can_assignee_approve`; 팀 버튼 L176-196 게이트 **L182 `can_edit_erp` 만**(F3).
- 모바일 카드 `templates/partials/shared/erp_mobile_queue_card_v2.html`(349줄): `quest_actionable` L250-254(`approve_label ∧ ¬all_approved ∧ ¬is_done ∧ can_assignee_approve`), `quest_inline_approve` L257, 버튼 L297-306, 완료 배지 L321-322.
- 모바일 상세 `templates/orders/partials/order_detail_mobile_v2.html`(411줄): 섹션 L261-322. `can_approve_quest = can_assignee_approve ∧ approve_label` L275-276 → 팀 분기 L300-317 은 **도달 불능**(F5).
- JS: `static/js/orders/dashboard/erp-dashboard-quest.js`(143줄) `approveQuestAssignee` L67-105(POST `{}`), `approveQuestTeam` L27-65; 모바일 `static/js/foms/erp-quest-approve.js`(186줄) SELECTOR L22, replaceState→reload L8-12.
- CSS: `.erp-quest-done` 은 `static/css/foundation/erp-pro/04-*.css`(grep 해서 확인). 인라인 스타일 금지.
- 자산 핀 `20260920a` → **`20260920b`** 로 올릴 파일: `templates/orders/dashboard.html:4`, `templates/orders/partials/dashboard_main.html:4`, `templates/partials/shared/layout_head.html:176`, `templates/partials/shared/layout_scripts.html:1792`, `static/css/foundation/erp-pro.css:9`, `static/js/orders/erp-dashboard-entry.js:12-13`, 테스트 `tests/domains/test_drawing_collab_frontend_contract.py:42,45,48`, `tests/domains/test_shell_fragment_css_fouc_audit.py:150,162`. **JS·CSS 를 바꾸면 핀을 안 올리면 SW 캐시로 옛 파일이 산다.** 핀 줄 전부 한 워커(W2) 소유.

### 승인 라우트·수동 상태
- `foms/api/quest.py`(594줄): POST `/quest` L126-180(**L170 `order.structured_data = sd` flag_modified 없음**), `_already_transitioned_into` L243-261, POST `/quest/approve` L278-523(COMMAND_REQUIRED L308-317, `_find_stage_quest` L322, ALREADY_TRANSITIONED L330-338 은 `not team` 일 때만, authz L349-354, assignee 분기 L363-403 — **COMPLETED quest 라도 assignee_approval 을 다시 덮어쓴다**, 팀 분기 L405-447, 종결 L451-455, `flag_modified` L465-466, `advance_stage_on_quest_completion` L478-497), PUT `/quest/status` L531-590(**L576 flag_modified 없음**, stage 정확일치만 L556-560, STAFF 허용).
- writer 인벤토리 `docs/harness/foms_order_mutation_writer_inventory.json` 는 `quest.py:466` 등 **lineno 를 고정**한다 — quest.py 줄이 밀리면 `python tools/harness/order_mutation_writer_scan.py` 로 재생성(명령·옵션은 파일 docstring). `tests/domains/test_rev_99.py` 가 검사.

### 강제 단계 변경
- `foms/services/orders/stage_override.py`(309줄): `apply_stage_override` L209-292 — `mode = classify_stage_move(from,to)`("regress"/"advance"), sd 셸 복사 L246-251, workflow 갱신 L252-262, `flag_modified` L265, `STAGE_OVERRIDE` 이벤트 L281-289. **quests 언급 0.**

### 생산 게이트(F2)
- `foms/api/production/orders.py`(1576줄): `_stage_quest_block` L375-398(quest 없음 → None L382-385), `api_production_start` CONFIRM 호환 분기 **L730-736**, run-only L722-729.
- `production/start` 를 부르는 테스트와 quest 시드 여부: `tests/domains/test_state_prod.py`(11곳, quests 0), `test_production_transition_guard_api.py`(10곳, quests 3곳뿐), `test_audit_action_coverage.py:179`(0), `test_auth_enforcement.py:235,247`(0), `test_confirm_to_production_flow.py:189,276`(시드 있음), `test_confirm_to_production_predicate.py:191,206`(있음), `test_tablet_domain_sheets_contract.py:74`·`test_tablet_t2_contract.py:328`(JS 문자열 계약 — 무관).
- 생산 보드 "고객 컨펌 전" 판정: `foms/services/production_dashboard_display.py:168-194`(`_production_quest_sales_state`).

### 타임라인(P2)
- `foms/services/order_timeline_v3.py`(202줄): `_stage_reach_events` L129-147 — `event_type != "STAGE_CHANGED"` 건너뜀 L139-140, `payload["to"]`, 최초 도달만.
- `foms/services/order_event_display.py`(578줄): `translate_event_type_to_korean` L128-201 — 없는 키: `STAGE_OVERRIDE`(L285 stage_override 가 내는 실제 키; L138 `STAGE_MANUAL_OVERRIDE` 는 죽은 키), `PRODUCTION_REWORK_STARTED`, `PRODUCTION_COMPLETE_REVERTED`, `PRODUCTION_HOLD_TOGGLED`, `ORDER_HELD`, `CONSTRUCTION_EVIDENCE_ADDED`. 각 emit 위치는 `grep -rn "event_type=\"<키>\"\|event_type='<키>'" foms/` 로 확인해 payload 키(from/to)를 본다.
- 엔진 이벤트 이름(`order_transition_service.py:183-221` + 생산·시공·CS 등록): `MEASUREMENT_REQUESTED`, `MEASUREMENT_COMPLETED`, `CUSTOMER_CONFIRMED`, `PRODUCTION_STARTED`, `PRODUCTION_COMPLETED`, `PRODUCTION_CANCELLED`, `CONSTRUCTION_COMPLETED`, `CS_COMPLETED`, `ORDER_HELD`, `ORDER_HOLD_RELEASED`, `LOGISTICS_STATUS_CHANGED`. 전이 이벤트 payload 는 `{axis:"MAIN", command, from, to, ...}`(§0 원문 참조).

### 도면 수령 확정 권한(F9)
- `foms/api/drawing/erp_orders_draftsman.py`(457줄): L345-375 — `can_modify_domain(SALES_DOMAIN)` L345-347, `get_assignee_ids(order,'SALES_DOMAIN')` 비면 이름 대조 L350-370, 403 L372-376.
- 주문 생성 시 owner 기록: `foms/services/orders/order_create.py:118-126`(quest `owner_person` 에 id 문자열), `foms/web/orders/listing.py:82-93`(`sales_owner_id` 폼 필드). `Order` 에 `sales_owner_id` 컬럼 없음 — 어디에 저장되는지(`assignments.sales_assignee_user_ids`? `manager_name`?) 워커가 확정하고 테스트로 못박는다.

### 기존 테스트
- `tests/domains/test_erp_quest_display.py`(436줄, `is_done` L315-384), `test_confirm_to_production_display.py`(214, `erp-quest-done` L142-182), `test_confirm_to_production_flow.py`(ALREADY_TRANSITIONED L166-190, `is_done` L265-267), `test_measure_approval_teams.py`(118, `_can_show_button` L78-90 = 2026-09-13 화면==서버 계약), `test_state_quest.py`(369), `tests/visual/test_p1_mockup_structure.py:563`.

## 3. 계약 초안(이름은 고정, CEO 가 규칙을 확정)

### C1 재전이(막다른 길 해소) — 서버
- 승인 라우트가 현 단계 quest 를 찾았고 그 quest 가 `COMPLETED` 이고 `stage_advance_target(stage)` 가 있으면 **재전이 요청**이다: 승인 기록을 다시 쓰지 않고(assignee_approval·team_approvals 불변, QUEST_APPROVAL_CHANGED 이벤트 없음) 권한 게이트(`authorize_quest_approve`)만 통과시킨 뒤 `advance_stage_on_quest_completion` 을 부른다. 응답 `{'success': True, 'retransitioned': True, 'auto_transitioned': True, 'next_stage': ...}`. 전이 이벤트 reason 은 `"<단계> 재전이(완료 quest, 강제 단계 변경 뒤)"` 처럼 재전이임을 남긴다.
- `_already_transitioned_into` 는 그대로(다음 단계로 **이미 넘어간** 경우만).
- 팀 모드 COMPLETED(RECEIVED) 도 같은 규칙.

### C2 강제 단계 변경 regress → quest 되돌림
- `apply_stage_override` 에서 `mode == "regress"` 이고 `to_code` 단계의 quest(별칭 매칭 `_find_stage_quest`)가 `COMPLETED` 면 그 quest 를 `status="OPEN"`, `assignee_approval={}`, `team_approvals={}`, `completed_at` 제거로 되돌리고 `quest["reopened_by_override"]={"at","from_stage","reason"}` 를 남긴다. `advance` 모드는 손대지 않는다. 되돌린 사실은 STAGE_OVERRIDE payload 에 `"quest_reopened": "<stage>"` 로 싣는다. 나중 단계 quest(예: PRODUCTION→MEASURE 로 되돌릴 때 CONFIRM quest)는 삭제하지 않는다(C1 이 그 단계에 도달했을 때 재전이 액션을 준다).
- 기존 운영 5건·스테이징 4건은 데이터 이관 없이 C1·C3 액션으로 사람이 넘긴다.

### C3 표시 SSOT — `build_current_quest_payload` 반환 키 추가(이름 고정)
- `can_retransition: bool` = `is_done ∧ advances_stage ∧ (현 stage == quest stage) ∧ 서버 권한 술어 통과`. `retransition_label: str` = `"{next_stage_label} 단계로 넘기기"`(예: "도면 단계로 넘기기"), `retransition_confirm: str`(C1 문구, 주문 컨텍스트 포함) — `quest_approve_cta.py` 에서 만든다.
- `approvable_teams: list[str]` = 팀 모드에서 **현재 사용자가 눌러 200 을 받을 팀**(`authorize_quest_approve` 와 같은 술어를 `quest_approve_authz.py` 의 새 순수 함수 `approvable_teams_for(user, order, stage_code, quest, required_teams)` 로 뽑아 화면과 서버가 한 함수를 쓴다; ADMIN 은 전부, CONSTRUCTION 배정 규칙 포함). 아직 승인 안 된 팀만.
- `is_synthesized: bool` = sd 에 없어서 템플릿으로 합성한 quest(L94-110 경로). **합성 quest 에 팀 버튼을 그릴지**는 CEO 결정 — 초안: RECEIVED(전이)·CS(cs/complete 게이트) 는 그린다, PRODUCTION·CONSTRUCTION 은 보드 명령이 실제 액션이라 **안 그린다**(원장 §6 "PRODUCTION quest 를 만들지 않는다" 유지; F3 두 번째 절).

### C4 3표면 동일 규칙
- 완료 배지(`is_done`) 옆에 `can_retransition` 이면 버튼 `[{retransition_label}]`: PC `.erp-btn-retransition`(그리드 셀 + collapse 카드 둘 다), 카드 `.erp-queue-card__quest-retransition`, 상세 `.erp-mobile-quest-retransition`. 클릭 = `POST /api/orders/<id>/quest/approve` `{}`(팀 모드면 `{team}` 불필요 — 서버가 COMPLETED 를 보고 재전이). 확인창 `retransition_confirm`. 기존 승인 JS 핸들러 재사용(SELECTOR 에 추가).
- 팀 버튼: PC L182 게이트를 `team in approvable_teams` 로, 카드·상세는 `approvable_teams` 가 비지 않으면 팀별 버튼(상세 L300-317 분기 도달 가능하게 `can_approve_quest` 를 `(can_assignee_approve ∨ approvable_teams) ∧ approve_label` 로). 카드는 팀 버튼을 **상세 링크**로 보낼지 인라인일지 CEO 결정(초안: RECEIVED 만 인라인 "접수 확인", 나머지 상세 링크).
- 거부당할 버튼 0 · 눌러야 하는데 버튼 없는 상태 0. 대조군 테스트: DRAWING 팀은 MEASURE 완료 quest 에 재전이 버튼 없음; 이미 DRAWING 으로 넘어간 주문(quest COMPLETED, stage DRAWING)은 버튼 없음(`_already_transitioned_into` 축).

### C5 F2 — CONFIRM 호환 경로 quest 필수
- `_stage_quest_block(sd, stage_code, stage_label, *, require_quest=False)`; `api_production_start` CONFIRM 분기만 `require_quest=True` → quest 없으면 409 `{"code":"QUEST_INCOMPLETE","message":"고객 컨펌 승인이 먼저 필요합니다.","missing_teams":[...]}`(code 는 기존 소비자 호환 위해 유지, CEO 가 새 code `CONFIRM_REQUIRED` 로 갈지 결정). `production/complete` 등 다른 호출부는 그대로(False).
- 위 표의 테스트 파일에서 CONFIRM 주문으로 start 를 부르는 곳은 승인 완료된 CONFIRM quest 를 시드한다(공용 헬퍼 `tests/support/quest_seed.py::confirm_quest_completed(**kw)` 신설, 500줄 미만). 거부 테스트 신설: quest 없음 → 409, quest COMPLETED → 200, quest OPEN → 409.

### C6 F4 — 수동 quest 저장·권한
- POST `/quest`·PUT `/quest/status` 에 `copy.deepcopy → 수정 → 재대입 → flag_modified` 규약 적용. PUT 의 stage 매칭은 `_find_stage_quest` 별칭.
- PUT `status == "COMPLETED"` 는 role ∈ {ADMIN, MANAGER} 만(그 외 403 `{"code":"ROLE_REQUIRED"}`) + `reason` 필수(400). 감사 `QUEST_STATUS_CHANGED` payload 에 reason. OPEN/IN_PROGRESS 는 STAFF 도 가능.
- writer 인벤토리 재생성 + `test_rev_99.py` 통과.

### C7 타임라인
- `_stage_reach_events`: `STAGE_CHANGED` 외에 `STAGE_OVERRIDE` 와 `payload.axis == "MAIN"` 이고 `payload.to` 가 stage 코드인 모든 전이 이벤트를 읽는다(엔진 이벤트 목록 §2). 최초 도달 규칙 유지. `production/start` 의 `PRODUCTION_STARTED` 는 이제 run 발급이라 `to` 가 없을 수 있음 — 있을 때만.
- 라벨 6종: `STAGE_OVERRIDE`="단계 강제 변경", `PRODUCTION_REWORK_STARTED`="수정 제작 시작", `PRODUCTION_COMPLETE_REVERTED`="제작 완료 취소", `PRODUCTION_HOLD_TOGGLED`="생산 보류 변경", `ORDER_HELD`="주문 보류", `CONSTRUCTION_EVIDENCE_ADDED`="시공 증빙 등록". 죽은 키 `STAGE_MANUAL_OVERRIDE` 는 남겨도 되나 주석으로 표기.

### C8 F9 — 주문 SALES owner 의 도면 수령 확정
- 주문 생성(`order_create.py`)이 owner 를 어디에 쓰는지 확정한 뒤, 그 축(id)이 `confirm-drawing-receipt` 권한에서 통과하게 한다(이름 대조 fallback 앞에 id 대조). 재현 테스트: `/add` 로 만든 주문의 owner STAFF(SALES) → 200; 다른 SALES STAFF → 403(대조군).

## 4. 워커 소유권(겹치지 않게 — 통합 검증자가 해제)

| 워커 | 편집 허용 파일 | 금지 |
|---|---|---|
| W1 서버(C1·C2·C6) | `foms/api/quest.py`, `foms/services/orders/quest_transition_service.py`, `foms/services/orders/stage_override.py`, `docs/harness/foms_order_mutation_writer_inventory.json`(재생성), 신규 `tests/domains/test_quest_retransition_deadend.py`, `tests/domains/test_stage_override_reopens_quest.py`, `tests/domains/test_quest_manual_status_authz.py`, 기존 `tests/domains/test_state_quest.py`·`test_confirm_to_production_flow.py`(필요 시 단언만) | 표시·템플릿·JS |
| W2 표시(C3·C4) | `foms/services/erp_quest_display.py`, `foms/services/orders/quest_approve_cta.py`, `foms/services/orders/quest_approve_authz.py`(새 순수 함수 추가만; `authorize_quest_approve` 는 그 함수를 재사용하도록 리팩터 허용), 템플릿 3개(`dashboard_grid.html`·`erp_mobile_queue_card_v2.html`·`order_detail_mobile_v2.html`), JS 2개(`erp-dashboard-quest.js`·`erp-quest-approve.js`), CSS `erp-pro/04-*.css`, **핀 줄 전부(§2 목록 + 테스트 2파일)**, 테스트 `test_erp_quest_display.py`·`test_confirm_to_production_display.py`·`test_measure_approval_teams.py`·`tests/visual/test_p1_mockup_structure.py`, 신규 `tests/domains/test_quest_surfaces_retransition_and_team_buttons.py` | `quest.py` 라우트 본문 |
| W3 생산 게이트(C5) | `foms/api/production/orders.py`(`_stage_quest_block`·start 분기만), 신규 `tests/support/quest_seed.py`, `tests/domains/test_state_prod.py`, `test_production_transition_guard_api.py`, `test_audit_action_coverage.py`, `test_auth_enforcement.py`, `test_confirm_to_production_predicate.py`, 신규 `tests/domains/test_production_start_requires_confirm_quest.py` | quest.py |
| W4 타임라인·F9(C7·C8) | `foms/services/order_timeline_v3.py`, `foms/services/order_event_display.py`, `foms/api/drawing/erp_orders_draftsman.py`, 관련 테스트(`grep -rln "order_timeline_v3\|translate_event_type_to_korean\|confirm-drawing-receipt" tests/`), 신규 `tests/domains/test_timeline_engine_events.py`, `tests/domains/test_drawing_receipt_sales_owner.py` | 그 외 |

공유 한 줄: `quest_approve_authz.py` 는 W2 만. `erp_mobile_order_display.py`·`dashboard_dto.py` 는 손대지 않는다(payload 키 추가는 `build_current_quest_payload` 안에서 끝난다).

## 5. 검증 명령(워커 공통)

```
cd /c/tmp/foms-s-measure-deadend && pwd
python -c "import app; print('APP_OK')"
python -m pytest <자기 테스트 파일들> -q -p no:cacheprovider
node --check static/js/orders/dashboard/erp-dashboard-quest.js && node --check static/js/foms/erp-quest-approve.js   # W2
python tools/harness/order_mutation_writer_scan.py --check   # W1(옵션명은 docstring 확인)
```
통합 검증자: `python -m pytest tests/domains tests/contracts tests/harness -q -p no:cacheprovider -x` 전량 + `tests/visual`, node --check 2파일, `git diff --stat`.

## 6. 함정

- CRLF 보존(파일 기존 개행 그대로). 인라인 style 금지(`erp-pro.css` ratchet). 새 .py 는 500줄·새 .js 는 300줄 미만(`tests/harness/test_file_size_ratchet.py`). 템플릿은 래칫 밖.
- structured_data 수정 규약: `copy.deepcopy` → 수정 → 재대입 → `flag_modified(order,'structured_data')`. `stage_override.py` 는 셸 복사 후 리스트 참조 유지가 의도 — quests 리스트를 바꿀 땐 **그 리스트를 새로 만들어** 재대입(참조 공유 함정).
- 테스트 레인은 SQLite(FK 미강제). `date.today()` 대신 `get_today_kst()`.
- `PUT /quest/status` 는 stage 정확일치라 한글 저장형 quest 를 못 찾는다(F4 재현에서 404) — 별칭으로.
- 승인 JS 는 성공 뒤 `location.reload()`(PC) / replaceState→reload(모바일). 재전이 버튼도 같은 경로.
- `test_measure_approval_teams.py` 의 `_can_show_button` 은 "화면 == 서버" 계약의 정본 — 재전이·팀 버튼도 같은 모양의 대조군(허용 팀 / 비허용 팀 / ADMIN)을 넣는다.
- 승격 시 docs·핀 줄만 충돌 — 그 처리는 총괄.
