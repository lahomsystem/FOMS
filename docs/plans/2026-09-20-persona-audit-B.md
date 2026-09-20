# 페르소나 검수 B — 도면·생산 (스테이징 실서버, 2026-09-20)

- 환경: `https://lahom-dev.up.railway.app`, deploy `0cb601e7b`(자산 핀 `?v=20260920a` 응답에서 확인). 운영 서버 미접속.
- 계정: `claude_master`(ADMIN, id 58) + 페르소나 `claude_persona_b_sales`(id 75, SALES/STAFF), `claude_persona_b_drawing`(id 76, DRAWING/STAFF), `claude_persona_b_production`(id 77, PRODUCTION/STAFF). 비밀번호는 어디에도 적지 않았다.
- 시드 주문(고객 `CLAUDE-TEST-PERSONA-B-*`, 연락처 010-0000-0000, SALES owner 75): #4744(B-1-DRAWING) · #4745(B-2-DAEUN) · #4746(B-3-PROD) · #4749(B-4-CONFIRMWAIT).
- 방법: `python requests`(Chrome desktop UA / iPhone UA, `X-CSRF-Token`+Origin/Referer). 화면 판정은 실제 HTML 응답의 `data-order-id` 행·카드 블록 안에서만 했다. 모바일 v2 큐 카드는 `claude_master` 가 v3 코호트라 쿠키 `foms_shell_pref=v2` 로 v2 셸을 켜서 봤다(v3 는 별도 관찰 §P2).
- 증빙: `docs/harness/evidence/persona-B-http-log.txt`(응답 코드·본문 원문 134줄), `persona-B-counts.json`(B7 표 원자료), `persona-B-4749-prod-grid-confirm-wait.html`, `persona-B-4749-erp-grid-daeun-done-badge.html`, `persona-B-4749-prod-mobile-card-daeun.html`, `persona-B-4746-erp-grid-confirm-button.html`, `persona-B-4746-v3-timeline-fragment.html`.
- 편집 없음(코드·템플릿·테스트). git 미사용.

## 결함

### P0 CONFIRM 인데 quest 가 한 번도 안 만들어진 주문은 [제작 시작] API 가 고객 컨펌 없이 200 → PRODUCTION
- 페르소나/계정/화면: `claude_persona_b_production`(PRODUCTION/STAFF) · `POST /api/orders/4744/production/start` · 생산 보드 제작대기 칸.
- 재현 절차:
  1. #4744 를 DRAWING 으로 두고 도면 담당자 지정 → 도면 전달(`transfer-drawing` 200, `drawing_status=TRANSFERRED`) → 관리자 수령 확정(`confirm-drawing-receipt` 200 `new_stage:"CONFIRM"`). 이 시점 `quests` 는 `RECEIVED` 하나뿐(고객컨펌 quest 없음, `blueprint` 없음).
  2. 생산 보드는 #4744/#4749 같은 주문을 제작대기 + `고객 컨펌 전` 배지(버튼 없음)로 보여 준다 — PC 그리드 `<span class="badge bg-secondary erp-grid-badge-sm">고객 컨펌 전</span>`, 칸반 칩, 시트 `data-tablet-sheet-muted`, 모바일 v2 카드 `foms-production-status`(evidence `persona-B-4749-prod-grid-confirm-wait.html`).
  3. 생산팀 계정으로 `POST /api/orders/4744/production/start {}`.
- 기대 / 실제: 기대 409(고객 컨펌 전). 실제 `HTTP 200 {"message":"제작이 시작되었습니다.","new_status":"PRODUCTION","success":true}` → `workflow.stage=PRODUCTION`, history `('PRODUCTION','제작 시작')`, 제작중 버킷 진입, `blueprint.customer_confirmed` 없음. 화면이 숨긴 버튼을 서버가 받는다(고객 컨펌 없는 단계 전이).
- 근거 경로:행: `foms/api/production/orders.py:730-736`(CONFIRM 호환 경로 → `_stage_quest_block`), `:375-398`(quest 가 없으면 None = 통과), 원장 `2026-09-17-confirm-to-production-workflow-ledger.md` §6 "CONFIRM 인데 quest 가 아예 없는 주문: 화면 '고객 컨펌 전', API start 는 200(계약 C8)".
- 범위 판정: 범위 밖·재현됨(지도 #5). 계약 C8 이 의도적으로 남긴 구멍이라 등급만 적는다. 수령 확정 직후의 모든 주문이 이 상태이므로(quest 는 GET/approve 로만 생김, 지도 #4) 결정이 필요하다.

### P1 `POST /api/orders/<id>/quest` · `PUT /api/orders/<id>/quest/status` 가 200 success 를 주지만 저장되지 않는다
- 페르소나/계정/화면: `claude_master`(ADMIN) · API 직접 호출(브리프의 이다은 재현 경로).
- 재현 절차:
  1. #4745 를 stage-override 로 CONFIRM 에 둔 뒤 `POST /api/orders/4745/quest {"stage":"CONFIRM"}` → `HTTP 200 {"success": true}`.
  2. `PUT /api/orders/4745/quest/status {"status":"COMPLETED"}` → `HTTP 404 {"success": false, "message": "Quest를 찾을 수 없습니다."}`.
  3. `GET /api/orders/4745/structured` → `quests=[('RECEIVED','OPEN')]` — 1 의 quest 가 없다.
  4. 대조군: #4749(RECEIVED quest 존재) 에 `PUT /quest/status {"status":"IN_PROGRESS"}` → `HTTP 200 {"success": true}`, 직후 structured 의 quest status 는 그대로 `OPEN`.
- 기대 / 실제: 기대 quest 생성·상태 변경이 저장됨. 실제 두 라우트 모두 `order.structured_data = sd`(같은 dict 객체 재대입)만 하고 `flag_modified` 가 없어 JSONB 변경이 커밋에 실리지 않는다(같은 파일의 approve 라우트 `:465-466` 은 `flag_modified` 를 부른다). 이 때문에 브리프가 지정한 이다은 재현 경로(`PUT /quest/status`)가 스테이징에서 불가능했고, 원장 §6 의 "PUT /quest/status 로 STAFF 가 COMPLETED 를 수동으로 찍으면 게이트 통과" 위험 기술은 실제로는 성립하지 않는다(찍어도 저장이 안 된다).
- 근거 경로:행: `foms/api/quest.py:170-174`(POST), `:575-580`(PUT), 대조 `:465-466`; `models.py:89`(`structured_data = Column(JSONColumn)` — Mutable 아님); CLAUDE.md 규약 "deepcopy → 수정 → 재대입 → flag_modified".
- 범위 판정: 범위 밖(이번 배포가 만든 결함은 아니고 지도 16건에도 없음). 단, 이번 배포 원장이 이 라우트를 전제로 위험을 적고 있어 함께 정정이 필요하다.

### P2 생산 보드 이벤트 4종의 타임라인 라벨이 "기타 변경"이다
- 페르소나/계정/화면: `GET /api/orders/4746/events` 의 `event_label`, 모바일 상세 타임라인.
- 재현 절차: #4746 에서 보류 → 제작 시작(release) → 제작 완료 → 완료 취소 → 수정 제작 뒤 events 조회.
- 기대 / 실제: 기대 사람이 읽는 라벨. 실제 `('PRODUCTION_REWORK_STARTED','기타 변경')`, `('PRODUCTION_COMPLETE_REVERTED','기타 변경')`, `('PRODUCTION_HOLD_TOGGLED','기타 변경')`, `('ORDER_HELD','기타 변경')`, `('STAGE_OVERRIDE','기타 변경')`. 약속 6 의 두 라벨(`CUSTOMER_CONFIRMED`→"고객 컨펌 완료", `PRODUCTION_CANCELLED`→"제작 취소")은 정상.
- 근거 경로:행: `foms/services/order_event_display.py:120-150`(라벨 표에 위 4종 없음).
- 범위 판정: 범위 밖(이번 배포는 2종만 약속).

### P2 v3 "주문 진행 · 360°" 패널은 STAGE_CHANGED 만 읽어 고객컨펌·생산을 "기록 없음"으로 그린다
- 페르소나/계정/화면: `claude_master` · `GET /api/foms/fragment/order/4746/timeline`(v3 셸 타임라인 버튼).
- 재현 절차: #4746 이 CONFIRM 승인 → PRODUCTION → 제작 취소/시작/완료/완료취소/수정제작을 모두 거친 뒤 조회.
- 기대 / 실제: 기대 고객컨펌·생산에 도달 기록. 실제 텍스트 `고객컨펌 | 기록 없음 | … | 생산 | 기록 없음`(현재 단계는 "현재 생산" 으로 맞게 표기). 이 주문의 이벤트에는 `STAGE_CHANGED` 가 하나도 없고 `CUSTOMER_CONFIRMED`·`PRODUCTION_STARTED`·`STAGE_OVERRIDE` 뿐이다(evidence `persona-B-4746-v3-timeline-fragment.html`).
- 근거 경로:행: `foms/services/order_timeline_v3.py:83-90`(`event_type != "STAGE_CHANGED"` 이면 무시), `foms/api/fragment.py:130-160`.
- 범위 판정: 범위 밖(배포 전에도 PRODUCTION_START 가 같은 식이었다). 새 명령 `CUSTOMER_CONFIRM` 의 이벤트도 같은 사각지대에 들어간다.

### P2 ERP 대시보드 그리드가 PRODUCTION 단계 주문에 [승인](team=PRODUCTION) 버튼을 남겨 생산 quest 를 만든다
- 페르소나/계정/화면: `claude_master` 데스크톱 `/erp/dashboard` 행 #4746·#4745(단계 PRODUCTION) / `claude_persona_b_production` 로 API.
- 재현 절차: 승인으로 PRODUCTION 이 된 #4745 의 그리드 행에 `<button class="… erp-btn-approve-team" data-team="PRODUCTION" data-confirm="생산 확인을 기록할까요? 단계는 '생산' 그대로 유지됩니다. …">승인</button>` 이 있다. 생산팀 계정으로 `POST /quest/approve {"team":"PRODUCTION"}` → `200 {"all_approved": true, "auto_transitioned": false, "next_stage": "시공"}` → `quests` 에 `('생산','COMPLETED', team_approvals.PRODUCTION)` 가 생긴다. 이어서 `production/complete` → 200(잠기지 않음).
- 기대 / 실제: 원장 §6 "승인 뒤 PRODUCTION quest 를 일부러 만들지 않는다(만들면 제작 완료가 생산팀 승인 뒤로 잠긴다)" 와 화면이 어긋난다. 실측에서는 생산팀이 누르면 곧바로 COMPLETED 라 잠금은 안 됐고, CS/SALES 가 누르면 403(권한) 이다. 문구·의도 정리만 필요.
- 근거 경로:행: `templates/orders/partials/dashboard_grid.html:82-95`, `foms/api/quest.py:330`(`team` 이 오면 `ALREADY_TRANSITIONED` 가드 건너뜀).
- 범위 판정: 범위 밖(기존 범용 승인 패널).

### P2 v3 모바일 셸(코호트 기본)에서는 생산 큐 카드가 상세 링크뿐이고, 모바일 상세에도 [제작 시작]/[제작 완료] 가 없다
- 페르소나/계정/화면: `claude_master` iPhone UA(쿠키 없음 = v3) `/erp/production/dashboard`, `/erp/orders/4746/mobile`.
- 재현 절차: v3 응답에는 `fos-queue-card`(링크, `persona_home_production.html:34`) 만 있고 `startProduction`/`completeProduction` 마크업이 없다. 모바일 상세(v3·v2 모두)도 `production/start`·`제작 시작`·`제작 완료` 문자열 0. v2 셸(쿠키 `foms_shell_pref=v2`)의 큐 카드에는 버튼이 있다(`data-action="startProduction"`, `completeProduction`).
- 기대 / 실제: 생산팀이 v3 셸 휴대폰만 쓰면 제작 시작·완료를 누를 곳이 없다(PC·태블릿·v2 셸에서만 가능).
- 근거 경로:행: `templates/partials/v3/persona_home_production.html:30-80`, `templates/production/partials/dashboard_body.html:131-140`(`shell_variant != 'v3'` 게이트), `foms/services/feature_flags.py:257-300`.
- 범위 판정: 범위 밖(지도 #12 는 v2 큐 기준). 코호트 범위에 따라 등급 재판정 필요.

### P2 주문의 SALES owner(`sales_owner_id`) 는 도면 수령 확정을 못 한다
- 페르소나/계정/화면: `claude_persona_b_sales`(id 75, #4744 의 sales_owner) · `POST /api/orders/4744/confirm-drawing-receipt`.
- 기대 / 실제: 기대 영업 담당이 수령 확정. 실제 `HTTP 403 {"success": false, "message": "도면 수령 확인은 지정된 영업 담당자만 가능합니다."}` — owner 와 SALES_DOMAIN assignee 가 다른 축이다. 관리자로만 진행했다.
- 근거 경로:행: `foms/api/drawing/erp_orders_draftsman.py:346-380`.
- 범위 판정: 범위 밖(기존 권한 축). 관찰 기록.

## 확인한 것(정상) — 시나리오 번호

- B1 DRAWING→CONFIRM: #4744·#4749 둘 다 담당자 지정 → 도면팀 페르소나 `transfer-drawing` 200("확정 대기 상태") → `drawing_status=TRANSFERRED` → 관리자 `confirm-drawing-receipt` 200 `new_stage:"CONFIRM"`. 생산 보드 제작대기에 '고객 컨펌 전'(PC 그리드·칸반 칩·시트 muted·모바일 v2 배지, 버튼 없음). 약속 5: DRAWING 단계 승인 `409 {"code":"COMMAND_REQUIRED"}`; CONFIRM 에서 DRAWING 팀 승인 `403 "현재 단계 승인 권한이 없는 팀입니다."`, PRODUCTION 팀 승인 `403`(같은 문구); DRAWING 팀 `production/start` `403 FORBIDDEN`. 403 뒤 quest 가 남지 않음(#4744 quests 불변).
- B2 이다은 재현(#4749, #4745 동일): 브리프의 PUT 경로가 불가(P1)해서 관리자 승인(→PRODUCTION, `고객컨펌` COMPLETED·assignee approved·blueprint) 뒤 stage-override 로 CONFIRM 복귀. 결과 dict 는 계약 C9 와 같고 `workflow.history` 에 PRODUCTION 항목이 하나 더 있다(그래서 보드 판정은 `production_dashboard_display.py:180-186` 의 history 분기를 탄다 — C9 의 quest 분기와 다른 가지). 화면: ERP PC 그리드 `data-stage="CONFIRM"` + `<span class="badge bg-success erp-quest-done">고객 컨펌 완료</span>`, 승인 버튼 0(evidence `persona-B-4749-erp-grid-daeun-done-badge.html`); 모바일 상세 `erp-quest-done` "고객 컨펌 완료", `erp-mobile-quest-approve` 0. 생산 보드: PC 그리드 제작대기 + `data-action="startProduction"` 버튼, 칸반 `data-kanban-action="start"`, 시트 `production-start`, 모바일 v2 카드 `startProduction`. 생산팀 `production/start` → `200 {"new_status":"PRODUCTION"}`(호환 경로, `run_started` 키 없음) → `workflow.stage=PRODUCTION`, history `('PRODUCTION','제작 시작')`, PC 그리드 제작중 + '생산 중' 배지. 스탯 스트립 제작대기 1→0·제작중 2→3, ERP 프로세스 맵 고객컨펌 1→0·생산 2→3. API 경로 (b) 는 `_stage_quest_block` 을 COMPLETED quest 로 통과했다.
- B3 승인→PRODUCTION(#4746): PC 그리드 CONFIRM 행 `erp-btn-approve-assignee` + `data-confirm="고객 컨펌을 완료하고 생산 단계로 넘길까요?\n\nCLAUDE-TEST-PERSONA-B-3-PROD / #4746"`(약속 1, evidence `persona-B-4746-erp-grid-confirm-button.html`). 관리자 승인 `200 {"all_approved": true, "auto_transitioned": true, "next_stage": "생산", "missing_teams": []}` → stage PRODUCTION, `blueprint={"customer_confirmed": true, "confirmed_by": "claude_master", …}`. 재요청 `409 {"code":"ALREADY_TRANSITIONED","message":"이미 생산 단계로 넘어간 주문입니다. 화면을 새로고침하세요."}`, quests 불변(생산 quest 없음)(약속 2). 보드 제작대기(run 없음) + [제작 시작] 4면 모두. 생산팀 start → `200 {"new_status":"PRODUCTION","run_started":true}` → 제작중(제작대기 1→0, 제작중 2→3 — 4 소스 동일). 다시 start `409 {"code":"INVALID_STAGE","message":"이미 제작중인 주문입니다."}`; 제작중 UI 에 시작 버튼 없음(칸반 complete 만, 시트 cancel+complete, 모바일 completeProduction, PC '생산 중').
- B4 제작 취소(#4746): `200 {"message":"제작을 취소했습니다. (제작대기 복귀)","new_status":"PRODUCTION"}` → stage PRODUCTION 유지, history `('PRODUCTION','제작 취소 (제작대기 복귀) — 페르소나B 취소 검수')`, 4 소스 모두 제작대기(1/2/0), 행 배지는 단계뿐(보류·재제작 없음), [제작 시작] 재노출. run SUPERSEDED 는 DB 를 안 봐서 직접 확인 못 했고 버킷 복귀로 간접 확인. 재취소 `409 "제작 시작 전 주문은 취소할 수 없습니다."`. 타임라인 `PRODUCTION_CANCELLED`→"제작 취소"(약속 6).
- B5(#4746): complete `200 {"new_status":"CONSTRUCTION"}` → 제작완료(칸반 rework, 시트 uncomplete+rework, 모바일 '제작 완료' 배지, 카운트 0/2/1); uncomplete `200 {"new_status":"PRODUCTION"}` → 제작중(run 재개, 카운트 0/3/0); complete 재실행 200; rework `200 {"message":"수정 제작을 시작했습니다.","new_status":"PRODUCTION"}` → 제작중, `production.rework={"active": true, "count": 1, "reason": "페르소나B 수정 제작"}`.
- B6(#4746 제작대기에서): hold on `200 data.hold.active=true` → start `409 {"code":"HOLD_ACTIVE","hold":{…"reason":"페르소나B 보류"},"message":"보류 중인 주문입니다. (사유: 페르소나B 보류)"}` → start `{"release_hold": true}` `200 run_started:true`, `production.hold.active=false`. 보류 중 칸반은 이동 버튼을 숨기고 시트·모바일은 [제작 시작] 을 둔다(JS 가 HOLD_ACTIVE 를 확인창으로 처리, `tablet-domain-sheets.js:70-96`).
- B7 숫자 대조(`q=CLAUDE-TEST-PERSONA-B`, 시점별; `persona-B-counts.json`):

| 시점 | 프로세스 맵(PC) 대기/중 | 칸반 열(start/complete/rework 버튼) | PC 필터 행 대기/중/완료 | 모바일 스탯 스트립 | 모바일 칩 전체/대기/중 |
|---|---|---|---|---|---|
| O2 시작 전 | 2/1 | 2/1/0 | [4745,4746]/[4744]/[] | 2/1/0 | 3/2/1 |
| O2 시작 후 | 1/2 | 1/2/0 | [4746]/[4744,4745]/[] | 1/2/0 | 3/1/2 |
| O3 시작 후 | 0/3 | 0/3/0 | []/[4744,4745,4746]/[] | 0/3/0 | 3/0/3 |
| O3 취소 후 | 1/2 | 1/2/0 | [4746]/[4744,4745]/[] | 1/2/0 | 3/1/2 |
| O3 완료 후 | 0/2 | 0/2/1 | []/[4744,4745]/[4746] | 0/2/1 | 3/0/2 |
| O3 수정제작 후 | 0/3 | 0/3/0 | []/[4744,4745,4746]/[] | 0/3/0 | 3/0/3 |

  모든 시점에서 5 소스가 일치. 모바일 칩에는 제작완료 칩이 없고(전체·대기·중만) 스탯 스트립에는 있다 — 설계대로.
- 약속 6: `GET /api/orders/4746/events` 에 `('CUSTOMER_CONFIRMED','고객 컨펌 완료')`, `('PRODUCTION_CANCELLED','제작 취소')`; 모바일 상세 `foms-timeline-item` 에 "고객 컨펌 완료"·"제작 취소" 표기.
- 약속 3 의 "제작대기 = CONFIRM(호환) 또는 PRODUCTION∧run 없음" 은 #4749(CONFIRM)·#4746(PRODUCTION 취소 후)·#4746(승인 직후) 세 경우로 확인.

## 정리 목록

- 주문 soft delete(`POST /delete/<id>` 302): #4744, #4745, #4746, #4749 — 이후 ERP·생산 대시보드 `q=CLAUDE-TEST-PERSONA-B` 행 0, `GET /structured` success=false.
- 계정 비활성화(`POST /admin/users/edit/<id>` is_active 해제, 302): 75 `claude_persona_b_sales`, 76 `claude_persona_b_drawing`, 77 `claude_persona_b_production` — 로그인 시도 200(비활성 flash) 확인.
- 남는 것(허용 잔여물): R2 `orders/4744/drawing_gateway/revisions/20260920_052500_3a7e1408_persona_b_drawing.png` 와 `orders/4749/drawing_gateway/revisions/*persona_b4.png`(각 1px PNG), OrderEvent·SecurityLog·감사 행, `production_runs` 행(삭제 주문 소속). 정리 못 한 것 없음.
