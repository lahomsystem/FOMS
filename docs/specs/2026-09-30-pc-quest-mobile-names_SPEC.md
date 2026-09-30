# PC 퀘스트 이름을 휴대폰 이름으로 — Spec (2026-09-30)

- 상태: **1단계 운영 반영(PR #468) · 2단계 구현(2026-09-30)** · 3단계 승인 대기
- 근거: 검토 보고서 `docs/plans/2026-09-30-pc-quest-mobile-process-names-review.md`(§7 사용자 결정), 목업 v2 https://claude.ai/artifact/Pxd7cWsqa42ZjfQi5z3VBH
- 기준 HEAD: `c19afa6ad` (deploy)

## 1. 목적

PC 주문 대시보드의 퀘스트 이름과 버튼 이름이 원시 legacy 템플릿 문구("주문 정보 확인", "CS/AS 접수 및 처리", 모든 단계 "승인")로 남아 있다. 휴대폰과 같은 이름으로 맞추고, 버튼은 누르면 일어나는 일을 말하게 한다.

## 2. 사용자 결정 (2026-09-30)

1. 퀘스트 제목 = 휴대폰 이름표 그대로: 접수 확인 · 실측 완료 · 고객 컨펌 완료 · CS 확인 · AS 확인.
2. 다음 단계로 넘기는 버튼 = "{다음 단계} 단계로 넘기기". PC 와 휴대폰, 실측 대시보드, 태블릿이 모두 같은 글자를 쓴다.
3. 팀 이름 = CS팀 · 영업팀 · 도면팀 · 생산팀 · 시공팀 · 출고팀.

## 3. 바꾸지 않는 것

- 단계 코드, `STAGE_LABELS`·`STAGE_NAME_TO_CODE`·`STAGE_SQL_FILTER_MAP`(저장값이자 필터 키, `foms/services/orders/erp_policy_constants.py:14-69`).
- 파이프라인 막대 9칸 이름과 `data-stage` 필터 키.
- DB 에 저장된 quest `title` — 이관하지 않는다. 감사 흔적으로 남긴다.
- 승인 API·전이 규칙·권한 판정. 확인창 문장(`_QUEST_APPROVE_CONFIRM_HEADS`).
- 클래스·ID 핀(`quest-collapse-*`, `quest-approvals-*`, `erp-btn-approve-*`, `erp-btn-retransition`, `erp-quest-done`).

## 4. 이름표 (정본)

| 단계 | 퀘스트 제목 | 버튼 | 끝난 뒤 배지 |
|---|---|---|---|
| RECEIVED | 접수 확인 | 실측 단계로 넘기기 | 접수 확인 완료 |
| MEASURE | 실측 완료 | 도면 단계로 넘기기 | 실측 완료 |
| CONFIRM | 고객 컨펌 완료 | 생산 단계로 넘기기 | 고객 컨펌 완료 |
| CS | CS 확인 | CS 확인 (기록만) | CS 확인 완료 |
| AS | AS 확인 | 없음 → "AS 화면 열기" 링크 (2단계) | — |
| DRAWING | (도면 창구 카드 유지) | 도면 창구 열기 | — |
| PRODUCTION | 제작대기 / 제작중 (2단계) | 생산 보드 열기 | — |
| CONSTRUCTION | 시공대기 / 시공중 (2단계) | 시공 보드 열기 | — |
| COMPLETED | 초록 "완료" 배지 하나 (2단계) | 없음 | — |

제목과 끝난 뒤 배지는 지금 `_QUEST_TASK_LABELS`·`_done_label` 그대로다(`foms/services/orders/quest_approve_cta.py:24-46`). 새로 생기는 것은 넘기기 버튼 글자뿐이다.

## 5. 설계

### 1단계 — 이름 (한 PR)

**A. 서버 이름표** — `foms/services/orders/quest_approve_cta.py` `build_approve_cta`
- 새 키 `task_label` = `_QUEST_TASK_LABELS[stage_code]` (없으면 None).
- `approve_label` = 단계를 넘기면 `f"{next_stage_label} 단계로 넘기기"`, 기록만 하면 `task_label`. command 단계(DRAWING)는 지금처럼 None.
- `retransition_label` = `approve_label` 그대로(2026-09-23 "재전이 버튼 = 승인 버튼과 같은 이름" 규칙 유지 — 이제 둘 다 "도면 단계로 넘기기").
- `done_label` = 지금처럼 `_done_label(task_label, stage_label)`.
- 코드 주석(:92-94)의 "따로 이름('도면 단계로 넘기기')을 두면 둘로 보인다" 문장을 새 규칙에 맞게 고친다.

**B. 제목 덮어쓰기** — 표시 계층에서만
- `foms/services/erp_quest_display.py:409` `build_current_quest_payload` 의 `title` = `cta["task_label"] or current_quest.get("title", "")`. 빈 문자열 금지(휴대폰 노출 조건이 title 이 비었는지 본다 — `order_detail_mobile_v2.html:128,263`, `erp_mobile_queue_card_v2.html:253`).
- `foms/api/quest.py:126-131` GET 응답의 `title` 도 같은 함수로 고른다.
- 저장된 title 이 옛 이름이어도 새 이름이 나온다(기존 주문 전부 한 번에 바뀜).

**C. PC 주문 그리드** — `templates/orders/partials/dashboard_grid.html`, `static/js/orders/dashboard/erp-dashboard-quest.js`
- 열 이름·부제·펼침 머리: "퀘스트" → "현재 작업", "주문 처리 및 퀘스트 관리" → "주문별 현재 작업", "현재 단계 퀘스트" → "현재 작업" (:14, :56, :134).
- 상태 배지 "진행중" → "할 일" (:118, :147). "완료"·`done_label` 은 그대로.
- 버튼 글자 "승인" → `approve_label` (담당자 :181, 팀 :207, JS 다시 그리기 :141-172).
- 소제목 "승인" → "담당" (:162).
- 안내 문구: "담당자 지정 필요" → "담당자를 먼저 정해 주세요", "(승인 권한 없음)" → "(담당자만 누를 수 있어요)".
- 토스트(JS :69-81, :117-126): "✅ 승인 완료 — X 단계로 이동" → "X 단계로 넘겼습니다", 남은 팀은 한글 팀 이름.
- 새 인라인 스타일 금지. 필요한 모양은 `static/css/foundation/erp-pro.css` 클래스로.

**D. 팀 이름 한 벌**
- 새 모듈 `foms/services/orders/team_labels.py` 에 `TEAM_LABELS`(CS→CS팀, SALES→영업팀, MEASURE→실측팀, DRAWING→도면팀, PRODUCTION→생산팀, CONSTRUCTION→시공팀, SHIPMENT→출고팀).
- 사본 교체: `foms/web/orders/dashboard.py:189`, `foms/web/construction/dashboard.py:64`, `foms/web/production/dashboard.py:84`, `foms/services/orders/order_event_display.py:25-33`("상담팀"), JS `erp-order-shared.js:6001-6011`.
- 위치-고정 계약 테스트 1개(사본이 다시 생기면 빨강).
- 필터 `<option>` 5곳의 라홈팀→CS팀 은 결정 3에 따라 함께 바꿨고 계약 테스트가 지킨다.

**E. 휴대폰**
- 하단 큰 버튼: `order_detail_mobile_v2.html:419` 의 ` → {next_stage_label} 전달` 꼬리를 뗀다(`approve_label` 이 이미 "도면 단계로 넘기기").
- 팀 버튼(:335-338): "{팀 코드} {이름}" → 버튼은 `approve_label` 만, 팀은 한글 이름으로 확인창에. "{팀} 승인완료"·"{팀} 대기" 배지도 한글 팀 이름.
- 큐 카드 버튼·상세 "현재 작업" 글자는 A·B 로 자동으로 바뀐다(템플릿 수정 없음).

**F. 실측 대시보드·태블릿**
- `foms/services/measurement/drawing_transfer_cta.py`: `DRAWING_TRANSFER_LABEL` "도면 전달" → "도면 단계로 넘기기". `TEAM_MODE_BLOCKED_REASON` → "이 주문은 주문 목록의 현재 작업 칸에서 '도면 단계로 넘기기'를 눌러 주세요."
- 태블릿 시트 `tablet_dashboard_sheet.html:24-94`: "다음 할 일 — {title} (승인: 팀)" → "현재 작업 — {title} ({팀})", 버튼 "퀘스트 승인" → `approve_label`.
- 실측 태블릿 하단 버튼(`tablet_split_body.html:160`, `tablet-measure-form.js` 상태 문구): "실측 완료 → 도면 전달" → "도면 단계로 넘기기".

**G. 도면·생산 글자**
- PC 도면 카드 버튼 "별도 작업실 열기" → "도면 창구 열기" (`dashboard_grid.html:320-322`).
- 도면 창구 막대 "수정요청"·"확정대기" → "수정 요청됨"·"확정 대기" (`templates/drawing/partials/workbench_dashboard_body.html:54,60` — 보이는 글자만. 필터 값은 `data-status` 영어 코드라 그대로다. title 속성 :52,58 도 같이).
- 생산 보드 칸 "생산 중" → "제작중" (`templates/production/partials/filters_grid.html:93`).

### 2단계 — 생산·시공·완료·AS 줄 모양 (별도 PR, 구간 계측 필수)

- 완료: 퀘스트 칸에 초록 "완료" 배지만. "진행중"·"(보드에서 진행)" 제거.
- 생산: "제작대기"/"제작중" 배지 + "생산 보드 열기". 제작중 판정은 생산 run 조회가 필요해(`production_dashboard_display.py:286-294`) 주문 대시보드 쿼리가 늘 수 있다 — 한 번에 모아 읽고 구간 계측으로 잰다.
- 시공: 지금 "-". "시공대기"/"시공중" 배지 + "시공 보드 열기"(`construction_dashboard_display.py:391-401` 판정 재사용).
- AS: 제목 "AS 확인" + "AS 화면 열기" 링크. "(보드에서 진행)" 제거.
- 시공·생산 보드 그리드의 퀘스트/진행중/팀별 승인/승인 글자(`construction/partials/filters_grid.html:12,117`, `production/partials/filters_grid.html:12,25,84`).
- 휴대폰 상세 "현재 작업" 칸이 이 단계들에서 어떻게 보이는지 실화면 확인(합성 quest 를 없애면 칸이 사라진다 — `erp_quest_display.py:96-101`).

### 3단계 — 정리 (별도 PR)

- `data/erp_quest_templates.json` 의 title 을 이름표와 맞추고 쓰지 않는 필드(process_flow 등) 정리. `data/erp_task_templates.json` 이름·담당 팀 맞춤.
- 죽은 복제본·표면 삭제: `scripts/ops/erp_build_step_runner.py:597-626`, `templates/orders/object.html` 퀘스트 칸, `erpRenderQuest`(주문 쪽 `loadQuestDetail` 은 1단계에서 지움(부르는 곳 없음)), 시공 퀘스트 닿지 않는 갈래, `order_event_display.py:499-502`.
- 편집 폼·강제 단계 변경 select 의 "A.~H." 접두 제거.

## 6. 테스트

- 기대값 갱신: 보고서 §3-2 목록(`test_erp_quest_display.py`, `test_auth_quest_read.py:133`, `test_quest_surfaces_retransition_and_team_buttons.py`, `test_confirm_to_production_display.py`, `test_measurement_drawing_transfer_cta.py:143,162,315,324`, `test_measurement_drawing_transfer_button.py:55,79`, `test_tablet_dashboard_sheet_contract.py`, `tests/visual/test_p1_mockup_structure.py:559`).
- 새 테스트: ① 저장 title 이 "주문 정보 확인" 인 주문도 payload·GET 응답 title 이 "접수 확인" ② 단계별 `approve_label`·`retransition_label`·`done_label` 표(4절) ③ 모르는 단계 코드는 저장 title 로 떨어진다(빈 문자열 아님) ④ 팀 이름 사본 금지 계약.
- 클래스·ID 핀 단언은 건드리지 않는다.

## 7. 검증

```
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_erp_quest_display.py tests/domains/test_quest_surfaces_retransition_and_team_buttons.py tests/domains/test_confirm_to_production_display.py tests/domains/test_auth_quest_read.py tests/domains/test_measurement_drawing_transfer_cta.py tests/domains/test_measurement_drawing_transfer_button.py tests/domains/test_tablet_dashboard_sheet_contract.py tests/domains/test_tablet_t2_contract.py tests/visual/test_p1_mockup_structure.py -q
node --check static/js/orders/dashboard/erp-dashboard-quest.js
python -m pytest -n 8 -q   # 전체 레인(층 래칫 포함)
powershell -File scripts/ops/pre_push_smoke.ps1   # exit 0, 파이프 뒤에서 읽지 않는다
```

- 실제 dev 서버에서 PC 주문 대시보드 9단계 실화면 + 휴대폰 상세·큐 카드 실화면(실데이터 시드, 합성 DOM 주입 금지).
- 스테이징에서 `claude_master` 로 가상 주문(`CLAUDE-TEST-`) 접수 → 실측 넘기기 1회.

## 8. 위험

- PC 와 휴대폰이 같은 payload 를 쓴다(`dashboard_dto.py:59`, `erp_mobile_order_display.py:844`) — 휴대폰 글자도 함께 바뀐다(결정 2 가 의도한 것).
- 휴대폰 사용자는 "실측 완료" 버튼에 익숙하다. 이제 제목이 "실측 완료", 버튼이 "도면 단계로 넘기기" — 배포 알림에 한 줄 안내.
- 1단계는 글자만 바꾸므로 쿼리 변화 없음. 2단계는 생산 run 조회로 쿼리가 늘 수 있어 성능 가드 확인 필수.
