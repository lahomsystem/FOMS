# 페르소나 검수 C — 시공·CS 완료·모바일 (스테이징 실서버, 2026-09-20)

- 환경: `https://lahom-dev.up.railway.app` (deploy `0cb601e7b`, 자산 핀 `?v=20260920a`). 운영 서버 미접속.
- 계정: `claude_master`(ADMIN, id 58) + 페르소나 `claude_persona_c_{construction,cs,sales,drawing,production}`(STAFF, id 70·71·72·73·74). 비밀번호는 어디에도 적지 않음.
- 도구: HTTP(requests, Chrome desktop UA / iPhone UA). 모바일 v2 큐는 스테이징 `claude_master` 가 v3 셸이라 쿠키 `foms_shell_pref=v2` 를 얹어 렌더했다(`foms/services/feature_flags.py:270-283`).
- 시드: `POST /add`(create_mode=ERP_ORDER, `erp_stage` 로 단계 지정, `sales_owner_id=27`) — 고객명 `CLAUDE-TEST-PERSONA-C-*`, 연락처 `010-0000-0000`. 단계 이동은 전부 실제 버튼이 부르는 API 로 밟았다.
- `erp_stage_code` 원문: `GET /api/orders/<id>/structured` 응답에는 `erp_stage_code` 키가 **없다**(top-level 키: as_cycle·mutation_version·structured_data…). 대시보드 행 `<tr class="erp-main-row" data-stage="…">` 를 원문으로 썼고, `structured_data.workflow.stage` 를 병기했다.
- 증거: `docs/harness/evidence/persona-C-http-log.jsonl`(요청·응답 197행 원문), `docs/harness/evidence/persona-C-*.html`(모바일 큐·상세·생산·시공 실제 응답 6건).

시드 주문 (id → 태그, 시작 단계): 4735 C1-CONS(CONSTRUCTION) · 4736 C2-CS-NOQ(CS) · 4737 C2-CS-Q(CS) · 4738 C3-RECEIVED · 4739 C3-MEASURE · 4740 C3-DRAWING · 4741 C3-CONFIRM · 4742 C3-PRODUCTION · 4743 C4-DAEUN(CONFIRM) · 4748 C5-CONFIRM-OWNED(CONFIRM, `sales_owner_id=72`=페르소나 SALES).

## 이번 배포가 약속하는 것 6항 — 판정

| # | 약속 | 판정 | 원문 |
|---|---|---|---|
| 1 | 컨펌 승인 → PRODUCTION, `customer_confirmed`, `auto_transitioned True`·`next_stage "생산"`, 확인 문구 | **OK** | 4741 `POST /quest/approve {}` → 200 `{"auto_transitioned": true, "next_stage": "생산", "all_approved": true}`; `structured_data.blueprint.customer_confirmed true`, `workflow.stage PRODUCTION`, PC 행 `data-stage="PRODUCTION"`. PC 그리드 [승인] `data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요?\n\nCLAUDE-TEST-PERSONA-C-C3-CONFIRM / #4741"`; 모바일 큐 카드 `<button class="foms-btn foms-btn--primary foms-btn--sm erp-queue-card__quest-approve" data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요? …">고객 컨펌 완료</button>`; 모바일 상세 하단 고정 버튼 '고객 컨펌 완료' 동일 문구. |
| 2 | 재요청 → 409 `ALREADY_TRANSITIONED`, 생산 quest 미생성 | **OK** | 4741 재요청 → 409 `{"code": "ALREADY_TRANSITIONED", "message": "이미 생산 단계로 넘어간 주문입니다. 화면을 새로고침하세요."}`; quests = `[CONFIRM COMPLETED]` 그대로(PRODUCTION quest 없음). |
| 3 | 생산 보드 제작대기/제작중 = run 축, 시작/취소 단계 무변경, 완료 = CONSTRUCTION | **OK** | 4741 PRODUCTION·run 없음 → PC 시트 '제작대기'+`startProduction`, 모바일 카드 [제작 시작]. `production/start`(PRODUCTION 팀) → 200 `{"new_status": "PRODUCTION", "run_started": true}` → '제작중', 모바일 [제작 완료]. 재시작 → 409 `INVALID_STAGE "이미 제작중인 주문입니다."`. `production/cancel` → 200 `{"message": "제작을 취소했습니다. (제작대기 복귀)", "new_status": "PRODUCTION"}` → '제작대기'·`data-stage="PRODUCTION"`. 재시작 200 → `production/complete` → 200 `{"new_status": "CONSTRUCTION"}` → 생산 보드 '제작완료', 시공 보드 '시공대기'+`startConstruction`. |
| 4 | 이다은 재현: 완료 배지(승인 버튼 없음), 제작대기 [제작 시작] → 200 → PRODUCTION+run | **OK** | 4743 승인(→PRODUCTION) 뒤 `POST /workflow/stage-override {to_stage: CONFIRM, reason, confirm: true}` → 200 `{"from": "PRODUCTION", "to": "CONFIRM", "mode": "regress"}`; quest `CONFIRM COMPLETED assignee approved`, `customer_confirmed true`. PC 그리드 quest 칸: 배지 `고객 컨펌 완료`·`✓ claude_master 승인완료`, [승인] 버튼 없음. 큐 카드: `<span class="… erp-queue-card__quest-done" role="status">고객 컨펌 완료</span>`(버튼 없음). 모바일 상세: `erp-quest-done` 배지 '고객 컨펌 완료', 승인 버튼 0. 생산 보드 제작대기 [제작 시작] → `production/start` 200 `{"new_status": "PRODUCTION"}` → '제작중'(run 발급), PC 행 `data-stage="PRODUCTION"`. |
| 5 | 도면 승인 409 `COMMAND_REQUIRED`(버튼 없음), DRAWING/PRODUCTION 팀 컨펌 승인 403 | **OK** | 4740(DRAWING) ADMIN 승인 → 409 `{"code": "COMMAND_REQUIRED", "message": "도면 단계는 단독 퀘스트 승인이 아니라 전용 command로 진행해야 합니다."}`; PC 그리드 quest 버튼 0(배지 '작업중'), 큐 카드는 `<a … erp-queue-card__drawing-open href="/erp/drawing-workbench/4740">도면 창구</a>` 링크만, 상세 quest 섹션 없음. 4741 DRAWING 페르소나 → 403 `"현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)"`, PRODUCTION 페르소나 → 403 동일, 단계 CONFIRM 유지. ADMIN 사유 없는 override → 422 `"오버라이드 승인은 사유(override_reason)가 필수입니다."`. |
| 6 | 타임라인 '고객 컨펌 완료'·'제작 취소' | **OK** | `GET /api/orders/4741/events` → `("CUSTOMER_CONFIRMED","고객 컨펌 완료")`, `("PRODUCTION_CANCELLED","제작 취소")`; 모바일 상세(`/erp/orders/4741/mobile`) 본문에 두 문구 존재. 4743·4748 도 `CUSTOMER_CONFIRMED → 고객 컨펌 완료`. |

## 결함

### P1 영업 담당자로 지정된 사용자 폰에 [고객 컨펌 완료] 버튼이 없다 — API 는 200 으로 받는다
- 페르소나/계정/화면: `claude_persona_c_sales`(SALES STAFF, id 72) / 모바일 큐 `/erp/dashboard?q=…`(iPhone UA, v2) · 모바일 상세 `/erp/orders/4748/mobile`
- 재현 절차:
  1. ADMIN 이 `POST /add`(ERP_ORDER, erp_stage=CONFIRM, `sales_owner_id=72`)로 주문 4748 생성. 담당자 이름(parties.manager)은 비움.
  2. 72 로 로그인해 모바일 큐 카드·상세를 연다.
  3. 같은 계정으로 `POST /api/orders/4748/quest/approve {}`.
- 기대 / 실제: 기대 — 담당 SALES 가 카드·상세에서 [고객 컨펌 완료] 를 누를 수 있어야 한다(약속 1). 실제 — 카드 푸터 `[상세, ERP 편집]` 만(`persona-C-mobile-queue-sales-4748.html`), 상세 quest 섹션 텍스트 "현재 작업 고객 컨펌" 에 버튼 0, 하단 고정 버튼 0. 그런데 API 는 **200** `{"auto_transitioned": true, "next_stage": "생산", "quest": {"approved_by": 72, "owner_person": "72", …}}` → 단계 PRODUCTION. 화면이 서버보다 좁다.
- 근거 경로:행: `foms/services/orders/order_create.py:122`(quest owner_person 에 `str(owner_user_id)` 를 넣고 `assignments.sales_assignee_user_ids` 는 안 채움) → `foms/services/erp_quest_display.py:352-374`(`can_modify_domain`→`get_assignee_ids` 빈 목록, 이름 대조는 "72" 라 실패) → `templates/partials/shared/erp_mobile_queue_card_v2.html:250-254`·`templates/orders/partials/order_detail_mobile_v2.html:274-275`(`can_assignee_approve` 가 노출 SSOT). 서버 `foms/services/orders/quest_approve_authz.py:135-137` 은 팀 capability(CS/SALES)만 본다.
- 범위 판정: 범위 밖(지도 외 — 소유자 판정 축, 09-13 팀 술어 게이트 이전부터). 단 약속 1 의 "모바일 큐 카드 [고객 컨펌 완료]" 를 **담당 영업이 못 본다**는 점에서 이번 배포 QA 에 직접 걸린다. 실운영 주문은 담당자 이름이 채워져 이름 대조로 통과할 수 있으나, 이름이 비거나 로그인 이름과 다르면 같은 결과.

### P1 팀 승인 단계(접수·생산·시공·CS)는 모바일 카드·상세 어디에도 승인 버튼이 없다 — API 는 받는다
- 페르소나/계정/화면: `claude_persona_c_cs`(CS STAFF) / 모바일 큐 카드·상세 4738(RECEIVED), 4736·4737(CS); ADMIN 도 동일
- 재현 절차:
  1. CS 팀으로 RECEIVED 주문 4738 의 큐 카드·상세(`/erp/orders/4738/mobile`)를 연다 → 버튼 없음(상세 quest 섹션 "현재 작업 주문 정보 확인" 텍스트만).
  2. 같은 계정으로 `POST /api/orders/4738/quest/approve {"team":"CS"}` → 200 `{"auto_transitioned": true, "next_stage": "실측"}` → 단계 MEASURE.
  3. CS 주문 4736 카드(`AS` 배지)·상세(`persona-C-mobile-detail-cs-4737.html`)도 버튼 0; `POST /api/orders/4736/quest/approve {"team":"CS"}` → 200 `{"next_stage": "완료"}`.
- 기대 / 실제: 기대 — CTA SSOT 가 `RECEIVED: "접수 확인"`, `CS: "CS 확인"` 라벨을 주고(`quest_approve_cta.py:24-31`) 상세 템플릿에 팀 승인 버튼 분기(`erp-mobile-quest-approve-team`)가 있으므로 CS 팀 화면에 버튼이 떠야 한다. 실제 — 카드·상세 모두 버튼 0. PC 그리드는 같은 주문에 [승인] 버튼을 그린다(4738 `data-confirm="주문 접수 확인을 마치고 실측 단계로 넘길까요? …"`). 모바일에서만 막다른 길.
- 근거 경로:행: `foms/services/erp_quest_display.py:329-333`(`approval_mode != "assignee"` 면 무조건 False) ← `templates/orders/partials/order_detail_mobile_v2.html:274-275`(`can_approve_quest = … can_assignee_approve …`) → `:300-320` 팀 분기가 도달 불능. 카드도 `erp_mobile_queue_card_v2.html:250-254` 같은 조건.
- 범위 판정: 범위 밖(지도 #3 의 이웃 — 지도는 CONFIRM 만 적었고 이번 배포가 CONFIRM 은 고쳤다; 팀 단계는 그대로).

### P2 `STAGE_OVERRIDE`·`CONSTRUCTION_EVIDENCE_ADDED` 이벤트가 타임라인에 "기타 변경" 으로 뜬다
- 페르소나/계정/화면: ADMIN / `GET /api/orders/4743/events`, `GET /api/orders/4735/events`
- 재현 절차: 4743 stage-override 뒤 events 조회; 4735 증빙 3건 등록 뒤 events 조회.
- 기대 / 실제: 기대 — '단계 수동 변경'(라벨표에 `STAGE_MANUAL_OVERRIDE` 존재), '시공 증빙 추가' 류. 실제 — `("STAGE_OVERRIDE","기타 변경")`, `("CONSTRUCTION_EVIDENCE_ADDED","기타 변경")`.
- 근거 경로:행: `foms/services/order_event_display.py:127-160` 라벨표에 `STAGE_OVERRIDE`·`CONSTRUCTION_EVIDENCE_ADDED` 키가 없다(`STAGE_MANUAL_OVERRIDE` 만 있음).
- 범위 판정: 범위 밖(지도 외, 문구).

## 지도 16건 중 재현된 것 (등급 없이 "범위 밖·재현됨")
- #1 CS→COMPLETED UI 호출자 0: `/erp/dashboard?q=…` HTML 에 `cs/complete` 참조 0(`/erp/cs/dashboard`·`/erp/as/dashboard` 는 404). 범위 밖·재현됨.
- #5 quest 게이트가 quest 존재에 달림: 4735 는 CS quest 가 없어 `cs/complete` 200 통과, 4737 은 OPEN quest 로 409. 범위 밖·재현됨.
- #6 CONSTRUCTION→CS quest 게이트 없음: 4735 의 CONSTRUCTION quest 가 OPEN(팀 승인 0)인 채로 `construction/complete` 200 → CS. 범위 밖·재현됨. (단 스테이징은 `FOMS_CONSTRUCTION_GATE_ENABLED` 가 켜져 있어 증빙 없이는 400 `{"error": "완료 요건 미충족", "data": {"missing": ["after", "signature"]}}` — 지도의 "기본 off" 와 다르다.)
- #12 모바일 생산 큐에 수정 제작·제작 취소·완료 취소 없음: `data-action` 은 `startProduction`/`completeProduction` 뿐(`persona-C-production-mobile-admin.html`). 범위 밖·재현됨.
- #13 모바일 시공 큐에 시공 불가 없음: `data-action` 은 `startConstruction`/`openCompleteGate`/`completeConstruction`/`reuploadConstructionPhotos`/`openAsAcceptModal`. 범위 밖·재현됨.
- #14 CS 단계 배지 "AS": 큐 카드 `foms-stage-badge` 가 CS 주문에 `AS`. 범위 밖·재현됨.

## 시나리오 C3 — 모바일 큐 카드 단계별 액션 표 (홈 `/erp/dashboard`, iPhone UA, v2)

| 단계 | ADMIN 카드 | 페르소나(담당 팀) 카드 | 요소 | 눌렀을 때(같은 API 호출) | PC 와 다른 점 |
|---|---|---|---|---|---|
| 접수 RECEIVED | 없음 | CS: 없음 | — | `POST /quest/approve {team:CS}` 200 → 실측 | PC 그리드는 [승인] 있음 (P1-2) |
| 실측 MEASURE | [실측 완료] | SALES(비담당): 없음 | `<button … erp-queue-card__quest-approve data-confirm="실측을 완료하고 도면 단계로 넘길까요?…">` | 200 `{"next_stage": "도면"}` → DRAWING | 같음 |
| 도면 DRAWING | [도면 창구] | 동일 | `<a … erp-queue-card__drawing-open href="/erp/drawing-workbench/4740">` (링크) | 도면 창구 이동; 승인 API 는 409 COMMAND_REQUIRED | PC 도 버튼 없음 |
| 고객컨펌 CONFIRM | [고객 컨펌 완료] | SALES 담당(4748): 없음 (P1-1) | `<button class="… erp-queue-card__quest-approve" data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요?…">` — **button 맞음** | 200 `{"auto_transitioned": true, "next_stage": "생산"}` → PRODUCTION | PC [승인] 동일 문구 |
| 생산 PRODUCTION | 없음(홈) / 생산 보드 카드 [제작 시작]·[제작 완료] | PRODUCTION: 동일 | `<button … data-action="startProduction">` | 200 run 발급 / 완료 → CONSTRUCTION | PC 에만 취소·수정 제작·완료 취소 |
| 시공 CONSTRUCTION | 없음(홈) / 시공 보드 카드 [시공 시작]·[완료 준비]·[시공 완료] | CONSTRUCTION 팀은 `/erp/dashboard`·`/erp/orders/<id>/mobile` 자체가 `/erp/shipment` 로 302(`foms/platform/http.py:267-283`), 시공 보드는 본인 배정 건만(`erp_mine_filter.py:37-40`) → 미배정 시드는 빈 보드 | `<button … data-action="startConstruction">` | start 200 attempt 발급, 재시작 409 ALREADY_STARTED, complete 200 → CS | PC 에만 없는 것 없음(시공 불가는 양쪽 다 없음) |
| CS | 없음 | CS: 없음 | — | `quest/approve {team:CS}` 200(단계 유지, next_stage "완료"); `cs/complete` 200 → COMPLETED | PC 그리드 [승인] 있음; 완료 버튼은 PC 에도 없음(#1) |

## 확인한 것(정상)
- C1: 4735 CONSTRUCTION — 시공팀 `construction/start` 200 `{"attempt_id": "a760db5f-…"}` → 시공 보드 '시공중'(PC `completeConstruction`, 모바일 [완료 준비]·[시공 완료]); 재시작 409 `ALREADY_STARTED`; 증빙(after 2·signature, `POST /attachments` + `construction/evidence`) 뒤 `construction/complete` 200 `{"new_status": "CS"}` → PC 행 `data-stage="CS"`, 시공 보드 '시공완료'(재 업로드·AS 접수). quest 게이트 없음(#6 재현).
- C2: UI 버튼 없음 확인(#1). 4737 CS quest OPEN → `cs/complete` 409 `{"code": "QUEST_INCOMPLETE", "missing_teams": ["CS"]}`(CS 팀·ADMIN 동일). 4736 CS 팀 승인 200 → `cs/complete` 200 `{"new_status": "COMPLETED"}` → `data-stage="COMPLETED"`. 4735 CS quest 없음 → 200 COMPLETED.
- C3: 위 표. 고객컨펌 카드는 `<button class="foms-btn foms-btn--primary foms-btn--sm erp-queue-card__quest-approve">` 이다.
- C4: 모바일에 없는 액션(수정 제작·제작 취소·완료 취소·시공 불가) — 범위 밖·재현됨(#12·#13).
- 약속 1~6 전부 OK(위 표).

## 막힌 것
- C5 아이폰 실기기: 기기 없음 → 미수행(추측 기록 안 함).
- `GET /api/orders/<id>/structured` 에 `erp_stage_code` 없음 → 대시보드 행 `data-stage` 로 대체.
- CONSTRUCTION 팀 계정은 `/erp/dashboard`·모바일 상세가 302 로 막히고 시공 보드가 본인 배정 건만 보여, 시공 보드 화면은 ADMIN(iPhone UA)로, 시공 API 는 시공 페르소나로 나눠 확인했다.

## 정리 목록
- 주문 soft delete(`POST /delete/<id>` 302): 4735, 4736, 4737, 4738, 4739, 4740, 4741, 4742, 4743, 4748 → `/erp/dashboard?q=CLAUDE-TEST-PERSONA-C` 행 0 확인.
- 계정 비활성(`POST /admin/users/edit/<id>` is_active 해제): 70 claude_persona_c_construction, 71 claude_persona_c_cs, 72 claude_persona_c_sales, 73 claude_persona_c_drawing, 74 claude_persona_c_production → `/admin/users` 전부 "비활성", 비활성 계정 로그인 200(302 아님) 확인.
- 남는 잔여물(허용): 삭제된 4735 의 첨부 2115·2116·2117(휴지통 주문 하위), 4741·4743 의 production run(삭제 주문 하위), append-only 감사 로그·이벤트.
- 로컬: 쿠키·페르소나 비밀번호 파일 삭제. `claude_master` 로그아웃 완료.
