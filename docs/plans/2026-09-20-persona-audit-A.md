# 페르소나 검수 A — 영업·CS·관리자 (스테이징 실서버, 2026-09-20)

- 환경: `https://lahom-dev.up.railway.app`, 자산 핀 `?v=20260920a` 확인(deploy `0cb601e7b`). 운영 서버 미접속.
- 검수자 계정: `claude_master`(ADMIN) + 페르소나 STAFF 4종 `claude_persona_a_{sales,cs,drawing,production}`(id 66·67·68·69, 검수 후 비활성화).
- 시드 주문 8건(고객명 `CLAUDE-TEST-PERSONA-A-O1…O8`, 연락처 010-0000-0000, 검수 후 soft delete): id 4728·4729·4730·4731·4732·4733·4734·4747.
- 방법: `requests` HTTP 하네스(로그인 폼 → `X-CSRF-Token`+`Origin`/`Referer`, Chrome desktop UA / iPhone UA + 쿠키 `foms_shell_pref=v2`). 화면 판정은 실제 HTML 응답의 `data-order-id` 행/카드 블록 안에서만 했다. 브라우저 스크린샷은 찍지 않았다(응답 원문을 아래에 인용).
- 주의: `GET /api/orders/<id>/structured` 응답에는 `erp_stage_code` 키가 없다(브리프가 지정한 판정 경로). 단계는 `structured_data.workflow.stage` 와 대시보드 행 `data-stage` 로 읽었다. 둘은 모든 시점에 일치했다.
- 시드 방식: ERP 주문 등록 경로 `POST /add`(create_mode=ERP_ORDER, `sales_owner_id=66`) → RECEIVED. CONFIRM 시드는 관리자 `POST /api/orders/<id>/workflow/stage-override`(to_stage CONFIRM, reason, confirm:true → 200 mode "skip"). 이다은 재현(O5)은 CONFIRM 에서 SALES 승인(→PRODUCTION) 뒤 stage-override 로 CONFIRM 역행(mode "regress") — 결과 dict 가 CEO 계약 C9 와 같은 모양(quest 고객컨펌 COMPLETED·assignee approved, blueprint.customer_confirmed True, run 0).

## 결함

### P1 모바일 큐 카드·모바일 상세의 [고객 컨펌 완료] 버튼이 담당자(parties.manager / sales_assignee_user_ids)에게만 뜬다 — 같은 주문을 PC 그리드는 [승인] 을 그리고 서버 API 는 CS/SALES 팀이면 200 으로 생산 전이시킨다
- 페르소나/계정/화면: CS STAFF(`claude_persona_a_cs`, id 67) / SALES STAFF(`claude_persona_a_sales`, id 66, 주문 owner) — PC `/erp/dashboard?q=…`, 모바일 `/erp/dashboard?q=…&focus_order=<id>`(iPhone UA, v2 셸), 모바일 상세 `/erp/orders/<id>/mobile`.
- 재현 절차:
  1. O6(4733, CONFIRM, parties.manager 없음, assignments {}) 을 CS 로 연다.
  2. PC 그리드 퀘스트 셀: `erp-btn-approve-assignee` [승인] 버튼 있음("담당자 지정 필요 승인").
  3. 같은 계정 모바일 큐 카드: `erp-queue-card__quest-approve` 요소 **없음**(CTA 목록 `[]`, 푸터 "상세 · ERP 편집" 뿐). 모바일 상세 `#foms-detail-quest`: "현재 작업 고객 컨펌" 만, 버튼 없음.
  4. 같은 계정으로 `POST /api/orders/4733/quest/approve {}` → `200 {"auto_transitioned": true, "next_stage": "생산", …}` → 단계 PRODUCTION, `blueprint.customer_confirmed True`(confirmed_by claude_persona_a_cs).
  5. 대조군: O3(4730) 에 `parties.manager.name = "페르소나A-SALES"` 를 PUT 으로 넣자 SALES 모바일 카드에 `<button class="… erp-queue-card__quest-approve" data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요?…">고객 컨펌 완료</button>` 가 떴고(CS 에게는 여전히 없음), O8(4747, MEASURE, manager 없음) 은 owner 인 SALES 에게도 모바일 카드/상세에 [실측 완료] 가 없었다(PC 는 있음, API 200).
- 기대 / 실제: 약속 1 은 "모바일 큐 카드 [고객 컨펌 완료]·모바일 상세" 에서 승인이 된다고 했다. 실제로는 `_compute_can_assignee_approve`(assignee id 또는 manager 이름 일치) 를 통과하는 사람에게만 모바일 버튼이 뜨고, PC 그리드는 `can_edit_erp` 로, 서버는 팀 capability(CS/SALES) 로 허용한다 — 세 표면의 답이 다르다. 담당자 이름이 비어 있거나 다른 사람 이름인 주문(마법사에서 담당자를 안 고른 주문, 관리자가 만든 주문)은 모바일에서 컨펌을 끝낼 수 없고 PC 로 가야 한다.
- 근거 경로:행: `foms/services/erp_quest_display.py:319-378`(`_compute_can_assignee_approve`: 팀 술어 통과 뒤 `can_modify_domain` → `sales_assignee_user_ids` → manager 이름 일치), `foms/services/orders/erp_policy_permissions.py:45-64`(`can_modify_domain` SALES_DOMAIN = assignee id 만), `templates/partials/shared/erp_mobile_queue_card_v2.html:250-255`(`quest_actionable` 가 `can_assignee_approve` 필수), `templates/orders/partials/order_detail_mobile_v2.html:274-275`, `templates/orders/partials/dashboard_grid.html:161`(`can_edit_erp or can_assignee_approve`), `foms/services/orders/quest_approve_authz.py:134-138`(서버는 팀 capability).
- 범위 판정: 이번 범위(약속 1 의 모바일 버튼) — 술어 자체는 기존이고 실측(MEASURE)에도 같은 규칙이 적용된다(지도 #11 과 같은 축이지만 16건 목록에 없는 항목).

### P1 승인 직후 PC 그리드가 합성 '생산' 퀘스트에 생산팀 [승인] 버튼을 SALES/CS 에게 그리고, 누르면 403 이다
- 페르소나/계정/화면: SALES STAFF(id 66) — PC `/erp/dashboard?q=CLAUDE-TEST-PERSONA-A-O2`.
- 재현 절차:
  1. O2(4729) CONFIRM 을 SALES 가 PC [승인] → 200, 단계 PRODUCTION(정상, 아래 "확인한 것" 3).
  2. 페이지 재조회: 퀘스트 셀 "진행중 생산 … 담당 팀 생산팀 승인 [승인]" — `<button class="… erp-btn-approve-team" data-order-id="4729" data-team="PRODUCTION" data-confirm="생산 확인을 기록할까요?\n단계는 '생산' 그대로 유지됩니다.…">`.
  3. 그 버튼이 보내는 요청 `POST /api/orders/4729/quest/approve {"team":"PRODUCTION"}` → `403 {"message": "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)"}`. 서버 상태 무변경(quests 에 PRODUCTION 없음, mv 3 유지).
- 기대 / 실제: 약속 2 대로 **같은 버튼(빈 payload)** 재요청은 409 ALREADY_TRANSITIONED 로 막히고 생산 quest 도 안 생긴다(정상). 그러나 새로고침 뒤 화면이 그리는 **다른 버튼**(팀 승인)은 영업/CS 에게 보이면서 서버가 거부한다. `team` 이 실린 요청은 `ALREADY_TRANSITIONED` 가드(`if not team and …`) 를 지나치므로 ADMIN 이 이 버튼을 누르면 PRODUCTION quest 가 생성·완결된다(직접 실행하진 않았다 — 실데이터 오염 방지).
- 근거 경로:행: `templates/orders/partials/dashboard_grid.html:176-196`(팀 모드 버튼은 `can_edit_erp` 만 본다), `foms/api/quest.py:319-334`(가드가 `not team` 조건), `foms/services/orders/quest_approve_authz.py:134-138`.
- 범위 판정: 범위 밖 — 기존 PC 그리드 팀 모드 버튼의 일반 동작(지도 #4·#5 와 같은 축, 16건 목록엔 없음). 데이터 손상은 없고 403 알림으로 끝나 P1 로 둔다.

### P2 360° 타임라인 fragment 는 엔진 전이로 지난 단계를 "기록 없음" 으로 그린다
- 페르소나/계정/화면: SALES STAFF — `GET /api/foms/fragment/order/<id>/timeline`(모바일 상세 상단 8단계 타임라인).
- 재현 절차: O2(4729, CONFIRM→PRODUCTION→CONSTRUCTION 을 승인·제작 완료로 통과) 와 O1(4728, RECEIVED→MEASURE→DRAWING 을 승인으로 통과) 의 fragment 를 읽는다.
- 기대 / 실제: 지나온 단계에 도달 시각이 남아야 한다. 실제 O2: "실측 기록 없음 … 고객컨펌 기록 없음 … 생산 기록 없음"(현재 생산), O1: "실측 기록 없음 도면 기록 없음"(현재 도면). 같은 주문의 "변경 이력"(OrderEvent) 에는 "고객 컨펌 완료 CONFIRM → PRODUCTION", "생산 시작", "제작 취소", "생산 완료 PRODUCTION → CONSTRUCTION" 이 정상으로 보인다.
- 근거 경로:행: `foms/services/order_timeline_v3.py:83-90`(`event_type != "STAGE_CHANGED"` 는 전부 건너뜀), `foms/services/orders/order_transition_service.py:196-203`(CUSTOMER_CONFIRM 은 `CUSTOMER_CONFIRMED` 이벤트를 남긴다).
- 범위 판정: 범위 밖(이번 배포 전에도 같은 규칙, 16건 목록엔 없음).

## 확인한 것(정상)
- 시나리오 1 RECEIVED→MEASURE: CS(67) `POST /api/orders/4728/quest/approve {"team":"CS"}` → `200 {"all_approved": true, "auto_transitioned": true, "next_stage": "실측"}`; workflow.stage MEASURE, quests = RECEIVED COMPLETED + MEASURE OPEN(assignee) 생성; PC 그리드 `data-stage="MEASURE"`; 프로세스 맵 주문접수 21→20, 실측 303→304(다른 칸 불변).
- 시나리오 2 MEASURE→DRAWING: SALES(66) `POST …/4728/quest/approve {}` → 200 next_stage "도면"; stage DRAWING; 모바일 큐 카드는 `<a class="… erp-queue-card__drawing-open">도면 창구</a>` 링크로 바뀜(승인 버튼 없음). O7(4734) 로 같은 경로 재확인. (모바일 실측 카드 버튼 미노출은 위 P1 참조 — O8.)
- 시나리오 3 CONFIRM 승인(약속 1):
  - PC(SALES, O2 4729): 그리드 버튼 `erp-btn-approve-assignee` 의 `data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요?\n\nCLAUDE-TEST-PERSONA-A-O2 / #4729"`; `POST {}` → `200 {"auto_transitioned": true, "next_stage": "생산", "all_approved": true, "quest": {"stage": "고객컨펌", "status": "COMPLETED", "approval_mode": "assignee", …}}`; `structured_data.workflow.stage = "PRODUCTION"`, `blueprint = {"customer_confirmed": true, "confirmed_at": "2026-09-20T05:27:08", "confirmed_by": "claude_persona_a_sales"}`; 그리드 `data-stage="PRODUCTION"`. 스테이징이 내려주는 `erp-dashboard-quest.js?v=20260920a` 의 토스트 문자열 `'✅ 담당자 승인 완료 — ' + nextStageLabel + ' 단계로 이동'` 확인.
  - 모바일 큐 카드(SALES, O3 4730, manager 지정): `<button type="button" class="foms-btn foms-btn--primary foms-btn--sm erp-queue-card__quest-approve" data-order-id="4730" data-approve-label="고객 컨펌 완료" data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요?\n\nCLAUDE-TEST-PERSONA-A-O3 / #4730">` — **button 이지 링크가 아니다**. 핸들러 `static/js/foms/erp-quest-approve.js:144-150` 가 `window.confirm(data-confirm)` 뒤 같은 API 를 부른다. `POST {}` → 200 next_stage "생산", stage PRODUCTION, customer_confirmed True; 카드 재조회 `data-workflow-stage="PRODUCTION"`, CTA 없음.
  - 모바일 상세(SALES, O4 4731): `#foms-detail-quest` 에 `erp-mobile-quest-approve-assignee` 버튼 + 같은 data-confirm; `POST {}` → 200 next_stage "생산", stage PRODUCTION, customer_confirmed True; 상세 재조회 "현재 작업 생산", 버튼 없음.
- 약속 2 재요청: O2·O3·O4 각각 같은 버튼(빈 payload) 재요청 → `409 {"code": "ALREADY_TRANSITIONED", "message": "이미 생산 단계로 넘어간 주문입니다. 화면을 새로고침하세요."}` (O2 는 2회 연속). quests 에 PRODUCTION/생산 quest 없음, mutation_version 불변.
- 시나리오 4 이다은 재현(O5 4732, CONFIRM·고객컨펌 quest COMPLETED·assignee approved·customer_confirmed True·run 0):
  - PC 그리드(SALES): `<span class="badge bg-success erp-quest-done">고객 컨펌 완료</span>`, `erp-btn-approve-*` 없음, 펼침 "claude_persona_a_sales ✓ 승인완료".
  - 모바일 큐 카드: `<span class="… erp-queue-card__quest-done" role="status">고객 컨펌 완료</span>`, 승인 버튼 없음. 모바일 상세: `erp-quest-done` "고객 컨펌 완료", 버튼 없음.
  - 생산 보드(관리자, `/erp/production/dashboard?q=…`): 행 배지 "제작대기", `<button class="… erp-production-action erp-grid-btn-quest" data-action="startProduction">제작 시작</button>`, "고객 컨펌 전" 배지 없음. `POST /api/orders/4732/production/start {}` → `200 {"message": "제작이 시작되었습니다.", "new_status": "PRODUCTION"}`; stage PRODUCTION, 보드 행 "제작중 생산 중"(버튼 없음); 프로세스 맵 고객컨펌 -1, 생산 +1.
- 시나리오 5 권한 대조군(O6 4733 CONFIRM): DRAWING STAFF `POST {}` → `403 {"message": "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)"}`; PRODUCTION STAFF → 403 같은 본문; ADMIN `{"emergency_override": true}`(사유 없음) → `422 {"message": "오버라이드 승인은 사유(override_reason)가 필수입니다."}`. 세 요청 뒤 quests·mutation_version 불변(quest 미생성). stage-override 도 사유 없이 → `400 {"error": "사유를 입력하세요."}`.
- 시나리오 6 도면 단계 승인(O7 4734 DRAWING): SALES `POST {}` → `409 {"code": "COMMAND_REQUIRED", "message": "도면 단계는 단독 퀘스트 승인이 아니라 전용 command로 진행해야 합니다."}`; CS `{"team":"CS"}` → 409 같은 본문. PC 그리드 퀘스트 셀은 "도면 창구 작업중 … 별도 작업실 열기" 만(승인 버튼 없음), 모바일 카드는 "도면 창구" 링크.
- 약속 3 생산 보드(관리자, O2 4729 PRODUCTION·run 없음): 제작대기 [제작 시작] → `200 {"run_started": true, "new_status": "PRODUCTION"}` → 행 "제작중"; 재시작 → `409 {"code": "INVALID_STAGE", "message": "이미 제작중인 주문입니다."}`; `production/cancel` → `200 {"message": "제작을 취소했습니다. (제작대기 복귀)", "new_status": "PRODUCTION"}` → 행 "제작대기"+[제작 시작], stage 여전히 PRODUCTION; 다시 시작 → 200 run_started; `production/complete` → `200 {"new_status": "CONSTRUCTION"}` → 행 "제작완료", stage CONSTRUCTION.
- 약속 6 타임라인 라벨: `GET /api/orders/4729/events` 의 `event_label` — CUSTOMER_CONFIRMED "고객 컨펌 완료", PRODUCTION_CANCELLED "제작 취소"(PRODUCTION_STARTED "생산 시작", PRODUCTION_COMPLETED "생산 완료"). 모바일 상세 "변경 이력" 섹션에 "✓ 고객 컨펌 완료 페르소나A-SALES · 2026-09-20 14:27 · CONFIRM → PRODUCTION", "✓ 제작 취소 …" 렌더 확인.

## 정리 목록
- 주문 soft delete(`POST /delete/<id>` → 302, 이후 `GET /api/orders/<id>/structured` 404, 대시보드 행 없음): 4728, 4729, 4730, 4731, 4732, 4733, 4734, 4747.
- 계정 비활성화(`POST /admin/users/edit/<id>` is_active 해제 → 302; 새 세션 로그인 시 "비활성화된 계정입니다"): 66 claude_persona_a_sales, 67 claude_persona_a_cs, 68 claude_persona_a_drawing, 69 claude_persona_a_production. 계정 행 자체는 남아 있다(`/admin/api/users` 목록에 비활성으로 노출).
- 앱 경로로 못 지운 것: soft delete 된 4729(run 3행)·4732(run 1행) 의 `production_runs` 행과 OrderEvent/감사 로그는 주문과 함께 남는다(앱에 삭제 경로 없음, 주문이 삭제 상태라 화면엔 안 보인다). O2 의 CONSTRUCTION 도달로 생긴 시공 일정 행은 없다(시공일 미입력).
- 로컬: 하네스 쿠키·페르소나 비밀번호 파일은 세션 scratchpad 에서 삭제했다. 비밀번호는 어디에도 적지 않았다.
