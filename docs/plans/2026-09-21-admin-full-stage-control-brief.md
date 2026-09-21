# 브리프(초안 — CEO 가 계약을 확정한다): 관리자는 모든 단계를 바꿀 수 있어야 한다 (2026-09-21)

작업 트리 `C:\tmp\foms-s-measure-deadend`(브랜치 `session/measure-deadend`, base origin/deploy). 워커는 **git 명령 금지**.
앞 배치 원장 `docs/plans/2026-09-20-measure-deadend-and-deferred-defects-ledger.md` · `2026-09-20-pipeline-gap-batch2-ledger.md`.
주문 일생 도식(사람용) https://claude.ai/artifact/TV4bDyeMpijUbdVNS7LZc2 — 이 배치가 끝나면 "되돌아가는 길" 절을 갱신한다(총괄 몫).

## 1. 사용자 지시와 결정 (2026-09-21)

> "관리자는 모든 단계를 변경 할 수 있어야 돼"

| # | 결정 |
|---|---|
| D1 | **범위: 삭제까지 포함.** 강제 단계 변경으로 본공정 8단계 + AS 접수·AS 처리·AS 완료 + 삭제됨까지 갈 수 있다. |
| D2 | 관리자는 **일반 화면에서도** 역행·건너뛰기가 바로 된다(지금은 403 후 강제 변경 창 안내). |
| D3 | 관리자는 **업무 게이트를 뚫고** 진행할 수 있다: 시공 증빙·컨펌 승인·CS 승인·보류·AS 열림·완료는 CS 단계에서만. |
| D4 | 뚫고 갈 때는 **사유 필수 + 주문 이력에 "관리자가 검사를 건너뛰었음" 이 보인다.** |

## 2. 지금 관리자가 막히는 자리 (정찰 실측, 경로:행)

### 2.1 강제 단계 변경 라우트
- 역할 게이트는 통과: `foms/api/orders/stage_override.py:69`(bulk `:218`), `OVERRIDE_ALLOWED_ROLES={ADMIN,MANAGER}`(`foms/services/orders/stage_override.py:53`).
- **목표 단계 제한**: `foms/services/orders/stage_override.py:277-278` — `normalize_main_stage(to) ∉ MAIN_PIPELINE_CODES`(`:42-51` 8코드) → 400 "메인 파이프라인 단계만 강제 변경할 수 있습니다. (AS/삭제는 기존 경로 사용)". **role 검사 없음 = 관리자도 차단.**
- 그 밖 전원 적용 가드(유지 대상): `confirm != true` 400(`api/orders/stage_override.py:81`), 빈 사유 400(`services/.../stage_override.py:280-282`), same 단계 400(`:286-288`), If-Match 형식 400(`api/...:96-98`)·stale 409(`:158-164`), bulk 1000건 상한(`:424-425`).
- AS overlay 주문은 bulk 에서 `include_as: true` 로만 포함(`api/orders/stage_override.py:272-275`, `:436`). **UI 에는 그 체크박스가 없다.**
- `classify_stage_move`(`services/.../stage_override.py:119-135`) same/advance/regress/skip/jump, `requires_privileged_override`(`:138-148`).

### 2.2 일반 화면 상태 변경
- `foms/api/orders/status.py:306-307`(단건)·`:551-553,594,620`(bulk), `foms/api/orders/field_update.py:556-557` — `requires_privileged_override` 면 403 `OVERRIDE_BLOCK_MESSAGE`. **role 검사 자체가 없어 관리자도 403.**
- 완료 거부(이번 주 신설): `status.py:314-315`·`:557-558`, `field_update.py:522-523` → 409 `USE_CS_COMPLETE`(`foms/services/orders/complete_path_policy.py:180,263-283`). 관리자 예외 없음.
- 폼 PUT 은 단계를 조용히 서버값으로 고정: `foms/api/erp_orders_structured.py:315-347`.

### 2.3 업무 게이트(관리자 우회 없음)
| 게이트 | 경로:행 | 거부 |
|---|---|---|
| 도면 수령 확정 전제 | `foms/api/drawing/erp_orders_draftsman.py:345-349` | 400 "전달된 도면(확정 대기 상태)에서만" |
| 도면 단계 단독 승인 | `foms/api/quest.py:314-322`(`_COMMAND_REQUIRED_STAGES` `:201`) | 409 `COMMAND_REQUIRED` |
| 제작 시작 컨펌 승인 | `foms/api/production/orders.py:749` → `_stage_quest_block(..., require_quest=True)` `:375-410` | 409 `QUEST_INCOMPLETE`/`QUEST_MISSING` |
| 제작 완료 생산 승인 | `production/orders.py:841` | 409 `QUEST_INCOMPLETE` |
| 보류 | `production/orders.py:363-372`(`release_hold` 로 자기해제 가능), `foms/api/cs/complete.py:118-120` | 409 `HOLD_ACTIVE` |
| 시공 증빙 | `foms/api/construction/orders.py:364-371`, `_evidence_gate_missing:186-195` (기본 ON) | 400 "완료 요건 미충족" + `data.missing` |
| 단계 전제 | `production/orders.py:740-741,753-754,836-837,899-905,1039-1043,1110-1111`, `construction/orders.py:226-230,381-382`, `cs/complete.py:194-196` | 409 `INVALID_STAGE`/`ALREADY_STARTED` |
| CS 승인·AS | `cs/complete.py:85-124` | 409 `QUEST_INCOMPLETE`/`AS_ACTIVE` |
| 엔진 공통 | `foms/services/orders/order_transition_service.py:355-377` | `to_values` 위반 409, 잠금 아래 `expected_from` 불일치 409 `StageConflictError` |

### 2.4 엔진의 `emergency_override`
`order_transition_service.py:312,338-339,359-367,404` — **인접성(`from_values`) 검사 하나만** 건너뛰고 `reason` 필수, payload 에 기록. `to_values`·잠금 재확인·If-Match·영수증은 그대로. **어떤 라우트도 이 파라미터를 노출하지 않는다**(전 호출부 기본 False).

### 2.5 화면
- 모달 `templates/orders/partials/erp_stage_override_modal.html` — 가시성 `:2` role ADMIN/MANAGER, **옵션 하드코딩 `:25-32`** 8단계(AS·삭제 없음). 진입 버튼 `erp_order_tab.html:230-237`, `..._mobile.html:402-409`.
- JS `static/js/orders/erp-stage-override.js` — `canOverride()` `:151-154`, 단건/벌크 `:333-338`, If-Match `:327-330`, 409 문구 `:350-353`, 상태 변경 가로채기 `:474`, 그리드 일괄 `:506-544`.

### 2.6 현 제약을 고정한 테스트(뒤집어 써야 한다 — 삭제 금지)
`tests/domains/test_workflow_stage_override.py:222-234`(ADMIN 이 AS_*/DELETED 로 400), `:169-179`·`:212-220`(ADMIN 역행·skip 403), `:236-253`(AS→메인 jump 200);
`tests/domains/test_state_form.py:380-410`(AS_RECEIVED 400); `tests/domains/test_logistics_dashboard_status.py:124-133`(ADMIN skip 403), `:59-82`(완료 409);
`tests/domains/test_auth_quest_approve.py:131-141`(ADMIN 도 `COMMAND_REQUIRED`); `tests/domains/test_production_start_requires_confirm_quest.py:87-99`;
`tests/domains/test_as_bulk_status_guard.py:72-156`(bulk AS 제외·`include_as`).

## 3. 계약 초안 (이름 고정, CEO 가 규칙 확정)

### C1 한 가지 방식으로만 뚫는다 — `admin_override`
- 요청 본문 공통 키 **`admin_override: true` + `override_reason: "<사유>"`**(둘 다 있어야 한다). role 이 ADMIN 이 아니면 403 `ADMIN_ONLY`. 사유 공백이면 422 `REASON_REQUIRED`.
- **평소 클릭은 지금 그대로 막힌다.** 관리자가 명시적으로 켠 요청만 뚫는다(실수 방지). 화면은 거부 응답을 받은 뒤 "관리자 권한으로 진행" 확인창을 띄워 사유를 받고 같은 요청을 다시 보낸다.
- 판정 헬퍼는 한 곳: 신규 `foms/services/orders/admin_override.py` — `resolve_admin_override(user, payload) -> AdminOverride | None`(`reason`, `actor_id`, `actor_name`), `admin_override_error(...)`(403/422 응답). 라우트는 이 함수만 부른다.

### C2 뚫을 수 있는 게이트 목록(그 밖은 못 뚫는다)
뚫음 허용: 컨펌·생산·CS 퀘스트 승인 게이트, 보류, AS 열림, 시공 증빙, 단계 전제(`INVALID_STAGE`), 도면 수령 확정 전제(`drawing_status`), 도면 단독 승인(`COMMAND_REQUIRED`), 완료 경로(`USE_CS_COMPLETE`), 일반 화면 역행·건너뛰기(`OVERRIDE_BLOCK_MESSAGE`).
**못 뚫음(그대로 유지)**: If-Match/REV 충돌(409), 잠금 아래 `expected_from` 불일치(`StageConflictError`), `to_values` 위반, `confirm != true`, 빈 사유, same 단계, bulk 1000건 상한, 삭제된 주문. 이유: 데이터 정합·동시성 보호는 권한 문제가 아니다.

### C3 강제 단계 변경 = 모든 단계
- `to_stage` 허용 집합을 **본공정 8 + `AS_RECEIVED`·`AS`·`AS_COMPLETED` + `DELETED`** 로 넓힌다(`MAIN_PIPELINE_CODES` 는 그대로 두고 새 상수 `OVERRIDE_TARGET_CODES` 신설).
- **AS 목표**는 raw stage 쓰기가 아니라 AS 축 서비스(`foms/services/orders/as_cycle_service.py`)를 태운다: `AS_RECEIVED`=AS 접수(없으면 새 cycle), `AS`=진행, `AS_COMPLETED`=완료. 본공정 `workflow.stage` 는 유지된다(AS 는 덮어쓰는 축이다). 화면 문구도 "AS 로 보냄"이 아니라 "AS 접수를 연다" 로.
- **`DELETED` 목표**는 `foms/services/orders/soft_delete.py::soft_delete_order` 를 부른다(휴지통행, 복구 가능). 상태 문자열을 직접 쓰지 않는다.
- 되돌아오는 길은 이미 있다(AS→메인 jump 200). 유지.
- bulk 도 같은 집합. **UI 에 `include_as` 체크박스를 추가**한다(서버는 이미 받는다).

### C4 일반 화면 역행·건너뛰기
- `status.py`·`field_update.py` 의 `requires_privileged_override` 분기에서 **관리자 + `admin_override` 면 통과**. 그 외는 지금 문구 그대로.
- 완료(`USE_CS_COMPLETE`)도 같은 규칙. 단 뚫어서 완료로 보낼 때도 **CS 완료 부수효과(시공 시도 종결·이력)** 가 함께 일어나야 한다 — 상태만 COMPLETED 로 바뀌고 뒤가 비면 안 된다. CEO 가 방식을 정한다(권장: 완료 목표는 `cs/complete` 의 서비스 함수를 admin_override 로 재사용).

### C5 기록 — 사유 필수 + 이력 표시
- 뚫린 요청마다 `OrderEvent(event_type="ADMIN_OVERRIDE_USED", payload={gate, route, reason, from, to, actor})` 1행. 기존 전이 이벤트는 그대로 남는다.
- 타임라인 라벨 등재(`foms/services/order_event_display.py`): `ADMIN_OVERRIDE_USED` = "관리자 강제 진행". 변경 설명문에 사유를 붙인다.
- 주문 상세 변경 이력에서 한눈에 보이게(기존 이벤트 렌더 재사용).
- 감사 로그(`SecurityLog`)도 함께.

### C6 화면
- 강제 단계 변경 모달: 옵션에 AS 3종 + 삭제 추가, AS·삭제 선택 시 경고 문구(무엇이 일어나는지 한 줄), bulk 모달에 `include_as` 체크박스.
- 게이트 거부(409/400)를 받은 화면에서 **관리자에게만** "관리자 권한으로 진행" 2차 확인 + 사유 입력 → 같은 요청에 `admin_override` 를 실어 재전송. 사유 입력은 배치 2에서 만든 공용 시트(`templates/partials/shared/foms_reason_sheet.html`, `static/js/foms/foms-reason-sheet.js`)를 재사용한다.
- 비관리자 화면은 바뀌지 않는다(버튼도, 문구도).

## 4. 워커 소유권

| 워커 | 편집 허용 | 금지 |
|---|---|---|
| W1 공통 판정 + 강제 변경 | 신규 `foms/services/orders/admin_override.py`, `foms/services/orders/stage_override.py`, `foms/api/orders/stage_override.py`, 테스트 `test_workflow_stage_override.py`·`test_state_form.py`·`test_as_bulk_status_guard.py` + 신규 `tests/domains/test_admin_override_contract.py` | 생산·시공·CS 라우트 |
| W2 일반 화면 경로 | `foms/api/orders/status.py`, `foms/api/orders/field_update.py`, `foms/services/orders/complete_path_policy.py`, 테스트 `test_logistics_dashboard_status.py`·`test_state_controls.py` + 신규 `tests/domains/test_admin_override_status_routes.py` | stage_override.py |
| W3 업무 게이트 | `foms/api/production/orders.py`, `foms/api/construction/orders.py`, `foms/api/cs/complete.py`, `foms/api/quest.py`, `foms/api/drawing/erp_orders_draftsman.py`, 해당 테스트 + 신규 `tests/domains/test_admin_override_gates.py` | status.py·field_update.py |
| W4 기록·화면 | `foms/services/order_event_display.py`, `templates/orders/partials/erp_stage_override_modal.html`, `static/js/orders/erp-stage-override.js`, 게이트 재시도 JS(`static/js/foms/foms-reason-sheet.js` 재사용), 자산 핀 줄 전부, 테스트 `test_erp_order_shared_form_scripts.py` + 신규 `tests/domains/test_admin_override_ui.py` | API 파일 |

## 5. 검증
```
cd /c/tmp/foms-s-measure-deadend && pwd
python -c "import app; print('APP_OK')"
python -m pytest <자기 테스트> -q -p no:cacheprovider
node --check <건드린 JS>
```
통합: `tests/domains` 전량 -x → `tests/contracts tests/harness tests/services tests/security` → CI 와 같은 `tests/visual` 부분집합 → 인벤토리 4종 재생성 + `--check` → `git diff --stat`.

## 6. 함정
- **`admin_override` 는 권한 축이다. 데이터 정합 축(If-Match·잠금·`to_values`)을 뚫으면 안 된다** — 뚫으면 동시 편집이 조용히 서로를 덮는다.
- 엔진의 `emergency_override` 는 인접성만 푼다. 비인접 전이를 라우트가 허용할 때 그 값을 넘겨야 하고, `reason` 이 없으면 엔진이 409 를 낸다.
- AS 목표를 raw stage 로 쓰면 `workflow.stage` 가 AS 문자열로 오염된다(과거 사고 지점, `state_axes` 의 복구 분기 참조). 반드시 AS 서비스 경유.
- 삭제 목표를 status 문자열로 쓰면 휴지통·복구가 깨진다. `soft_delete_order` 만 쓴다.
- 뚫기 요청도 **감사·이벤트가 먼저**가 아니라 **성공했을 때만** 기록한다(실패한 시도는 SecurityLog 로만).
- 기존 테스트는 "관리자도 막힌다" 를 고정하고 있다 — 지우지 말고 "평소엔 막히고, `admin_override` 면 통과" 두 갈래로 바꾼다(음성 대조군 유지).
- 자산 핀: JS·CSS 를 바꾸면 핀을 올린다(현재 `20260920b`). 핀 줄은 W4 소유.
- 인벤토리 lineno 는 재생성으로 맞춘다.
