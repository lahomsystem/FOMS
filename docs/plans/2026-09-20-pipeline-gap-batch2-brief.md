# 브리프(초안 — CEO 가 계약을 확정한다): 파이프라인 잔여 결함 4묶음 (2026-09-20, 배치 2)

작업 트리 `C:\tmp\foms-s-measure-deadend`(브랜치 `session/measure-deadend`, base origin/deploy, 직전 커밋 `246978993`).
`C:\DEV\FOMS` 는 읽지도 편집하지도 않는다. 워커는 **git 명령 금지**(커밋·push 는 총괄).
앞 배치 원장 `docs/plans/2026-09-20-measure-deadend-and-deferred-defects-ledger.md` · 지도 `2026-09-17-pipeline-map-scout.md` · 검수 `2026-09-20-pipeline-persona-audit.md`.

## 1. 사용자 결정 (2026-09-20, AskUserQuestion 2회)

| # | 결정 |
|---|---|
| D1 | 팀 별칭: 경리팀(ACCOUNTING)이 승인하면 **필요한 칸(CS)에 기록**하고 실제 누른 팀을 함께 남긴다. |
| D2 | 실측 보드 [완료] 버튼은 **정식 경로(cs/complete)로 보낸다.** 막히면 이유를 화면에 보여 준다. 출고·배송 같은 보드 상태는 지금대로. |
| D3 | 시공 완료: **사진·서명 증빙 게이트를 운영에도 켠다.** |
| D4 | 도면 수령 확정과 시공 불가: **둘 다 정식 전이 경로로.** 화면 동작은 그대로. |
| D5 | 쓰이지 않는 `POST /api/orders/<id>/confirm/customer`(cs/confirm.py): **지운다.** |
| D6 | 모바일: **새 화면(v3) + 빠진 버튼 모두** — v3 생산·시공 카드에 시작/완료, 그리고 수정 제작·제작 취소·완료 취소·시공 불가를 휴대폰에서 가능하게. |
| D7 | 단계 배지: CS 단계는 **"CS"**(AS 와 구분). |

앞 배치에서 이미 결정·구현된 것(중복 금지): 재전이 버튼, regress quest 재개, CONFIRM quest 없는 제작 시작 409, 수동 quest 권한, 팀 버튼 `approvable_teams`, 타임라인 엔진 이벤트·라벨 7종, 도면 수령 확정 owner id 축.

## 2. 앵커 (정찰 2건, 이 트리 기준 — 열어서 확인)

### A. 누르면 거부당하는 버튼

- **A1 팀 별칭**: `foms/api/quest.py:407` `effective_team = (team or actor_team) if (role=='ADMIN' or emergency_override) else actor_team`; 슬롯 쓰기 `:461-466` `current_quest["team_approvals"][effective_team] = {...}`; 완료 판정 `:471`.
  별칭표 `foms/services/orders/order_mutation_policy.py:18` `_TEAM_NORMALIZE={"MEASURE":"SALES"}`, `:54` `_TEAM_CAPABILITY_ALIASES={"ACCOUNTING":("CS",)}`, `:245-259` `team_capabilities`, `:262-278` `team_has_capability`.
  판정 `foms/services/orders/erp_policy_quests.py:117-126` — `team_approvals.get(team_key)` **정확 일치만**(별칭 없음) → ACCOUNTING 슬롯은 CS 요구를 못 채운다.
  `foms/services/orders/quest_approve_authz.py:158-183` `approvable_teams_for` 도 같은 정확 일치로 "승인됨" 을 판정한다.
- **A2 PC 담당자 버튼**: `templates/orders/partials/dashboard_grid.html:175` `{% if can_edit_erp|default(false) or o.current_quest.can_assignee_approve|default(false) %}`; 같은 구멍이 `templates/orders/partials/tablet_dashboard_sheet.html:82`.
  `can_edit_erp` = `foms/services/erp_permissions.py:291-305`(팀 CS/SALES capability만, role·단계·quest 무시). 서버 술어는 `quest_approve_allowed`(`quest_approve_authz.py:140-155`).
  관련 테스트: `tests/domains/test_tablet_dashboard_sheet_contract.py:208`, `tests/domains/test_measure_approval_teams.py:78,90,114-125`, `tests/domains/test_auth_quest_approve.py:285-302`, `tests/domains/test_erp_permissions.py:43-62`.

### B. 마지막 단계·게이트 구멍

- **B1 CS→COMPLETED UI 부재**: 정식 라우트 `foms/api/cs/complete.py:159-210`(게이트 `_cs_gate_block:103-119` = quest·보류·AS, quest 없음은 통과 `:80-100`). 화면 호출자 0(템플릿·JS grep 0).
- **B2 우회로**: `templates/partials/shared/status_select_options.html:39-51` 매크로 `complete_order_control` → `static/js/measurement/complete-order-btn.js:28-35` → `POST /api/update_order_field {field:'status', value:'COMPLETED'}`.
  `foms/api/orders/field_update.py:454-607` — `:476-489` 권한은 role 3종만(팀 무관), `:532-566` `is_logistics_board_status("COMPLETED")` 가 True 라(`foms/services/orders/status_constants.py:31-36`) 단계 override 가드도, `should_canonicalize_main_status`(`foms/api/orders/status.py:145-181`)도 건너뛰고 `setattr` + `workflow.stage="COMPLETED"`(`:585-607`). 렌더 화면 3곳: `templates/measurement/{metropolitan,regional,self_measurement}_dashboard.html`.
  영향받는 테스트: `tests/domains/test_logistics_dashboard_status.py:54-73`(COMPLETED 직접 저장 단언 — **이번에 바뀐다**), `tests/domains/test_state_controls.py:125-127,156-157,201-209`, `tests/domains/test_measurement_drawing_transfer_button.py:168-171`.
- **B3 시공 완료**: `foms/api/construction/orders.py:325-385` — 유일한 게이트가 `:346-353` `env_bool("FOMS_CONSTRUCTION_GATE_ENABLED", default=False)` + `_evidence_gate_missing:168-178`(after 사진 2장·서명). **quest 게이트 없음**(파일 내 `quest` 0건). 운영 web 서비스에 그 변수 없음(=off), 스테이징은 켜져 있다.
  테스트 `tests/domains/test_state_const_cs.py:141-188,227-298`, `tests/postgres/test_state_const_cs.py:144,173`.

### C. 기록이 안 남는 전이

- **C1 도면 수령 확정**: `foms/api/drawing/erp_orders_draftsman.py:315` 라우트, 게이트 `:341`(drawing_status TRANSFERRED), 직접 쓰기 `:384-428`(workflow.stage·history·status·`sync_erp_flat_columns`), 이벤트는 `DRAWING_STATUS_CHANGED` 하나 `:430-448`. 레지스트리에 DRAWING→CONFIRM 명령 없음.
  엔진 `foms/services/orders/order_transition_service.py:307-322` `transition_order(...)`, 레지스트리 `:183-228`, 등록 예시 `foms/api/production/orders.py:256-274`(`COMMAND_REGISTRY.setdefault`), 잠금·버전·영수증 `:441-451`, 충돌 `:376-386` `StageConflictError`.
  writer 예외 태그 `tools/harness/order_mutation_writer_scan.py:138`(`STATE-DRAWING-01`).
  테스트: `tests/domains/test_drawing_collab_fixes.py:63-92`, `test_drawing_confirm_cleanup.py:274-289`, `test_drawing_receipt_sales_owner.py:79-156`(전부 `drawing_status` 만 단언 — 단계 전이 단언 없음).
- **C2 시공 불가**: `foms/api/construction/orders.py:483-603` — `_REWORK_STAGE_MAP:483-494`, `new_stage = map.get(reason)` `:524`, `execute_order_mutation` 안에서 stage 직접 쓰기 `:554-578`, 이벤트 `CONSTRUCTION_REWORKED` `:579-585`, **changed-family 빈 리스트** `:586`(캐시 무효화 없음), `expected_from` 검사 없음.
  테스트 `tests/domains/test_state_const_cs.py:210-221`, `test_audit_action_coverage.py:160-169`, `test_construction_date_event_ssot.py:232-237`.
- **C3 죽은 API**: `foms/api/cs/confirm.py`(80줄) — `blueprint.customer_confirmed` 만 쓰고 quest·stage 무변경, 이벤트·영수증 없음. 화면 호출자 0. 참조: `foms/api/cs/__init__.py:6`, `foms/platform/blueprints.py:78,147`, 계약 `tests/contracts/runtime/foms_namespace_surface_tests.py:772,787`, writer 예외 `tools/harness/order_mutation_writer_scan.py:142`.

### D. 모바일·말투

- **D1 빠진 버튼**: 모바일 생산 큐 `templates/production/partials/mobile_queue.html:42-50`(start/complete 만), 모바일 시공 큐 `templates/construction/partials/mobile_queue.html:88-105`(시공 불가 없음).
  있는 쪽: 태블릿 `templates/production/partials/tablet_kanban_body.html:320-322`(rework), `templates/construction/partials/tablet_workmode_body.html:126`(`data-cwork-fail`).
  JS: `static/js/foms/tablet-domain-sheets.js:72,134-160,183`(`/production/rework|cancel|uncomplete|hold`, 762줄·기준선 등재), `static/js/foms/tablet-construction-workmode.js:256-302`(`/construction/fail`, prompt 2회), 모바일 위임 `templates/production/partials/scripts.html:271-279,845-857`, `static/js/construction/dashboard.js:404-437,497-509`.
- **D2 v3 화면**: `templates/production/partials/dashboard_body.html:131,163-171`(v3 면 v2 모바일 큐 자체가 렌더 안 됨), `templates/partials/v3/persona_home_production.html`(151줄, **data-action 0개 — 시작·완료조차 없다**), 코호트 `foms/services/feature_flags.py:257-306`(env `FOMS_SHELL_V3_ENABLED`·`FOMS_SHELL_V3_COHORT`, 쿠키 `foms_shell_pref=v2` 옵트아웃). **v3 사용자 수를 아는 방법이 앱에 없다**(로깅 0).
- **D3 라벨**: `foms/services/erp_mobile_order_display.py:518-533` `stage_badge_label` 이 `CS→"AS"`(913줄·기준선 등재), 정본 `foms/services/orders/erp_policy_constants.py:14-26` `STAGE_LABELS["CS"]="CS"`.
  `templates/orders/object.html:154-155` JS `STAGE_LABELS` 가 CONSTRUCTION 에서 끝나 CS/COMPLETED 는 영문 코드 노출(`label(map, code, '-')` `:157`).
  테스트: 배지 문자열을 단언하는 테스트 없음. `tests/domains/test_tablet_dashboard_sheet_contract.py:189` 는 템플릿 참조만.

### 공통 제약
- 파일 크기 래칫(`tests/harness/file_size_baseline.json`, py 500·js 300, 기준선 밖 파일은 넘기면 red): `erp_quest_display.py` 494(여유 6), `quest_approve_authz.py` 267, `erp_policy_quests.py` 250, `erp_orders_draftsman.py` 464, `order_transition_service.py` 473, `cs/complete.py` 231, `status_constants.py` 120. 기준선 등재(증가 허용): `quest.py` 671, `production/orders.py` 1591, `construction/orders.py` 613, `field_update.py` 942, `erp_mobile_order_display.py` 913, `feature_flags.py` 586, `tablet-domain-sheets.js` 762, `construction/dashboard.js` 1355.
- writer 인벤토리 3종(`order_mutation_writer_scan.py`·`state_writer_scan.py`·`failopen_scan.py`)은 lineno 고정 — 줄이 밀리면 재생성 후 `--check`.
- structured_data 규약(deepcopy→수정→재대입→flag_modified), 인라인 style 금지, `fetch` 는 try/catch + `data.success`, jQuery 금지.

## 3. 계약 초안 (이름 고정, CEO 가 규칙 확정)

### C-A1 팀 별칭 슬롯
- 승인 슬롯 키 = **필수 팀 중 actor 의 capability 가 만족하는 팀**(`team_has_capability(actor_team, [t])` 인 첫 `t`, 여럿이면 payload `team` 우선). 그 팀이 없으면 지금처럼 403.
- 슬롯 값에 `by_team: <actor_team>` 을 함께 남긴다(누가 눌렀는지 보존). 기존 키(`approved`,`approved_by`,`approved_by_name`,`approved_at`) 불변.
- ADMIN·override 가 payload `team` 을 지정하면 그 팀 슬롯(현행 유지).
- 테스트: ACCOUNTING STAFF 가 CS 필수 quest 승인 → 슬롯 `CS.approved=True`·`by_team="ACCOUNTING"` → `check_quest_approvals_complete` True → 단계 전이. 대조군: DRAWING STAFF 403, MEASURE 팀(→SALES 정규화) 이 SALES 필수 quest 에 SALES 슬롯.

### C-A2 담당자 버튼 술어
- `dashboard_grid.html:175`·`tablet_dashboard_sheet.html:82` 의 `can_edit_erp or ...` → **`can_assignee_approve` 단독**. 없으면 `(승인 권한 없음)`.
- 테스트: 화면==서버 파서블 대조군(필수 팀 / 비필수 팀 / ADMIN / VIEWER), 태블릿 시트 계약 테스트 갱신.

### C-B1·B2 완료 경로 일원화
- 매크로 `complete_order_control` 이 그리는 버튼은 **주문의 현재 단계가 CS 면 `POST /api/orders/<id>/cs/complete`**, 그 밖(출고·배송 보드 상태 축)은 지금처럼 `update_order_field`. 판정은 서버가 템플릿 인자로 준다(`complete_endpoint`·`complete_blocked_reason` 같은 이름은 CEO 확정).
- `field_update` 의 `status=COMPLETED` 는 **메인 파이프라인 주문에 대해 409/403 으로 거부**하고 안내 문구를 준다(`code: USE_CS_COMPLETE`). AS·출고 축 상태는 불변. `test_logistics_dashboard_status.py:61-73` 은 새 계약으로 뒤집어 쓴다(삭제 금지).
- 막혔을 때 화면은 서버 사유(quest 미승인 팀·보류·AS)를 그대로 보여 준다 — 막다른 길 금지: CS quest 미승인이면 승인 버튼이 있는 곳(대시보드 퀘스트 칸)으로 가는 길을 문구에 넣는다.

### C-B3 시공 증빙 게이트 기본 ON
- `env_bool("FOMS_CONSTRUCTION_GATE_ENABLED", default=True)` 로 뒤집는다(운영 변수 미설정 = 켜짐). 끄려면 명시적으로 `false`.
- 400 응답의 `missing` 을 화면이 사람 말로 보여 주는지 확인(모바일 완료 게이트 시트 `foms-complete-gate.js`).
- 테스트: 증빙 없음 → 400·`missing`, 증빙 채움 → 200 CS. 기존 테스트 중 게이트를 끈 채 통과하던 것은 시드를 채운다.

### C-C1 도면 수령 확정 → 엔진
- 새 명령 `DRAWING_RECEIPT_CONFIRM`(axis MAIN, from `("DRAWING",)`, to `("CONFIRM",)`, event `DRAWING_RECEIPT_CONFIRMED`, effect `STAGE_NOTIFICATION`) 을 `erp_orders_draftsman.py` 에서 `COMMAND_REGISTRY.setdefault` 로 등록하고 `transition_order` 를 쓴다. 기존 `DRAWING_STATUS_CHANGED` 이벤트와 파일 정리(`finalize_drawing_files_on_confirm`)는 유지.
- 타임라인 라벨에 새 event_type 등재(`order_event_display.py`) — 안 하면 "기타 변경".
- 테스트: 200 시 `workflow.stage=CONFIRM`·`erp_stage_code`·`mutation_version` 증가·영수증 1건·이벤트 파리티, 이미 CONFIRM 인 주문 재요청 → 409 충돌(또는 멱등 replay — CEO 확정), drawing_status 미TRANSFERRED 400 유지.

### C-C2 시공 불가 → 엔진
- 사유별 명령 4종(`CONSTRUCTION_FAIL_TO_DRAWING|MEASURE|PRODUCTION|CONSTRUCTION`) 또는 단일 명령 + to_values 다중 — CEO 확정. `expected_from=("CONSTRUCTION",)`, event `CONSTRUCTION_REWORKED` 유지, `effect_type` 은 CEO 확정.
- 캐시 무효화: 지금 빈 changed-family 리스트(`:586`)를 단계 이동에 맞게 채운다.
- 테스트: 사유 4종 각각 목표 단계 + 버전·영수증, CONSTRUCTION 아닌 단계에서 409, 기존 attempt 봉인·이력·재예약 단언 유지.

### C-C3 죽은 API 제거
- `foms/api/cs/confirm.py` 라우트 삭제 + blueprint 등록 해제(`foms/api/cs/__init__.py`, `foms/platform/blueprints.py`), writer 예외 태그 정리, 네임스페이스 계약 테스트 갱신(`foms_namespace_surface_tests.py:772,787`).
- 삭제 근거를 파일 대신 원장·계약 테스트 주석에 남긴다.

### C-D1·D2 모바일 버튼
- v2 모바일 생산 큐: `제작중`에 [수정 제작]·[제작 취소], `제작완료`에 [완료 취소]. v2 모바일 시공 큐 `시공중`에 [시공 불가].
- v3 화면(`persona_home_production.html` + 시공 대응 파일): 시작·완료를 먼저 넣고, 위 4종도 같이. v3 카드의 액션은 v2 와 **같은 `data-action` 이름**을 써서 기존 위임 JS 를 태운다(새 JS 파일 최소화, 300줄 래칫 주의).
- 사유 입력이 필요한 것(`rework`·`cancel`·`fail`)은 `window.prompt` 대신 기존 모바일 시트 패턴을 쓴다 — CEO 가 패턴 하나를 정해 3곳이 같게.
- 권한: 서버 데코레이터와 같은 조건에서만 버튼을 그린다(생산팀·시공팀·ADMIN). 거부당할 버튼 0.
- v3 코호트 관측: `resolve_shell_variant` 가 v3 로 판정될 때 **하루 1회 수준의 저비용 기록**(예: SecurityLog/감사 1행 또는 카운터)을 남길지 CEO 확정 — 지금은 v3 사용자 수를 알 방법이 없다.

### C-D3 라벨
- `stage_badge_label` 의 `CS` 를 `"CS"` 로. 나머지 축약(접수·실측·컨펌…)은 유지하되 `STAGE_LABELS` 와 어긋나는 값은 주석으로 근거를 남긴다.
- `templates/orders/object.html:154-155` JS `STAGE_LABELS` 에 CS·COMPLETED·AS 3종 추가(정본과 같은 문자열). 하드코딩 중복 자체는 `data-*` 주입으로 없앨지 CEO 확정.
- 테스트: `stage_badge_label("CS") == "CS"`, object.html 에 영문 코드 노출 0.

## 4. 워커 소유권(겹치지 않게)

| 워커 | 편집 허용 | 금지 |
|---|---|---|
| W1 승인·권한(C-A1·C-A2) | `foms/api/quest.py`, `foms/services/orders/erp_policy_quests.py`, `foms/services/orders/quest_approve_authz.py`, `templates/orders/partials/dashboard_grid.html`, `templates/orders/partials/tablet_dashboard_sheet.html`, 관련 테스트(`test_auth_quest_approve.py`·`test_measure_approval_teams.py`·`test_tablet_dashboard_sheet_contract.py`·`test_state_quest.py`) + 신규 `tests/domains/test_team_alias_approval_slot.py` | 생산·시공·field_update |
| W2 완료 경로(C-B1·C-B2·C-B3) | `foms/api/orders/field_update.py`, `foms/api/cs/complete.py`, `foms/api/construction/orders.py`(완료 게이트 부분), `templates/partials/shared/status_select_options.html`, `static/js/measurement/complete-order-btn.js`, 테스트 `test_logistics_dashboard_status.py`·`test_state_controls.py`·`test_state_const_cs.py`·`test_measurement_drawing_transfer_button.py` + 신규 `tests/domains/test_cs_complete_from_measure_board.py` | 시공 불가 블록(W3), quest.py |
| W3 엔진 전이(C-C1·C-C2·C-C3) | `foms/api/drawing/erp_orders_draftsman.py`, `foms/api/construction/orders.py`(`construction/fail` 블록만 — W2 와 파일 공유: **W3 이 `:483-603`, W2 가 `:325-385`**), `foms/api/cs/confirm.py`(삭제), `foms/api/cs/__init__.py`, `foms/platform/blueprints.py`, `foms/services/order_event_display.py`, `tools/harness/order_mutation_writer_scan.py`(예외 태그), 테스트 `test_drawing_collab_fixes.py`·`test_state_const_cs.py`(fail 부분)·`foms_namespace_surface_tests.py` + 신규 `tests/domains/test_drawing_receipt_transition_engine.py`·`test_construction_fail_transition_engine.py` | 완료 게이트 블록(W2) |
| W4 모바일·라벨(C-D1·C-D2·C-D3) | `templates/production/partials/mobile_queue.html`·`dashboard_body.html`·`scripts.html`, `templates/construction/partials/mobile_queue.html`, `templates/partials/v3/persona_home_production.html`(+ 시공 v3 대응 파일), `foms/services/erp_mobile_order_display.py`, `templates/orders/object.html`, 필요한 JS(기존 파일 우선), `foms/services/feature_flags.py`(관측 결정 시), 테스트 `test_production_dashboard_mobile.py`·`test_construction_dashboard_mobile.py`·`test_erp_mobile_order_display.py` + 신규 `tests/domains/test_mobile_production_construction_actions.py` | API 파일 |

**파일 공유 주의**: `foms/api/construction/orders.py` 를 W2·W3 가 나눠 쓴다. CEO 는 두 워커에게 편집 구간(행 범위·함수 이름)을 명시하고, 같은 함수는 한 워커만 건드리게 한다. 충돌 시 통합 검증자가 해제.

## 5. 검증 (워커 공통)

```
cd /c/tmp/foms-s-measure-deadend && pwd
python -c "import app; print('APP_OK')"
python -m pytest <자기 테스트 파일들> -q -p no:cacheprovider
node --check <건드린 JS>
```
통합 검증자: `tests/domains` 전량 -x → `tests/contracts tests/harness` → CI 와 같은 `tests/visual` 부분집합 → 인벤토리 3종 재생성 + `--check` → `git diff --stat`.

## 6. 함정

- `field_update` 는 화면 여러 곳(실측 3보드·출고·AS)이 같은 라우트를 쓴다 — COMPLETED 거부가 **다른 축 상태 변경을 막으면 안 된다**(AS·출고 보드 상태 목록 확인).
- `construction/fail` 은 `execute_order_mutation` 안에 있어 버전·영수증은 이미 있다 — `transition_order` 로 옮길 때 **이중 영수증·이중 버전 증가**가 나지 않게 한다.
- 도면 수령 확정은 파일 정리(`finalize_drawing_files_on_confirm`)와 같은 커밋이다 — 전이 실패 시 파일이 지워진 채 단계가 안 바뀌는 순서가 되면 안 된다.
- v3 셸은 `shell_variant` 가 `v3` 일 때 v2 마크업을 **아예 렌더하지 않는다** — v2 에만 버튼을 넣으면 v3 사용자에겐 없는 것과 같다.
- 모바일 액션 이름은 `window[data-action]` 전역 위임이라 이름 충돌 주의(`scripts.html:845-857`).
- 새 이벤트 타입은 `order_event_display.py` 라벨표에 반드시 등재(안 하면 "기타 변경").
- 시공 증빙 게이트 기본 ON 은 **운영 업무에 바로 영향**이다 — 기존 테스트가 게이트 off 를 전제하면 시드를 채워 고친다(테스트를 끄지 마라).
- CRLF 보존. 기준선 밖 파일의 500/300줄 초과 금지.
