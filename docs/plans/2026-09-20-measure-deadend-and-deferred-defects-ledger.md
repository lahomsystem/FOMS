# 실측 막다른 길 해소 + 컨펌→생산 배치 이월 결함 처리 원장 (2026-09-20)

브리프 `docs/plans/2026-09-20-measure-deadend-and-deferred-defects-brief.md` · 앞 배치 원장 `2026-09-17-confirm-to-production-workflow-ledger.md` ·
검수 `2026-09-20-pipeline-persona-audit.md`(F1~F9) · 지도 `2026-09-17-pipeline-map-scout.md`.
작업 트리 `C:\tmp\foms-s-measure-deadend`(base origin/deploy `a89243fee`).

## 1. 제보와 원인 (총괄이 스테이징 HTTP 로 직접 확정)

PC 에서 실측 완료를 눌렀는데 도면으로 안 넘어간다(주문 이영아). 스테이징 #4382 의 `OrderEvent` 원문:

| 시각(KST) | 이벤트 | 내용 |
|---|---|---|
| 09-14 14:39:39 | `QUEST_APPROVAL_CHANGED` + `MEASUREMENT_COMPLETED` | 담당자 승인(claude_master) → `COMPLETE_MEASUREMENT` MEASURE→DRAWING |
| 09-14 14:39:50 | `STAGE_OVERRIDE` | mode regress, DRAWING→MEASURE, 사유 "스테이징 도면 전달 버튼 검증 후 원상 복구" |

즉 **관리자 강제 단계 변경(regress)이 quest 를 되돌리지 않는다**(`stage_override.py` 가 "퀘스트 부수효과 호출 안 함"을 의도로 명시). 그 결과 `workflow.stage=MEASURE` + MEASURE quest `COMPLETED` 가 남고, 앞 배치가 COMPLETED quest 를 `is_done` 완료 배지로 그리게 하면서 승인 버튼이 사라져 **막다른 길**이 됐다(그 전에는 "-" 였고 PC 는 `can_edit_erp` 로 버튼을 그렸다). 후보 ②③④(수동 COMPLETED·409 rollback·백필)는 이벤트 원문으로 배제.

**같은 모양 건수**(읽기 전용 SQL, 운영은 사용자 승인 1회):

| 대상 | 완료 quest ∧ 그 quest 단계 == 현재 단계 ∧ `stage_advance_target` 존재 | PRODUCTION ∧ current run 없음 | CONFIRM ∧ CONFIRM quest 없음 |
|---|---|---|---|
| 스테이징 | 4건 (#2921·#3338·#3610·#4382, 전부 MEASURE) | 0 | — |
| 운영 | 5건 (전부 MEASURE, 2026-03-31~08-16) | 0 | 1건 |

운영은 읽기만 했고 쓰기·변경 0(가드: `TESTCLR` 0건 지문 대조, 조회 뒤 `railway unlink`).

## 2. 사용자 결정 (2026-09-20)

- D1 막다른 길은 **둘 다** — ① 완료 배지 옆 재전이 액션(3표면) ② 강제 단계 변경 regress 시 그 단계 quest 를 다시 OPEN.
- D2 F2(P0): CONFIRM 호환 경로에서 **quest 없음 = 409**.
- D3 F4(P1): `POST /quest`·`PUT /quest/status` 저장 버그 수정 + **수동 COMPLETED 는 ADMIN/MANAGER + 사유 필수**.
- D4 운영 DB 읽기 1회 승인 · 모바일 팀 승인 버튼 추가(F5) · 타임라인 P2(F6·F7) 이번 범위.

## 3. 구현 (34 파일 수정 + 10 신규, 워커 4 병렬 + 통합 검증 + 리뷰 2 + CEO 판정 + fix)

| 계약 | 무엇 |
|---|---|
| C1 재전이(서버) | `foms/api/quest.py` 승인 라우트: 현 단계 quest 가 `COMPLETED` 이고 `stage_advance_target` 가 있으면 **승인 기록을 다시 쓰지 않고**(assignee_approval·team_approvals·completed_at 불변, 가짜 `QUEST_APPROVAL_CHANGED` 없음) 권한 게이트만 통과시킨 뒤 전이. 응답 `retransitioned: true`(정상 승인 응답에도 `false` 를 항상 싣는다), 전이 사유 "…재전이(완료 quest, 강제 단계 변경 뒤)". 옛 동작은 같은 요청에 승인자를 actor 로 **덮어썼다**. |
| C2 regress → quest 되돌림 | `stage_override.py::_reopen_completed_stage_quest` — regress 일 때만, 되돌아간 단계의 COMPLETED quest 중 최신 1건을 `status=OPEN`·승인 비움·`reopened_by_override{at,from_stage,reason}`, `completed_at` 제거. STAGE_OVERRIDE payload 에 `quest_reopened`. 원본 리스트·dict 제자리 수정 금지(셸 복사 함정). advance/skip/jump 불변, 나중 단계 quest 보존. |
| C3 표시 SSOT | `build_current_quest_payload` 에 `can_retransition`·`retransition_label`·`retransition_confirm`·`approvable_teams`·`is_synthesized` 추가. 판정은 새 순수 함수 `quest_approve_authz.actor_teams_for / quest_approve_allowed / approvable_teams_for / display_team_axes` 한 곳 — `authorize_quest_approve`(서버 게이트)가 **같은 함수**를 쓴다. 합성 quest 의 팀 버튼은 RECEIVED·CS 에서만(생산 quest 는 만들지 않는다는 앞 배치 규칙 유지). |
| C4 3표면 | PC 그리드(셀·collapse 카드), 모바일 큐 카드, 모바일 상세에 재전이 버튼. 팀 버튼 노출이 `can_edit_erp` → `team in approvable_teams`(F3), 모바일 상세·카드에 팀 승인 버튼 신설(F5). 거부당할 버튼 0·버튼 없는 막다른 길 0 을 대조군 테스트로 못박음. 핀 `20260920b` 9곳(+`layout_scripts.html` 의 `erp-quest-approve.js` 줄). |
| C5 F2 | `_stage_quest_block(..., require_quest=True)` — CONFIRM 호환 경로만. quest 없음도 409(`code QUEST_INCOMPLETE` 유지, 구분은 `reason: QUEST_MISSING`, 문구 "고객컨펌 승인이 먼저 필요합니다."). 화면 승인 버튼이 quest 를 만들고 전이까지 하므로 막다른 길이 아님을 테스트로 확인. `production/complete` 등 다른 호출부는 기본값 그대로. 테스트 픽스처 공용 헬퍼 `tests/support/quest_seed.py`. |
| C6 F4 | 두 라우트에 `deepcopy → 수정 → 재대입 → flag_modified`. PUT 은 별칭 매칭(한글 저장형 '고객컨펌' 404 해소). 수동 `COMPLETED` 는 ADMIN/MANAGER(403 `ROLE_REQUIRED`) + 사유 필수(400 `REASON_REQUIRED`), `manual_status{by,at,reason}` 기록. |
| C7 타임라인 | `order_timeline_v3._stage_reach_events` 가 `STAGE_CHANGED`·`STAGE_OVERRIDE`·`payload.axis == "MAIN"` 전이를 함께 읽고 `to` 가 알려진 단계일 때만 기록(옛 코드는 미상 값을 RECEIVED 로 접었다). 라벨 7종 등재(`STAGE_OVERRIDE`="단계 강제 변경" 외), `STAGE_OVERRIDE` 변경 설명문에 사유 표기. 죽은 키 `STAGE_MANUAL_OVERRIDE` 는 주석으로 표기. |
| C8 F9 | `confirm-drawing-receipt` 가 이름 대조 전에 `active_assignee_ids(db, order.id, 'SALES')` **id 대조**를 본다 — 주문 생성 시 owner 는 `OrderAssignment(domain="SALES")` 행에만 남는다. |

신규 테스트 10파일(재전이 9·override 되돌림 7·수동 상태 8·생산 게이트 9·3표면 33·타임라인 8·도면 수령 6 등), 기존 계약 테스트 갱신 9파일.

## 4. CEO 판정 (fix 1회)

리뷰 findings 중 실질 1건 채택: **같은 단계에 COMPLETED 와 OPEN quest 가 함께 있으면 화면(활성 우선)과 서버(첫 일치)가 다른 quest 를 잡았다** — C2 가 나중 단계 quest 를 보존하고 엔진이 다음 단계 quest 를 append 하므로 이번에 실제로 만들어지는 모양이 됐다. 수정: 새 헬퍼 `quest_transition_service.find_stage_quest_for_approve`(활성 최신 → 완료 최신 → 첫 일치)로 라우트가 표시 SSOT 와 같은 규칙을 쓴다. 그 밖 P3 4건(문구·토스트 분기·주석 정정·합성 quest 문구 "(보드에서 진행)") 반영.

기각: `check_quest_approvals_complete`·`_stage_quest_complete` 의 첫 일치 정렬 통일(소유권 밖, 라우트 수정 뒤 게이트 답이 같음) → 다음 배치 요청.

## 5. 게이트 (총괄이 직접 재실행, 워커 보고와 별개)

| 게이트 | 결과 |
|---|---|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `node --check` 2파일 | exit 0 |
| `python -m pytest tests/domains -q` | 7641 passed, 5 skipped |
| `python -m pytest tests/contracts tests/harness -q` | 624 passed |
| `scripts/ops/pre_push_smoke.ps1` | **EXIT 0** (33 targets, 806 passed) |

인벤토리 3종(writer·state·failopen) 재생성 후 `--check` exit 0. `tests/visual` 전체(로컬 Playwright 레인)는 실패 19건이 base `a89243fee` 에서도 동일 — 이 배치와 무관한 로컬 베이스라인 드리프트이고 CI 는 그 레인을 제외한다.

## 6. 잔여 위험·다음 배치

- **팀 alias 함정(기존)**: ACCOUNTING(CS alias) STAFF 가 팀 승인을 하면 슬롯이 `ACCOUNTING` 으로 기록돼 required `CS` 가 미승인으로 남는다(`quest.py` `effective_team`). 화면은 버튼을 그리고 서버는 200 인데 종결이 안 된다 — 다음 배치에서 `요청 team ∈ actor capability` 로.
- C1 재전이 뒤 `workflow.stage_override` 표식이 남는다(기능 영향 없음 — `override_pins_stage` 가 단계 불일치면 무효). 지우려면 엔진 스냅샷 경계를 건드려야 해 이번엔 보류.
- C2 되돌림은 quest 축만이다. CONFIRM 을 되돌려도 `blueprint.customer_confirmed` 는 남고, MEASURE 되돌림에서 실측 플랫 컬럼도 남는다.
- PC 그리드 담당자 버튼 게이트(`can_edit_erp or can_assignee_approve`)는 이번에 안 바꿨다 — 필수 팀이 아닌 사람에게 뜰 수 있다(F3 는 팀 버튼만).
- `PUT /quest/status` 수동 COMPLETED 는 전이를 일으키지 않는다. 관리자가 찍으면 화면은 완료 배지 + 재전이 버튼을 주고 그 버튼이 전이한다(의도된 2단계).
- 스테이징 4건·운영 5건은 데이터 이관 없이 사람이 재전이 버튼으로 넘긴다(SALES/CS/ADMIN).
- 범위 밖 유지: F8(v3 모바일 생산 큐 제작 시작/완료 — 코호트 범위 측정 먼저), 지도 #1 CS→COMPLETED UI 부재 / #2 `field_update status=COMPLETED` 게이트 우회 / #6 CONSTRUCTION→CS quest 게이트 부재 / #7 DRAWING→CONFIRM·`construction/fail` 엔진 우회 / #9 `cs/confirm.py` 가 quest 를 안 닫음 / #11 모바일 실측 완료의 AS 열림 억제 / #13 모바일 시공 불가 / #14 `stage_badge_label` CS→"AS" / #15 `object.html` STAGE_LABELS 하드코딩.
- 승격 시 충돌 예상: docs(AI_STATUS·AI_CHANGELOG)와 핀 줄(`layout_head.html`·`layout_scripts.html`·`dashboard.html`·`dashboard_main.html`·`erp-pro.css`·`erp-dashboard-entry.js`) — 원격 쪽을 살리고 내 줄만 얹는다. AI_STATUS 예산은 production 기준으로 다시 잰다.
