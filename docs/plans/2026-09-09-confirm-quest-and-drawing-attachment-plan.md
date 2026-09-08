# 고객컨펌 승인 불가 + 수령확정 도면 미저장 — 수정 계획·진행 원장

- 작성: 2026-09-09 / 세션 워크트리 `c:\tmp\foms-s-confirmfix` (branch `session/confirmfix`)
- 사용자 승인: 두 건 모두 근본 수정 방향 승인 (T1 = 빠진 단계 채우기, T2 = 전달 시 첨부로 남기기)

## 배경 (실측 근거)

### 문제 1 — 고객컨펌 단계에서 퀘스트 승인이 항상 409
운영 주문 #5193 에서 `POST /api/orders/5193/quest/approve` → 409 `COMMAND_REQUIRED`.

- 가드: `foms/api/quest.py:187` `_COMMAND_REQUIRED_STAGES = {"DRAWING","CONFIRM"}`, 거부는 `:364`.
- 가드가 지목하는 전용 command `CUSTOMER_CONFIRM` 은 **레지스트리에 없다**. 실제 등록 command 18종
  (`REQUEST_MEASUREMENT`·`COMPLETE_MEASUREMENT`·`PRODUCTION_*`·`AS_*`·`CS_COMPLETE`·`SET_MAIN_STAGE`…)
  중 `CUSTOMER_CONFIRM` 없음 — 이름은 docstring 에만 존재.
- 어댑터 `complete_confirm_quest`(`foms/services/orders/quest_transition_service.py:231`) 의
  프로덕션 호출자 0건(테스트 `tests/domains/test_state_quest.py:217` 만).
- 기존 라우트 `POST /api/orders/<id>/confirm/customer`(`foms/api/cs/confirm.py:24`) 는
  화면 호출자 0건이고 `blueprint.customer_confirmed` 만 세울 뿐 **quest 를 닫지 않는다**.
- 파급: 생산 시작이 CONFIRM quest 완료를 요구(`foms/api/production/orders.py:685`) → 승인도 못 하고
  생산으로도 못 넘어간다(단계 강제 변경 우회만 가능).
- 가드는 2026-07-26 `2391174c0`(AUTH-QUEST-01)·`9b8a3f79b`(STATE-QUEST-01) 로 어댑터와 함께 들어왔고,
  어댑터를 호출할 command/UI 가 끝내 안 들어왔다.

### 문제 2 — 수령확정 후에도 ERP 주문 '도면' 탭이 비어 있다
- 주문 첨부 '도면' 탭의 정본 = `OrderAttachment(category='drawing')` 행
  (`foms/api/files/order_routes.py:239`, 클라이언트 `static/js/orders/dashboard/erp-dashboard-attachments.js`).
- 도면 경로 전체에 **그 행을 만드는 INSERT 가 없다**. 전달은 기존 행의 category 를 바꾸는 UPDATE 뿐
  (`foms/api/drawing/erp_orders_drawing.py:183-189`).
- 도면 마법사 산출물은 `orders/<id>/drawing_wizard/exports/` 키만 있고 첨부 행이 없다
  (`foms/api/drawing/wizard.py:883` — 저장/전달 분리 `dc81a5658` 이후 의도적 미생성)
  → UPDATE 대상 0건 → 탭 영구 공백.
- 수령확정(`foms/api/drawing/erp_orders_draftsman.py:314`)은 `structured_data` 만 쓰고,
  정리 로직(`foms/services/drawing_confirm_cleanup.py:270-284`)은 keep 목록 밖 `drawing` 첨부 행과
  R2 파일을 **삭제**한다.

## 작업 (progress ledger)

| # | 작업 | 상태 | 완료 기준 |
|---|---|---|---|
| T1 | 고객컨펌 완료 경로 구현 | DONE | CONFIRM 단계에서 승인 요청이 200 + CONFIRM quest `status=COMPLETED` + `blueprint.customer_confirmed=True`, stage 는 CONFIRM 유지(전이 없음). DRAWING 은 409 유지 |
| T2 | 전달 시 도면 첨부 행 생성 | DONE | 마법사 도면 전달 후 `GET /api/orders/<id>/attachments?category=drawing` 이 전달 파일을 반환. 수령확정 뒤에도 동일(정리 로직이 안 지움) |
| T3 | 계약 테스트 갱신·추가 | DONE | T1/T2 회귀 테스트 red→green, 기존 DRAWING 409 계약 유지 |
| T4 | dev 서버 검증 | DONE | 고객컨펌 승인 성공 토스트 + 도면 탭에 파일 표시(스크린샷) |
| T5 | deploy 반영·CI 전수 green | PENDING | 4개 워크플로 나열 확인 |

## 설계 결정

**T1**: `_COMMAND_REQUIRED_STAGES` 의 취지는 "standalone 승인이 **stage 를 전이시키면 안 된다**"이다
(`quest_transition_service.py:195` 가 전이를 막는 층). CONFIRM 완료는 전이가 아니라 quest 종결이며
CONFIRM→PRODUCTION 은 여전히 `PRODUCTION_START` 소관이다. 따라서 quest approve 라우트가 CONFIRM 에서
어댑터(`complete_confirm_quest`) + `blueprint.customer_confirmed` 를 **같은 tx** 로 실행하도록 채운다.
DRAWING 은 전달/수령확정이 진짜 전용 경로이므로 409 를 그대로 둔다. 서버 한 곳만 고치면 대시보드·태블릿·
주문상세·모바일·object 뷰 등 8개 호출 표면이 전부 살아난다(클라 8곳 수정 불필요).

**T2**: 전달 시점에 `materialize_transfer_attachments` 결과(key·filename)로 행이 없는 키에 대해
`OrderAttachment(category='drawing')` 를 INSERT 한다. 정리 로직의 keep 목록은 전달 이력에서 재구성되므로
현재 전달 파일은 보존된다.

## 상태 로그

- 2026-09-09: 조사 완료, 계획 승인, 워크트리 생성.
- 2026-09-09 T1 DONE: `foms/api/quest.py` — 라우트 가드를 DRAWING 전용으로 좁히고(`_COMMAND_REQUIRED_STAGES`),
  CONFIRM 최종 승인 시 `blueprint.customer_confirmed` 를 같은 tx 로 기록, 자동 전이는 건너뛴다
  (`_NO_AUTO_ADVANCE_STAGES`). 서비스 층 전이 거부는 그대로. 계약 테스트 교체:
  `test_confirm_approval_completes_quest_without_stage_transition`(DRAWING 409 는 유지).
- 2026-09-09 T2 DONE: `foms/api/drawing/erp_orders_drawing.py` — 전달 시 첨부 행이 없는 도면 key 에
  `OrderAttachment(category='drawing')` INSERT(파일명·확장자 판정·업로더 기록). 신규 테스트
  `tests/domains/test_drawing_transfer_attachments.py` 3건.
- 검증: APP_OK, tests/domains -k "quest or confirm or production or state" 715 passed,
  -k drawing 425 passed, 네임스페이스 계약 179 passed.
- 2026-09-09 T4 DONE: dev 서버(5001)+실제 PostgreSQL HTTP E2E.
  ① 고객컨펌 승인 200 → quest `COMPLETED`·`assignee_approval.approved=True`·
     `blueprint.customer_confirmed=True`·stage 는 `CONFIRM` 유지(전이 없음).
  ② 도면 전달 200 → `GET /attachments?category=drawing` 에 파일 등장(file_type=image),
     **수령확정 뒤에도 첨부 행 유지**(정리 로직이 안 지움), `drawing_status=CONFIRMED`.
  seed 주문은 로컬 dev DB 전용(`CLAUDE-TEST-` 접두 2건).
- 2026-09-09: REV-99 writer 인벤토리는 lineno 이동분만 재생성(신규 writer 0건).
