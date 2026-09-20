# 고객 컨펌 → 생산 워크플로 정정 + 모바일 동기화 + 전체 파이프라인 검수 (초안 브리프, CEO 가 확정한다)

작성 2026-09-17 · 작업 트리 `C:\tmp\foms-s-confirm-flow`(브랜치 `session/confirm-flow`, base origin/deploy `0eb9e10a3`).
**`C:\DEV\FOMS` 는 313 커밋 뒤라 읽지도 편집하지도 않는다.** 이 문서는 초안이다. CEO 는 §5 계약을 확정하되
§7 소유권 경계와 §8 함정은 유지한다.

## 1. 운영 제보 (2026-09-17, 스크린샷 3장)

1. **고객컨펌 승인을 눌러도 '컨펌 완료' 같은 배지가 없다.** 퀘스트 칸이 그냥 "-" 가 된다.
2. **이다은 주문**: 고객컨펌 칸에 남아 있고 퀘스트 "-". 생산 탭에서는 제작대기에 [제작 시작] 버튼이 뜨는데
   누르면 `오류: 필수 승인이 완료되지 않아 전이할 수 없습니다.` — 화면은 허용, 서버는 거부.
3. 전체 프로세스를 실제 사용자 페르소나로 꼼꼼히 검수해 달라.
4. **모바일** `/erp/dashboard?q=임인경&focus_order=5177`: '고객 컨펌' 을 누르면 주문 상세로만 이동하고
   PC 처럼 승인이 안 된다. 모바일도 PC 와 같게.

## 2. 사용자 결정 (2026-09-17, 총괄이 물어 확정)

- **D1 고객 컨펌 승인 즉시 본공정 stage 를 `CONFIRM → PRODUCTION` 으로 옮긴다.** 프로세스 맵의 '생산' 숫자가
  실제 진행과 맞아야 한다.
- **D2 생산 보드 버킷 재정의**: 제작대기 = `PRODUCTION` 단계이면서 '제작 시작' 을 아직 안 누른 주문,
  제작중 = 누른 주문. '제작 시작' 은 더 이상 stage 전이가 아니라 **생산 run 시작**이다.
- **D3 이미 승인됐는데 CONFIRM 에 남은 운영 주문(이다은 류)은 데이터 이관 없이 코드로 푼다.** 운영 DB 조사 요청 없음.
- 권한·팀 규칙은 바꾸지 않는다(2026-09-13 정정 `resolve_required_approval_teams` 그대로).

## 3. 정찰로 확정한 원인 (경로:행은 이 트리 기준, 열어서 확인하라)

### 3.1 "승인 완료" 판정이 세 곳에서 다르다 (제보 1·2 의 뿌리)

| 판정자 | 위치 | 읽는 것 | 결과(이다은: 담당자 승인 완료·status COMPLETED) |
|---|---|---|---|
| 승인 라우트 | `foms/api/quest.py:328-354, 419-422` | CONFIRM/MEASURE 는 `approval_mode=assignee` → `assignee_approval` 기록, `status=COMPLETED` | 승인 성공 |
| ERP 대시보드 표시 | `foms/services/erp_quest_display.py:34, 70-83` `resolve_current_quest` | `ACTIVE_QUEST_STATUSES={OPEN,IN_PROGRESS}` 만 → COMPLETED 는 **None** | 퀘스트 칸 "-" (배지 코드 `dashboard_grid.html:106-110, 134-138` 은 도달 불가) |
| 생산 보드 표시 | `foms/services/production_dashboard_display.py:168-194` | `assignee_approval` 또는 `team_approvals[SALES]` | 제작 시작 버튼 노출 |
| 생산 API 게이트 | `foms/api/production/orders.py:377-399` `_stage_quest_block` → `foms/services/orders/erp_policy_quests.py:42-103` `check_quest_approvals_complete` | **`team_approvals` 만** — `approval_mode`/`assignee_approval`/`status=COMPLETED` 를 모른다 | `missing_teams=[CS,SALES]` → 409 |
| 전이 서비스 | `foms/services/orders/quest_transition_service.py:115-139` `_stage_quest_complete` | 두 모드 다 안다. quest 없으면 True | (참고용 정답에 가장 가깝다) |

같은 축의 다른 소비자: `foms/api/cs/complete.py:80-103` `_cs_quest_block` 도 `check_quest_approvals_complete` 를 쓴다.

### 3.2 모바일이 버튼 대신 링크를 주는 이유 (제보 4)

- `foms/services/orders/quest_approve_cta.py:24-31, 63-72`: `_QUEST_APPROVE_LABELS` 에 CONFIRM 이 없고
  `is_command_required_stage(CONFIRM)` 이 True → `approve_label=None`.
- 큐 카드 `templates/partials/shared/erp_mobile_queue_card_v2.html:249-260, 321-327`:
  `quest_actionable` 이 `approve_label` 을 요구 → 거짓 → `confirm_actionable` 분기가 **`<a href=상세>` 고객 컨펌** 을 그린다.
  `static/js/foms/erp-quest-approve.js:176` 은 `<A>` 를 일부러 건너뛴다.
- 모바일 상세 `templates/orders/partials/order_detail_mobile_v2.html:271-273, 123-131`: 같은 `approve_label` 게이트.
- PC 그리드 `templates/orders/partials/dashboard_grid.html:161-166`: `approve_label` 을 안 보고 `can_edit_erp or can_assignee_approve` 로 [승인] 을 그린다 → PC 만 된다.
- 라우트 `foms/api/quest.py:198` 은 `_COMMAND_REQUIRED_STAGES={DRAWING}` 으로 이미 CONFIRM 을 허용했는데(`:190-197` 운영 #5193 막다른 골목 기록),
  서비스 `quest_transition_service.py:77` 은 `{DRAWING, CONFIRM}` 그대로 → 표시 SSOT 가 옛 집합을 본다. `:201 _NO_AUTO_ADVANCE_STAGES={CONFIRM}`.

### 3.3 지금의 CONFIRM→PRODUCTION 구조 (D1·D2 가 바꾸는 것)

- `_STAGE_ADVANCE` (`quest_transition_service.py:71-74`) 에 CONFIRM 행이 없다. 승인은 제자리(`quest.py:446-447`), `blueprint.customer_confirmed` 기록(`:426-433`).
- 유일한 전이 = 생산 탭 제작 시작 `foms/api/production/orders.py:652-703` `transition_order(PRODUCTION_START, expected_from=CONFIRM → PRODUCTION)`
  + `_apply_start_side_effects:506-519` (history·보류 해제·**`ProductionRun` 행 발급** `_mint_current_production_run:437-452`, `models.py:399-445` `production_runs`, current run 은 주문당 최대 1개 partial unique).
- 생산 보드 버킷 = **SQL case on `Order.erp_stage_code`** `foms/services/production_read_model.py:76-86`: CONFIRM→제작대기, PRODUCTION→제작중, CONSTRUCTION→제작완료. 인덱스 스캔이 목적(perf-gate 대상).
- 생산 보드 소비자: `templates/production/partials/filters_grid.html:80-95`, `mobile_queue.html:44-51`, `tablet_kanban_body.html:26-28, 309-314`, `tablet_sheet.html:177-181`, `foms/web/production/dashboard.py:446,463`, KPI `production_read_model.py:113+`.
- 생산 다른 명령: complete(PRODUCTION→CONSTRUCTION `:709`), rework(CONSTRUCTION→PRODUCTION `:773`), cancel(PRODUCTION→CONFIRM `:895`, 보류 게이트 없음), uncomplete(CONSTRUCTION→PRODUCTION `:963`), hold(stage 무변경 `:1346`).
- 명령 레지스트리 `foms/services/orders/order_transition_service.py:183-211` + 생산 등록 `foms/api/production/orders.py:253-275`. `complete_confirm_quest` (`quest_transition_service.py:253-317`) 는 **호출자 0**.
- 프로세스 맵 카운트도 `erp_stage_code` (`foms/services/orders/dashboard_read_model.py:272-284`).

### 3.4 파이프라인 전체 지도 (페르소나 검수의 뼈대 — 정찰 원문은 `docs/plans/2026-09-17-pipeline-map-scout.md` 에 그대로 저장)

| # | 전이 | PC 액션 | 모바일 액션 | 엔드포인트 | 게이트 | 다음 quest 생성 |
|---|---|---|---|---|---|---|
| 1 | RECEIVED→MEASURE | 승인(팀) | 접수 확인 | `quest/approve` | 팀 승인 전원(CS) | **예**(유일) |
| 2 | MEASURE→DRAWING | 도면 전달(실측 보드)·승인 | 실측 완료 | `quest/approve` | 담당자 1인 | 아니오 |
| 3 | DRAWING→CONFIRM | 수령 확정 | 수령 확정 | `confirm-drawing-receipt` | drawing_status=TRANSFERRED | 아니오 (**엔진 우회 직접 쓰기** `erp_orders_draftsman.py:383-392`) |
| 4 | CONFIRM→PRODUCTION | 제작 시작(생산 탭) | 제작 시작 | `production/start` | 단계·보류·CONFIRM quest | 아니오 |
| 5 | PRODUCTION→CONSTRUCTION | 제작 완료 | 제작 완료 | `production/complete` | 단계·보류·PRODUCTION quest | 아니오 |
| 6 | CONSTRUCTION→CS | 시공 완료 | 시공 완료 | `construction/complete` | 증빙 게이트(기본 off) — **quest 게이트 없음** | 아니오 |
| 7 | CS→COMPLETED | **없음** | **없음** | `cs/complete` (UI 호출자 0) | quest·보류·AS | 종결 |

정찰이 적은 불일치 16건 중 이번 범위 밖(기록만): CS→COMPLETED UI 부재와 `field_update status=COMPLETED` 우회(게이트 무시),
CONSTRUCTION→CS quest 게이트 부재, DRAWING→CONFIRM 엔진 우회, `cs/confirm.py` 가 quest 를 안 닫는 것, `stage_badge_label` CS→"AS" 라벨 불일치,
`object.html:155` STAGE_LABELS 하드코딩, 모바일에 rework/cancel/uncomplete/시공불가 없음, 태블릿 실측 완료 버튼의 AS 열림 억제 부재.
**페르소나 검수자는 이 목록을 다시 세는 게 아니라 실제 화면·API 로 재현하고 P0/P1/P2 를 매긴다.**

## 4. 목표 (완료 기준)

- G1 고객 컨펌 승인(PC·모바일 큐 카드·모바일 상세 모두) → quest 종결 + `blueprint.customer_confirmed` + **stage PRODUCTION** 한 tx.
- G2 생산 보드: 제작대기 = PRODUCTION ∧ current run 없음, 제작중 = PRODUCTION ∧ current run 있음. 제작 시작 = run 발급(stage 무변경).
  **호환**: 승인은 됐는데 CONFIRM 에 남은 기존 주문은 제작대기에 보이고 제작 시작이 stage 도 함께 옮긴다(D3). 미승인 CONFIRM 주문은 '고객 컨펌 전'.
- G3 "승인 완료" 판정 SSOT 하나 — 라우트·표시·생산 게이트·CS 게이트·전이 서비스가 같은 함수를 쓴다. `approval_mode` 와 `status=COMPLETED` 를 안다.
- G4 ERP 대시보드 퀘스트 칸: 현 단계 quest 가 COMPLETED 면 "-" 대신 **완료 배지**(예: `고객 컨펌 완료`)를 그린다(PC 그리드·모바일 큐 카드·모바일 상세).
- G5 모바일 CONFIRM 액션 = PC 와 같은 승인 버튼(링크 아님), 같은 확인 문구, 같은 서버 판정.
- G6 `is_command_required_stage` 집합이 라우트와 같아진다(`{DRAWING}`). 옛 주석·템플릿 주석(`erp_mobile_queue_card_v2.html:246-248`, `quest_approve_cta.py:22`) 갱신.
- G7 페르소나 검수 보고서(원장) — 영업·CS·도면·생산·시공·관리자 6 페르소나가 dev 서버에서 파이프라인을 끝까지 밟는다.

## 5. 계약 초안 (CEO 가 확정 — 이름은 CEO 가 바꿔도 되지만 워커 브리프 전체에 일관되게)

### 5.1 판정 SSOT
`foms/services/orders/erp_policy_quests.py` `check_quest_approvals_complete(sd, stage)` 를 **모드 인지형으로 확장**(새 함수 만들지 말고 이 함수를 고친다 — 소비자 5곳이 이미 이걸 부른다):
- quest 매칭은 `_stage_aliases` 와 같은 별칭 집합(한글·코드 둘 다).
- `status == COMPLETED` → `(True, [])`.
- `approval_mode == assignee` → `assignee_approval.approved` 로 판정, missing 은 `[]` 또는 `["ASSIGNEE"]` 같은 고정 토큰(CEO 결정, 소비자 문구와 맞출 것).
- team 모드 → 기존 로직.
- quest 없음 → 기존대로 `(False, required_teams)`. (`_stage_quest_block` 의 "없으면 게이트 안 함" 은 그대로.)
`quest_transition_service._stage_quest_complete` 는 이 함수를 부르도록 바꿔 중복을 없앤다(동작 동일해야 `test_state_quest.py` green).

### 5.2 전이
- `quest_transition_service._STAGE_ADVANCE` 에 `"CONFIRM": ("CUSTOMER_CONFIRM", "CONFIRM", "PRODUCTION", False)` 추가.
  `order_transition_service.py:183-211` 레지스트리에 `CUSTOMER_CONFIRM`(from CONFIRM, to PRODUCTION, event `CUSTOMER_CONFIRMED`, effect `STAGE_NOTIFICATION`) 등록.
- `_COMMAND_REQUIRED_STAGES` → `{DRAWING}` (서비스·라우트 동일). `foms/api/quest.py:201 _NO_AUTO_ADVANCE_STAGES` 에서 CONFIRM 제거.
  `complete_confirm_quest` 어댑터는 삭제하거나 새 흐름의 실제 호출자로 만든다(죽은 코드로 남기지 마라).
- `PRODUCTION_START`: `expected_from` 이 CONFIRM 인 기존 등록을 **PRODUCTION→PRODUCTION run 시작**으로 바꿀지, 아니면 stage 무변경 명령을 새로 두고
  CONFIRM(승인 완료) 호환 경로만 옛 전이를 쓰게 할지 CEO 가 정한다. 어느 쪽이든 `api_production_start` 는
  (a) stage PRODUCTION ∧ current run 없음 → run 발급, (b) stage CONFIRM ∧ quest 완료 → 전이 + run 발급, (c) 그 밖 409.
- `PRODUCTION_CANCEL`(제작 취소): CEO 가 정한다 — run 종결(stage 유지, 제작대기로 복귀)이 D2 와 맞다. CONFIRM 으로 되돌리는 옛 동작을 남길 이유가 있으면 이유를 적어라.

### 5.3 생산 보드 버킷
`production_read_model.production_stage_bucket_expr()` 를 `erp_stage_code` + **`production_runs` EXISTS(is_current)** 로 바꾼다:
- CONFIRM → 제작대기(호환), PRODUCTION ∧ ¬run → 제작대기, PRODUCTION ∧ run → 제작중, CONSTRUCTION → 제작완료.
- 인덱스: `production_runs(order_id, is_current)` partial unique 가 이미 있다(`models.py:443`). JSONB 를 SQL 에서 읽지 마라.
- `production_dashboard_display._production_quest_sales_state` 는 5.1 SSOT 로 판정한다. 표시 규칙: CONFIRM ∧ 미승인 → '고객 컨펌 전', 그 외 제작대기 → [제작 시작].
- KPI/카운트(`empty_production_step_stats`·`fill_production_step_counts`·`_kpi_stage_label_from_erp_stage`)·태블릿 칸반·모바일 큐·시트가 같은 버킷을 쓰는지 전수 확인.

### 5.4 표시·CTA
- `quest_approve_cta._QUEST_APPROVE_LABELS["CONFIRM"] = "고객 컨펌 완료"`, `_QUEST_APPROVE_CONFIRM_HEADS["CONFIRM"] = "고객 컨펌을 완료하고 생산 단계로 넘길까요?"`.
- `erp_quest_display.resolve_current_quest`: 현 단계 quest 가 전부 COMPLETED 면 None 대신 **가장 최근 COMPLETED quest** 를 돌려주되 payload 에 `is_done: True` 를 붙인다(이름 CEO 결정).
  `tests/domains/test_erp_quest_display.py:22-51` 이 "stale COMPLETED 는 숨긴다" 를 못박고 있다 — 그 테스트가 지키려던 것(옛 단계의 낡은 quest)과 이번 것(현 단계의 완료 quest)을 구분해 테스트를 고쳐라.
- PC 그리드·모바일 큐 카드·모바일 상세: `is_done` 이면 `완료` 배지(문구 `{{ title }} 완료`), 승인 버튼 없음.
- 모바일 큐 카드 `confirm_actionable` 링크 분기 삭제 — CONFIRM 도 `quest_actionable` 로 인라인 승인. 모바일 상세 `can_approve_quest` 도 같은 라벨 게이트라 자연히 풀린다. `erp-quest-approve.js` 의 `auto_transitioned` 처리가 PRODUCTION 이동을 표시하는지 확인(다음 단계 라벨 `next_stage_label`).

### 5.5 테스트(필수)
- 판정 SSOT 진리표: (assignee 승인·미승인) × (team 전원·일부·없음) × (status OPEN/IN_PROGRESS/COMPLETED) × (한글/코드 stage) — 소비자 3곳(생산 start·CS complete·전이 서비스)이 같은 답.
- 이다은 재현: CONFIRM ∧ assignee 승인 ∧ COMPLETED ∧ `_NO_AUTO_ADVANCE` 시절 데이터 → 생산 보드 제작대기 + 제작 시작 200 + stage PRODUCTION + run 1개.
- 승인 → PRODUCTION E2E (PC 본문 `{}`·모바일 동일), `blueprint.customer_confirmed`, `auto_transitioned True`, `next_stage` 생산, DRAWING 은 여전히 409.
- 생산 보드 버킷 SQL: PRODUCTION ∧ run 유/무, CONFIRM 승인/미승인 4조합 + 카운트 일치.
- 모바일 큐 카드 CONFIRM 이 `<button class="erp-queue-card__quest-approve">` 이고 `<a ... confirm-open>` 이 없다. 완료 배지 3표면.
- 기존 계약: `test_state_quest.py`(CONFIRM standalone 거부 테스트는 **의미가 바뀐다** — 삭제가 아니라 새 계약으로 교체), `test_auth_quest_approve.py:142-169`(무전이 → 전이로 교체), `test_production_transition_guard_api.py`, `test_state_prod.py`, `test_erp_quest_display.py:264-281`.

## 6. 검증 명령 (통합 검증자가 전량, 파이프 없이 exit 직독)

```
cd C:/tmp/foms-s-confirm-flow && pwd
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_state_quest.py tests/domains/test_auth_quest_approve.py tests/domains/test_erp_quest_display.py tests/domains/test_production_transition_guard_api.py tests/domains/test_state_prod.py tests/domains/test_state_prod_actions.py tests/domains/test_state_const_cs.py tests/domains/test_erp_mobile_order_display.py tests/domains/test_measure_approval_teams.py tests/domains/test_measurement_drawing_transfer_cta.py tests/domains/test_measurement_drawing_transfer_button.py tests/domains/test_order_transition_service.py -q
python -m pytest tests/domains -q -x --timeout=600
python -m pytest tests/contracts tests/harness -q
node --check static/js/foms/erp-quest-approve.js
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1   # EXIT 0
```
파일 크기 래칫(500줄)·layer dependency 래칫·writer 인벤토리(`docs/harness/*_inventory.json` lineno)·AI_STATUS 4,000자 예산이 CI 에 있다.
새 테스트 파일은 500줄 아래로 쪼개고, 인벤토리는 스캐너 결과와 대조해 좁게 고친다.

## 7. 파일 소유권 (겹치면 안 된다)

| 워커 | 편집 허용 |
|---|---|
| W1 판정·전이 | `foms/services/orders/erp_policy_quests.py`, `foms/services/orders/quest_transition_service.py`, `foms/services/orders/order_transition_service.py`, `foms/api/quest.py`, `foms/services/orders/quest_approve_cta.py` |
| W2 생산 보드 | `foms/api/production/orders.py`, `foms/services/production_read_model.py`, `foms/services/production_dashboard_display.py`, `foms/web/production/dashboard.py`, `templates/production/partials/*` |
| W3 표시·모바일 | `foms/services/erp_quest_display.py`, `foms/services/erp_mobile_order_display.py`, `foms/services/orders/dashboard_dto.py`, `templates/orders/partials/dashboard_grid.html`, `templates/partials/shared/erp_mobile_queue_card_v2.html`, `templates/orders/partials/order_detail_mobile_v2.html`, `static/js/foms/erp-quest-approve.js`, `static/js/orders/dashboard/erp-dashboard-quest.js`, 관련 CSS 1개, 자산 핀 줄(템플릿 `layout_scripts.html` 의 해당 줄만) |
| W4 테스트 | `tests/domains/test_confirm_to_production_*.py`(신규, 파일당 500줄 미만), 그리고 §5.5 가 지목한 기존 테스트 파일들의 **바뀐 계약 부분만** |
| 통합 검증자 | 전부 + `docs/harness/*_inventory.json` |
| 페르소나 검수자 | **편집 금지**. 읽기·dev 서버·HTTP·pytest 만 |

공통 금지: git 명령, 소유권 밖 파일, CRLF 훼손, docs 를 읽는 테스트, jQuery, 인라인 스타일, 새 pip 패키지.
공통 첫 명령 `cd C:/tmp/foms-s-confirm-flow && pwd`. dev 서버가 필요하면 `PORT=5001 python run.py`(이 트리는 startup DDL 자동 생략) — 포트는 워커마다 다르게(5001 페르소나, 5002 통합).

## 8. 함정

1. 도면 파일 '도면 전달'(`drawing_status` 축)과 stage 축을 섞지 마라(2026-09-14 브리프 §7-1).
2. `check_quest_approvals_complete` 의 OPEN short-circuit(`:74-89`)은 "아무 팀도 승인 안 했으면 False" 를 위한 것 — 모드 확장 시 이 의미를 유지.
3. `resolve_current_quest` 는 매칭 quest 가 없을 때 템플릿으로 **합성**한다(`:85-90`). 합성 quest 는 저장하지 않는다 — 계속 그렇게.
4. 승인 라우트는 quest 가 없으면 lazy-create 한다(`quest.py:308-316`). 전이 뒤 `_append_next_stage_quest` 로 PRODUCTION quest 를 만들지 말라고 `make_next_quest=False` 를 둔 이유가 있는지(생산 quest 는 팀 승인 PRODUCTION, `_stage_quest_block(sd,"PRODUCTION")` 이 제작 완료를 막게 됨) CEO 가 판단하고 기록.
5. 생산 보드 SQL 은 perf-gate 대상. `production_runs` EXISTS 는 인덱스가 있지만 실측하라(`perf-gate` 스킬 또는 EXPLAIN). JSONB path 를 SQL case 에 넣으면 인덱스가 죽는다.
6. `PRODUCTION_CANCEL` 이 CONFIRM 으로 되돌리던 옛 동작은 이제 "컨펌을 다시 받는다" 는 뜻이 된다. 제작 취소 ≠ 컨펌 취소. 되돌리는 stage 를 정하면 `quest.status` 도 같이 정하라.
7. `stage_override`·`status` 라우트·`field_update` 는 stage 를 직접 쓴다 — 이번에 손대지 않는다(범위 밖). 단 이들이 PRODUCTION 으로 놓은 주문은 run 이 없으니 제작대기로 떨어진다 — 의도한 결과다.
8. 워커 4명이 같은 트리에서 동시에 편집한다. 워커 사이 인터페이스(함수 이름·payload 키·템플릿 변수)는 계약 §5 로만 통한다.
9. 로컬 게이트 개수(`Pytest subset (N targets)`)를 보고하라. 이 트리는 origin 기준이라 33타깃 안팎이어야 한다.
10. `docs/harness/foms_order_mutation_writer_inventory.json`·`foms_state_writer_inventory.json` 은 lineno 고정 — quest.py·production/orders.py 를 고치면 밀린다. 통합 검증자가 스캐너로 좁게 갱신.

## 9. 산출 원장

`docs/plans/2026-09-17-confirm-to-production-workflow-ledger.md` — 총괄이 쓴다. 페르소나 검수 보고는 `docs/plans/2026-09-17-pipeline-persona-audit.md` 에 검수자가 직접 쓴다(편집 허용 파일은 그 하나).
