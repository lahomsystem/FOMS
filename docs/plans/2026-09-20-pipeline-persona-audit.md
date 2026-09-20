# 페르소나 검수 종합 원장 — 컨펌→생산 배포(스테이징 `0cb601e7b`, 2026-09-20)

- 입력: `docs/plans/2026-09-20-persona-audit-A.md`(영업·CS·관리자) · `-B.md`(도면·생산) · `-C.md`(시공·CS 완료·모바일). 검수 기준은 `docs/plans/2026-09-20-persona-audit-staging-brief.md` 의 약속 6항.
- 종합 방법: 세 보고의 결함을 원인 단위로 합쳤고(같은 코드 경로면 하나), 보고가 적은 경로:행은 워크트리 코드에서 직접 대조했다. 재현 절차나 응답 원문이 없는 결함은 "근거 부족" 으로 표시했다. 서버·DB 는 이 종합에서 다시 부르지 않았다.
- 페르소나 계정·주문 시드는 전부 스테이징(`lahom-dev`)이며 운영은 접속하지 않았다(세 보고 공통).

## 1. 한 줄 결론

**약속 6항은 API·PC 그리드·관리자 경로에서 모두 확인됐다. 다만 약속 1 이 말한 "모바일 큐 카드·모바일 상세" 승인은 담당자 이름이 일치하는 사람에게만 보이므로(주문 owner·CS 팀은 못 본다) 약속 1 은 "결함 동반 확인" 이다. 범위 밖에서 P0 1건(고객 컨펌 없는 CONFIRM 주문의 제작 시작 200)과 P1 3건이 재현됐다.**

| # | 약속 | 판정 | 근거(페르소나) |
|---|---|---|---|
| 1 | 컨펌 승인 → PRODUCTION, `customer_confirmed`, `auto_transitioned true`·`next_stage "생산"`, PC 확인창 문구 | **결함 동반 확인** | A(4729 PC·4730 카드·4731 상세), B(4746 PC), C(4741 PC·카드·상세) 전부 200·PRODUCTION·문구 일치. 그러나 카드·상세 버튼은 이름 대조 통과자에게만 노출 → 결함 F1 |
| 2 | 재요청 → 409 `ALREADY_TRANSITIONED`, 생산 quest 미생성 | **확인** | A(4729·4730·4731), B(4746), C(4741) — 409 본문 동일, quests 불변, mutation_version 불변 |
| 3 | 생산 보드 제작대기/제작중 = run 축, 시작·취소 단계 무변경, 완료 = CONSTRUCTION | **확인** | A(4729), B(4746 + 숫자 대조 6시점 5소스 일치), C(4741 + 시공 보드 시공대기 확인) |
| 4 | 이다은 재현: 완료 배지(승인 버튼 없음), 제작대기 [제작 시작] → 200 → PRODUCTION+run | **확인(재현 경로 대체)** | A(4732), B(4749·4745), C(4743). 브리프의 `PUT /quest/status` 경로는 저장이 안 돼(F4) 승인→stage-override 역행으로 만들었다. history 에 PRODUCTION 항목이 하나 더 남아 보드 판정이 C9 의 quest 분기가 아니라 history 분기를 탄다(B 지적) |
| 5 | 도면 승인 409 `COMMAND_REQUIRED`(버튼 없음), DRAWING/PRODUCTION 팀 컨펌 승인 403 | **확인** | A(4734·4733), B(4744), C(4740·4741). ADMIN 사유 없는 override 422 도 세 보고 일치. B 의 HTTP 로그에는 403 줄이 없어 B 몫은 A·C 로 대신 성립 |
| 6 | 타임라인 "고객 컨펌 완료"·"제작 취소" | **확인** | A(4729), B(4746), C(4741) events API + 모바일 상세 본문. 다른 이벤트 6종은 "기타 변경"(F7) |

## 2. 결함 표 (P0→P1→P2, 이번 범위→범위 밖, 같은 원인은 하나로)

| ID | 등급 | 범위 | 제목 | 페르소나·화면 | 재현 | 기대 / 실제 | 경로:행(종합자 대조) |
|---|---|---|---|---|---|---|---|
| F1 | P1 | **이번 범위** | 모바일 큐 카드·모바일 상세의 [고객 컨펌 완료]·[실측 완료] 버튼이 담당자 이름 대조를 통과한 사람에게만 뜬다. 같은 주문을 PC 그리드는 [승인] 을 그리고 서버는 CS/SALES 팀이면 200 으로 전이시킨다 | A: CS(67) O6 4733 CONFIRM, SALES owner(66) O8 4747 MEASURE / C: SALES owner(72) 4748 CONFIRM — 모바일 큐 `/erp/dashboard?q=…`(iPhone UA, `foms_shell_pref=v2`), 상세 `/erp/orders/<id>/mobile` | 1) 담당자 이름(parties.manager) 비운 CONFIRM 주문을 CS 또는 owner SALES 로 연다 2) 카드 `erp-queue-card__quest-approve` 없음(푸터 "상세 · ERP 편집" 뿐), 상세 `#foms-detail-quest` 버튼 없음 3) 같은 계정 `POST /api/orders/<id>/quest/approve {}` → 200 `auto_transitioned true` → PRODUCTION 4) 대조군(A): 4730 에 `parties.manager.name` 을 SALES 이름으로 넣자 SALES 카드에 버튼 노출(CS 는 여전히 없음) | 기대: 세 표면(PC·모바일·API)이 같은 답. 실제: 모바일은 `_compute_can_assignee_approve`(팀 술어 → `can_modify_domain` assignee id → `sales_assignee_user_ids` 비면 manager 이름 일치)만, PC 는 `can_edit_erp or can_assignee_approve`, 서버는 팀 capability. `POST /add` 로 만든 주문은 quest `owner_person` 이 `"72"` 같은 id 문자열이고 assignments 는 비어 이름 대조도 실패(C) | `foms/services/erp_quest_display.py:319-378`(대조 완료), `foms/services/orders/erp_policy_permissions.py:45-64`, `foms/services/orders/order_create.py:118-126`, `templates/partials/shared/erp_mobile_queue_card_v2.html:250-255`, `templates/orders/partials/order_detail_mobile_v2.html:274-275`, `templates/orders/partials/dashboard_grid.html:161`, `foms/services/orders/quest_approve_authz.py:134-138`. 범위 판정은 A "이번 범위"·C "범위 밖(단 약속 1 QA 에 직접 걸림)" 으로 갈렸다 — 약속 1 이 모바일 표면을 명시하므로 이번 범위로 둔다 |
| F2 | **P0** | 범위 밖·재현됨(지도 #5, 계약 C8) | CONFIRM 인데 quest 가 한 번도 안 만들어진 주문은 [제작 시작] API 가 고객 컨펌 없이 200 → PRODUCTION | B: `claude_persona_b_production`(PRODUCTION STAFF) `POST /api/orders/4744/production/start` | 1) 4744 DRAWING → 도면 담당자 지정 → `transfer-drawing` 200 → 관리자 `confirm-drawing-receipt` 200 `new_stage CONFIRM`(quests 는 RECEIVED 뿐, blueprint 없음) 2) 생산 보드 4면은 "고객 컨펌 전" 배지·버튼 없음 3) 생산팀으로 start `{}` | 기대 409. 실제 200 `{"new_status":"PRODUCTION"}` → stage PRODUCTION, history `('PRODUCTION','제작 시작')`, `customer_confirmed` 없음. 증빙 `persona-B-http-log.txt:60` 에 quests `[('RECEIVED','OPEN')]`·hist PRODUCTION 원문 | `foms/api/production/orders.py:730-736`(CONFIRM 호환 경로), `:375-398`(`_stage_quest_block` — quest 없으면 None). 원장 §6 계약 C8 이 일부러 남긴 구멍이지만, 수령 확정 직후의 **모든** 주문이 이 상태(quest 는 GET/approve 로만 생김)라 결정이 필요하다 |
| F3 | P1 | 범위 밖 | PC 그리드가 PRODUCTION 단계 주문에 생산팀 [승인](team=PRODUCTION) 버튼을 `can_edit_erp` 만 보고 그린다 — SALES/CS 가 누르면 403, PRODUCTION 팀이 누르면 생산 quest 가 만들어진다(원장 §6 "만들지 않는다" 와 어긋남) | A: SALES(66) PC `/erp/dashboard?q=…O2` 4729 / B: `claude_master` PC 4745·4746, `claude_persona_b_production` API | 1) CONFIRM 승인 → PRODUCTION 2) 재조회: 퀘스트 셀 `erp-btn-approve-team data-team=PRODUCTION data-confirm="생산 확인을 기록할까요?…"` 3) SALES: `POST /quest/approve {"team":"PRODUCTION"}` → 403 "현재 단계 승인 권한이 없는 팀입니다." 상태 무변경(A) 4) PRODUCTION 팀: 같은 요청 → 200 `all_approved true, auto_transitioned false` → quests 에 `('생산','COMPLETED')` 생성, 이어 `production/complete` 200(B) | 기대: 승인 뒤 화면에 서버가 거부할 버튼이 남지 않고, 생산 quest 는 생기지 않는다. 실제: `team` 이 실린 요청은 `ALREADY_TRANSITIONED` 가드(`if not team and …`)를 지나친다. ADMIN 클릭은 실행 안 함(실데이터 보호). B 는 "곧바로 COMPLETED 라 제작 완료는 안 잠겼다" 고 봄 | `templates/orders/partials/dashboard_grid.html:176-196`(대조 완료; B 가 적은 `:82-95` 는 알림 배지 블록이라 오기), `foms/api/quest.py:319-334`(대조 완료), `quest_approve_authz.py:134-138` |
| F4 | P1 | 범위 밖 | `POST /api/orders/<id>/quest` · `PUT /api/orders/<id>/quest/status` 가 200 success 를 주지만 저장되지 않는다(`flag_modified` 없음) | B: `claude_master`(ADMIN) API 직접 호출 | 1) 4745 CONFIRM 에서 `POST /quest {"stage":"CONFIRM"}` → 200 2) `PUT /quest/status {"status":"COMPLETED"}` → 404 "Quest를 찾을 수 없습니다." 3) structured quests `[('RECEIVED','OPEN')]` 4) 대조군 4749 `PUT {"status":"IN_PROGRESS"}` → 200 인데 직후 status OPEN 그대로 | 기대: 커밋에 실림. 실제: 두 라우트 모두 `order.structured_data = sd`(같은 dict 재대입)만. 파일 안 `flag_modified` 호출은 승인 라우트 `:466` 한 곳뿐(종합자 grep 확인). 결과로 브리프의 이다은 재현 경로가 불가했고, 원장 §6 "PUT 로 STAFF 가 COMPLETED 를 찍으면 게이트 통과" 위험 기술은 성립하지 않는다(정정 필요) | `foms/api/quest.py:168-172`(POST), `:575-579`(PUT), 대조 `:465-466`; `models.py:89`(JSONColumn, Mutable 아님); CLAUDE.md 규약 |
| F5 | P1 | 범위 밖(지도 #3 이웃) | 팀 승인 단계(접수·생산·시공·CS)는 모바일 카드·상세 어디에도 승인 버튼이 없다 — API 는 받고 PC 그리드는 [승인] 을 그린다 | C: `claude_persona_c_cs`(CS STAFF) 4738 RECEIVED, 4736·4737 CS; ADMIN 도 동일 | 1) CS 팀으로 4738 카드·상세(`/erp/orders/4738/mobile`) → 버튼 0("현재 작업 주문 정보 확인" 텍스트만) 2) `POST /quest/approve {"team":"CS"}` → 200 → MEASURE 3) 4736 카드·상세 버튼 0, 같은 API 200 `next_stage "완료"`. 증빙 `persona-C-mobile-detail-cs-4737.html` | 기대: CTA SSOT 가 "접수 확인"·"CS 확인" 라벨을 주고 상세 템플릿에 `erp-mobile-quest-approve-team` 분기가 있으니 담당 팀 화면에 버튼. 실제: `_compute_can_assignee_approve` 가 `approval_mode != "assignee"` 면 즉시 False 이고 상세·카드가 그 값을 SSOT 로 써 팀 분기(`:298-318`)가 도달 불능. F1 과 같은 함수의 다른 분기라 같은 배치에서 고치는 게 맞다 | `foms/services/erp_quest_display.py:329-333`(대조 완료), `templates/orders/partials/order_detail_mobile_v2.html:274-275`·`:298-318`(대조 완료), `erp_mobile_queue_card_v2.html:250-254`, `foms/services/orders/quest_approve_cta.py:24-31` |
| F6 | P2 | 범위 밖 | 360° 타임라인 fragment 가 `STAGE_CHANGED` 만 읽어 엔진 전이(CUSTOMER_CONFIRMED·PRODUCTION_STARTED·STAGE_OVERRIDE)로 지난 단계를 "기록 없음" 으로 그린다 | A: SALES `GET /api/foms/fragment/order/4729,4728/timeline` / B: `claude_master` 4746 | 승인·제작 완료로 CONFIRM→PRODUCTION→CONSTRUCTION 을 통과한 주문의 fragment 를 읽는다 | 기대: 지나온 단계에 도달 시각. 실제: "실측 기록 없음 … 고객컨펌 기록 없음 … 생산 기록 없음"(현재 단계 표시는 맞음). 같은 주문의 변경 이력(OrderEvent)에는 "고객 컨펌 완료 CONFIRM → PRODUCTION" 이 정상. 증빙 `persona-B-4746-v3-timeline-fragment.html` | `foms/services/order_timeline_v3.py:83-90`(대조 완료: `event_type != "STAGE_CHANGED"` 는 건너뜀), `foms/services/orders/order_transition_service.py:196-203`(CUSTOMER_CONFIRM → `CUSTOMER_CONFIRMED`), `foms/api/fragment.py:130-160` |
| F7 | P2 | 범위 밖 | 이벤트 6종의 타임라인 라벨이 "기타 변경": `STAGE_OVERRIDE`, `PRODUCTION_REWORK_STARTED`, `PRODUCTION_COMPLETE_REVERTED`, `PRODUCTION_HOLD_TOGGLED`, `ORDER_HELD`, `CONSTRUCTION_EVIDENCE_ADDED` | B: `GET /api/orders/4746/events` / C: ADMIN 4743·4735 events | B: 4746 보류→시작→완료→완료 취소→수정 제작 뒤 조회. C: 4743 stage-override 뒤, 4735 증빙 3건 등록 뒤 조회 | 기대: 사람이 읽는 라벨("단계 수동 변경" 은 `STAGE_MANUAL_OVERRIDE` 키로만 존재). 실제: 위 6 키 전부 "기타 변경". 증빙 `persona-B-http-log.txt:63,115` | `foms/services/order_event_display.py:127-160`(종합자 grep: 6 키 모두 라벨표에 없음) |
| F8 | P2 | 범위 밖(지도 #12 는 v2 기준) | v3 모바일 셸(코호트 기본)에서는 생산 큐 카드가 상세 링크뿐이고 모바일 상세(v2·v3)에도 [제작 시작]/[제작 완료] 가 없다 | B: `claude_master` iPhone UA 쿠키 없음(v3) `/erp/production/dashboard`, `/erp/orders/4746/mobile` | v3 응답: `fos-queue-card` 링크만, `startProduction`/`completeProduction` 마크업 0. 상세: `production/start`·"제작 시작"·"제작 완료" 문자열 0. v2 셸(`foms_shell_pref=v2`) 카드에는 `data-action=startProduction/completeProduction` 있음 | 기대: 생산팀 휴대폰에서 시작·완료 가능. 실제: v3 코호트 휴대폰만 쓰는 생산팀은 누를 곳이 없다. 코호트 범위에 따라 등급 재판정 필요 | `templates/production/partials/dashboard_body.html:131`(대조 완료: `shell_variant != 'v3'` 게이트), `templates/partials/v3/persona_home_production.html:30-80`, `foms/services/feature_flags.py:257-300` |
| F9 | P2 | 범위 밖 · **근거 부족** | 주문의 SALES owner(`sales_owner_id`)는 도면 수령 확정을 못 한다(owner ≠ SALES_DOMAIN assignee) | B: `claude_persona_b_sales`(id 75, 4744 owner) `POST /api/orders/4744/confirm-drawing-receipt` | 보고에 재현 절차 절이 없고 응답 원문 한 줄뿐. `persona-B-http-log.txt` 에는 403 줄이 하나도 없다 | 보고 실제: 403 "도면 수령 확인은 지정된 영업 담당자만 가능합니다." 코드 대조로는 성립한다(assignee id → manager 이름 대조만, owner id 축 없음) — 재현 로그가 없어 "근거 부족" 으로 둔다 | `foms/api/drawing/erp_orders_draftsman.py:346-380`(대조 완료) |

지도 16건 중 이번에 다시 재현된 것(등급 없이, C): #1 CS→COMPLETED UI 호출자 0(`cs/complete` 참조 없음), #5 quest 게이트가 quest 존재에 달림(4735 CS quest 없음 → `cs/complete` 200, 4737 OPEN → 409; F2 와 같은 축), #6 CONSTRUCTION→CS quest 게이트 없음(단 스테이징은 `FOMS_CONSTRUCTION_GATE_ENABLED` 가 켜져 증빙 없이는 400 — 지도의 "기본 off" 와 다름), #12 모바일 생산 큐에 수정 제작·제작 취소·완료 취소 없음, #13 모바일 시공 큐에 시공 불가 없음, #14 CS 단계 배지 "AS".

## 3. 확인한 것(정상)

- RECEIVED→MEASURE: CS `{team:CS}` 승인 200 → MEASURE, MEASURE quest 생성, PC `data-stage MEASURE`, 프로세스 맵 접수 -1·실측 +1(A 4728; C 4738).
- MEASURE→DRAWING: SALES `{}` 승인 200 → DRAWING, 모바일 카드는 "도면 창구" 링크(A 4728·4734; C 4739).
- DRAWING→CONFIRM(B 4744·4749): 담당자 지정 → 도면팀 `transfer-drawing` 200(TRANSFERRED) → 관리자 `confirm-drawing-receipt` 200 `new_stage CONFIRM`; 생산 보드 4면(PC 그리드·칸반 칩·시트 muted·모바일 v2 배지)에 "고객 컨펌 전", 버튼 없음. 403 뒤 quest 잔류 없음.
- CONFIRM 승인 → PRODUCTION(약속 1·2): 위 표. PC 토스트 문자열 `'담당자 승인 완료 — … 단계로 이동'` 이 스테이징 JS(`erp-dashboard-quest.js?v=20260920a`)에 있음(A). 모바일 카드 요소는 `<button class="foms-btn foms-btn--primary foms-btn--sm erp-queue-card__quest-approve">` 로 링크가 아니다(A·C).
- 이다은 재현(약속 4): PC 그리드 `erp-quest-done` "고객 컨펌 완료"+"✓ … 승인완료", 승인 버튼 0; 카드 `erp-queue-card__quest-done`; 상세 `erp-quest-done`; 생산 보드 제작대기 [제작 시작]("고객 컨펌 전" 배지 없음) → start 200 → PRODUCTION·제작중; 프로세스 맵 고객컨펌 -1·생산 +1(A 4732; B 4749·4745; C 4743).
- 생산 보드(약속 3): 제작대기 = CONFIRM(호환)·PRODUCTION∧run 없음(승인 직후·취소 후) 세 경우 확인; start 200 `run_started true` → 재시작 409 `INVALID_STAGE "이미 제작중인 주문입니다."` → cancel 200 "제작을 취소했습니다. (제작대기 복귀)" stage PRODUCTION 유지 → 재취소 409 "제작 시작 전 주문은 취소할 수 없습니다." → 재시작 200 → complete 200 CONSTRUCTION(A 4729; B 4746; C 4741 + 시공 보드 시공대기 `startConstruction`).
- 생산 보드 추가(B 4746): uncomplete 200 PRODUCTION(run 재개), rework 200 `production.rework {active true, count 1}`, hold on → start 409 `HOLD_ACTIVE`(사유 포함) → `{release_hold:true}` 200. 숫자 대조 6시점(프로세스 맵·칸반 열·PC 필터 행·모바일 스탯 스트립·모바일 칩) 전부 일치 — `docs/harness/evidence/persona-B-counts.json`.
- 권한(약속 5): DRAWING STAFF·PRODUCTION STAFF 컨펌 승인 403 "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)"; ADMIN `emergency_override` 사유 없음 422; stage-override 사유 없음 400 "사유를 입력하세요."; DRAWING 팀 `production/start` 403; 세 요청 뒤 quests·mutation_version 불변(A 4733; B 4744; C 4741).
- 도면 단계(약속 5): SALES `{}`·CS `{team:CS}`·ADMIN 승인 → 409 `COMMAND_REQUIRED`; PC 퀘스트 셀 "도면 창구 작업중 …" 승인 버튼 없음; 카드 `erp-queue-card__drawing-open` 링크(A 4734; C 4740).
- 타임라인(약속 6): `CUSTOMER_CONFIRMED` "고객 컨펌 완료", `PRODUCTION_CANCELLED` "제작 취소"(추가로 `PRODUCTION_STARTED` "생산 시작", `PRODUCTION_COMPLETED` "생산 완료"); 모바일 상세 "변경 이력" 에 "✓ 고객 컨펌 완료 … CONFIRM → PRODUCTION" 렌더(A 4729; B 4746; C 4741·4743·4748).
- 시공(C 4735): 시공팀 `construction/start` 200 `attempt_id` → 시공중(PC `completeConstruction`, 모바일 [완료 준비]·[시공 완료]) → 재시작 409 `ALREADY_STARTED` → 증빙(after 2·signature) 뒤 `construction/complete` 200 → CS, 시공 보드 "시공완료"(재 업로드·AS 접수).
- CS 완료(C): 4737 CS quest OPEN → `cs/complete` 409 `QUEST_INCOMPLETE missing_teams [CS]`(CS 팀·ADMIN 동일); 4736 CS 팀 승인 200 → `cs/complete` 200 COMPLETED.
- 모바일 큐 카드 단계별 액션 표(C 보고 §C3): 접수 없음·실측 button·도면 링크·고객컨펌 button·생산/시공은 홈 카드 없음(각 보드 카드 button)·CS 없음. CONSTRUCTION 팀 계정은 `/erp/dashboard`·모바일 상세가 `/erp/shipment` 로 302(`foms/platform/http.py:267-283`, 대조 완료), 시공 보드는 본인 배정 건만.

## 4. 검수 못 한 것(blocked)과 이유

- 브라우저 스크린샷(png) 없음 — A·B·C 모두 실제 HTML 응답의 `data-order-id` 블록을 증빙으로 썼다(gstack-browse 미사용). B·C 는 HTML/로그 파일을 남겼고, A 는 보고서 인용만 있고 파일이 없다.
- `GET /api/orders/<id>/structured` 응답에 브리프가 지정한 `erp_stage_code` 키가 없다 — 대시보드 행 `data-stage` + `structured_data.workflow.stage` 로 대체(세 보고 공통, 모든 시점 일치).
- 브리프의 이다은 재현 경로(`PUT /quest/status COMPLETED`)는 F4 때문에 불가 — 승인 → stage-override CONFIRM 역행으로 대체. history 에 PRODUCTION 항목이 남아 보드 판정이 C9 의 quest 분기가 아니라 history 분기(`production_dashboard_display.py:180-186`)를 탄다. quest 분기 자체는 실서버에서 밟지 못했다.
- `production_runs` 행(SUPERSEDED/COMPLETED)은 스테이징 DB 를 직접 읽지 않아 버킷 이동으로만 간접 확인(B).
- C5 아이폰 실기기 1회: 기기 없음 → 미수행(C).
- CONSTRUCTION 팀 페르소나는 `/erp/dashboard`·모바일 상세가 302, 미배정 시드는 시공 보드에 안 뜸 → 시공 보드 화면은 ADMIN(iPhone UA), API 는 시공 페르소나로 나눠 확인(C).
- A 는 "DRAWING 팀이 만든 CONFIRM 주문"(도면 전달→수령 확정) 경로를 B 영역이라 밟지 않고 stage-override 로 CONFIRM 시드를 만들었다(B 가 그 경로를 밟았으므로 공백은 없음).
- ADMIN 이 PRODUCTION 단계 팀 [승인] 을 누르는 경우(F3)는 실데이터 보호로 실행하지 않았다(A). PRODUCTION 팀 클릭은 B 가 실행했다.
- B 의 HTTP 로그(`persona-B-http-log.txt`)에는 403 응답 줄이 없다 — B 가 적은 403 4건(DRAWING/PRODUCTION 팀 승인, DRAWING 팀 start, SALES owner 수령 확정)은 로그로 못 받친다. 앞 셋은 A·C 가 독립 재현했고, 마지막은 F9 "근거 부족".

## 5. 스테이징 정리 상태

- 주문 soft delete(`POST /delete/<id>` 302, 이후 `GET /structured` 실패·대시보드 행 0) 22건: A 4728·4729·4730·4731·4732·4733·4734·4747 / B 4744·4745·4746·4749 / C 4735·4736·4737·4738·4739·4740·4741·4742·4743·4748.
- 계정 비활성화(`POST /admin/users/edit/<id>` is_active 해제 302, 로그인 거부 확인) 12건: 66·67·68·69(`claude_persona_a_*`), 70·71·72·73·74(`claude_persona_c_*`), 75·76·77(`claude_persona_b_*`). 계정 행은 남아 `/admin/api/users` 에 비활성으로 노출된다.
- 남은 잔여물(앱 경로로 못 지움, 삭제 주문 하위라 화면 비노출):
  - `production_runs` 행: 4729(3행)·4732(1행)(A), 4744·4745·4746(B, 행 수 미기재), 4741·4743(C).
  - 첨부: 4735 의 2115·2116·2117(휴지통 주문 하위).
  - R2: `orders/4744/drawing_gateway/revisions/20260920_052500_3a7e1408_persona_b_drawing.png`, `orders/4749/drawing_gateway/revisions/*persona_b4.png`(각 1px PNG).
  - OrderEvent·SecurityLog·감사 로그(append-only, 삭제 API 없음).
- 로컬: 하네스 쿠키(.pkl)·페르소나 비밀번호 파일은 세 보고 모두 삭제했다고 적었다. 비밀번호 문자열은 보고서·증빙 로그에 없다(종합자 grep: `password|passwd` 0건).
- 증빙 파일: `docs/harness/evidence/persona-B-http-log.txt`(134줄), `persona-B-counts.json`, `persona-B-*.html` 5건, `persona-C-http-log.jsonl`(197줄), `persona-C-*.html` 6건. A 는 파일 없음.

## 6. 다음 배치 권고(범위 밖 P1 이상)

1. **F2(P0) 결정 먼저** — 계약 C8 을 유지할지(수령 확정 직후 주문은 화면만 "고객 컨펌 전"), `confirm-drawing-receipt` 가 CONFIRM quest 를 심도록 바꿀지, `_stage_quest_block` 이 CONFIRM 단계에서 quest 부재를 차단으로 볼지 셋 중 하나. 화면(4면 버튼 없음)과 API(200)가 갈린 유일한 P0.
2. **F4(P1)** — `POST /quest`·`PUT /quest/status` 에 `flag_modified` 추가(규약 그대로). 동시에 원장 `2026-09-17-confirm-to-production-workflow-ledger.md` §6 의 "PUT 로 COMPLETED 를 찍으면 게이트 통과" 위험 기술을 정정한다(고치면 그 위험이 실제로 생기므로 게이트 쪽 판단도 같이).
3. **F3(P1)** — PC 그리드 팀 모드 버튼을 서버 술어(팀 capability)와 맞추고, PRODUCTION 단계에서 생산 quest 를 만드는 경로를 원장 §6 의도("만들지 않는다")에 맞게 막거나 의도를 고쳐 적는다. `quest.py:330` 의 `if not team` 가드도 같이 본다.
4. **F5(P1)** — `_compute_can_assignee_approve` 의 `approval_mode != "assignee" → False` 분기를 팀 승인용 술어로 나누고, 모바일 카드·상세가 그 값을 쓰게 한다. F1 과 같은 함수라 이번 범위 F1 수정과 한 배치가 효율적이다.
5. P2 묶음(F6·F7·F8·F9)은 문구·표시 결함이라 별도 배치. F8 은 v3 코호트 실제 범위를 먼저 재서 등급을 다시 매긴다. F9 는 재현 로그부터 받는다.
6. 절차 권고: 다음 페르소나 검수는 A 처럼 파일 없는 인용만 남기지 말고 B·C 처럼 응답 원문 파일을 남기되, 403 같은 거부 응답도 로그에 실리게 한다(B 로그 공백).
