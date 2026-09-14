# 실측 대시보드 → 도면 전달 버튼 (초안 브리프, CEO 가 확정한다)

작성 2026-09-14 · 브랜치 `deploy` · 이 문서는 **초안**이다. CEO 에이전트는 계약(이름·시그니처)과
워커 브리프를 확정하면서 아래를 고쳐도 된다. 단 §6 소유권 표의 **파일 경계**와 §7 함정은 유지한다.

## 1. 사용자 요구 (확정 · 사용자 답변 2026-09-14)

- 대상 화면 2개: `https://lahom-production.up.railway.app/self_measurement_dashboard`,
  `.../regional_dashboard`.
- 실측이 끝난 주문을 **도면 단계로 넘기는 버튼**을 붙인다.
  - 동작 = **본공정 stage 를 `MEASURE` → `DRAWING` 으로 이동**(사용자 선택: "단계를 도면으로 넘김").
  - 도면팀 알림은 기존 파이프라인이 하는 만큼만. **새 알림 채널을 만들지 않는다**(§7-6).
- 권한 = **실측 주관팀 + 관리자**. 잣대는 서버의 기존 판정과 같아야 한다
  (`resolve_required_approval_teams('MEASURE', ...)` = CS + SALES, 그리고 담당자 승인).
- **한 건씩만.** 체크박스 일괄 전달은 범위 밖.

## 2. 이미 있는 것 (재사용이 기본, 새 API 금지)

실측→도면 전이는 **이미 구현돼 있다**. 태블릿 실측 화면의 "실측 완료 → 도면 전달" 버튼과 같은 길을 쓴다.

| 층 | 앵커 |
|---|---|
| 엔드포인트 | `foms/api/quest.py:336-341` `POST /api/orders/<id>/quest/approve` (`@login_required` + `@role_required(['ADMIN','MANAGER','STAFF'])`) |
| 권한 판정 | `foms/api/quest.py:278-333` `_authorize_quest_approve`, 필수팀 `:270` `_required_teams_for_stage` |
| 전이 | `foms/api/quest.py:519-535` → `foms/services/orders/quest_transition_service.py:167-179` `advance_stage_on_quest_completion` |
| 전이 표 | `quest_transition_service.py:71-74` `_STAGE_ADVANCE["MEASURE"] = ("COMPLETE_MEASUREMENT","MEASURE","DRAWING", False)` |
| 전이 게이트 | `quest_transition_service.py:227-230` + 술어 `:130-139` `_stage_quest_complete` (MEASURE 는 `approval_mode="assignee"`) |
| 화면용 payload | `foms/services/erp_quest_display.py:370-418` `build_current_quest_payload(*, sd, stage, stage_code, order, current_user, user_map)` |
| 배치 user map | `erp_quest_display.py:476` `load_assignee_user_map_batch(db, sds)` |
| 문구 SSOT | `foms/services/orders/quest_approve_cta.py:24-37` — `MEASURE` 라벨 `"실측 완료"`, 확인 `"실측을 완료하고 도면 단계로 넘길까요?"` |
| 선례 버튼(태블릿) | `templates/measurement/partials/tablet_split_body.html:158-161`, JS `static/js/foms/tablet-measure-form.js:1641-1648`, 가시성 `:386-387` |
| 선례 JS(모바일) | `static/js/foms/erp-quest-approve.js:140-171` (confirm → disable → fetch → `data.success` → `data.code` 표면화 → toast → reload) |
| stage 상수 | `foms/services/orders/erp_policy_constants.py:14-26` (`MEASURE`=실측, `DRAWING`=도면), 순서 `foms/services/orders/stage_override.py:42-51` |
| stage 읽기 | `foms/services/orders/state_axes.py:127-140` `read_main_stage` |

**새 Blueprint·새 라우트·새 서비스 전이 함수를 만들지 마라.** 기존 `quest/approve` 를 부른다.

## 3. 대상 화면의 현재 모습

라우트 `foms/web/measurement/dashboard.py`:
- `:999-1043` `self_measurement_dashboard()` — `@login_required` 만. 버킷 pending/scheduled/as/completed.
- `:673-799` `regional_dashboard()` — `@login_required` 만. 버킷 완료/AS/설치예정/상차알림/진행중.
- `:598` `_fetch_legacy_dashboard_orders`, `:746-751` **읽기 경로는 `order.status` 를 쓰지 않는다**(테스트가 강제).

템플릿(둘 다 매크로 없이 `{% for %}` 인라인, `<tr data-order-id=...>`):
- `templates/measurement/self_measurement_dashboard.html` — pending `:219-331`(상태 select `:252-256`,
  실측완료 체크박스 `:261-270`), scheduled `:388-503`(`complete_order_control` `:426`), AS `:558-628`,
  완료 `:682-770`. 스크립트 `:1376` `js/measurement/complete-order-btn.js?v=20260807b`,
  CSS `:7` `css/measurement/complete-order-btn.css?v=20260807d`.
- `templates/measurement/regional_dashboard.html` — 상차알림 `:504-650`, 진행중 `:721-858`,
  AS `:906-935`(`as_complete_control` `:917`), 설치예정 `:988-1106`(`complete_order_control` `:1005`),
  완료 `:1166-1260`. 스크립트 `:2197-2200`, CSS `:7` 동일 핀.
- 공용 매크로 `templates/partials/shared/status_select_options.html:39-50` `complete_order_control`,
  `:64-73` `as_complete_control`, `:86-88` `board_status_badge`. 버튼 클래스 관례
  `btn btn-sm btn-success js-complete-order` + `data-order-id` + `data-confirm`.
- 버튼 JS 선례 `static/js/measurement/complete-order-btn.js:21-59`(전역 위임 + `window.__FOMS_..._BOUND` 재바인딩 방지).
- 버튼 CSS `static/css/measurement/complete-order-btn.css:5-52`(`.foms-board-status-stack` 세로 스택).

## 4. 계약 초안 (이름 고정 — CEO 가 바꾸면 워커 브리프 전체에 반영해야 한다)

### 4.1 서버

새 모듈 `foms/services/measurement/drawing_transfer_cta.py` (패키지 없으면 `__init__.py` 포함):

```python
def build_drawing_transfer_ctas(db, orders, current_user) -> dict[int, dict]:
    """주문 id → {'visible','enabled','label','confirm','blocked_reason'}.

    visible  : 본공정 stage 가 MEASURE 이고 승인 CTA 가 존재할 때만 True.
    enabled  : 서버 `_authorize_quest_approve` 와 **같은 잣대**로 True/False.
    label    : quest_approve_cta 의 문구를 그대로 쓰되 이 화면은 '도면 전달'로 노출한다.
    confirm  : quest_approve_cta 의 확인 문장 + 고객/주문번호.
    blocked_reason: enabled=False 일 때 title 로 보여줄 한 줄(예: '실측 승인 권한 없음').
    """
```

- 권한 잣대 중복 금지: `foms/api/quest.py:278-333` 의 판정을 **import 가능한 술어로 추출**해서 API 와
  화면이 같은 함수를 쓰게 한다(추출 위치는 CEO 판단 — `foms/services/orders/` 아래 권장).
  API 동작은 바뀌면 안 된다(순수 리팩터 + 기존 테스트 green).
- 화면이 서버보다 넓은 버튼을 내밀면 안 된다(2026-09-14 실측 403 사고와 같은 축, `docs/AI_STATUS.md` 상단).
- 성능: 주문 수만큼 쿼리를 돌리지 마라. `load_assignee_user_map_batch` 로 한 번에.
- 라우트 `foms/web/measurement/dashboard.py` 두 곳의 render 컨텍스트에 `drawing_ctas` 를 넣는다.
  버킷 전부(완료 버킷 포함해도 무방 — `visible` 이 걸러 준다)를 한 번에 계산.

### 4.2 마크업

`templates/partials/shared/status_select_options.html` 에 매크로 추가:

```jinja
{% macro drawing_transfer_control(order_id, cta) %}
```
- `cta` 가 없거나 `cta.visible` 이 거짓이면 **아무것도 출력하지 않는다**.
- 출력: `<button type="button" class="btn btn-sm btn-outline-info js-drawing-transfer"
  data-order-id="{{ order_id }}" data-confirm="{{ cta.confirm }}">도면 전달</button>`
- `cta.enabled` 가 거짓이면 `disabled` + `title="{{ cta.blocked_reason }}"`.
- 두 대시보드의 **미완료 섹션 행**에 넣는다(self: pending·scheduled / regional: 상차알림·진행중·설치예정).
  완료·AS 섹션은 넣지 않는다. 기존 `complete_order_control` 이 있는 셀이면 같은
  `.foms-board-status-stack` 안에 쌓는다.

### 4.3 클라이언트

- 새 파일 `static/js/measurement/drawing-transfer-btn.js`, 템플릿 핀 `?v=20260914a`.
  `static/js/foms/erp-quest-approve.js:140-171` 의 요청 본문·성공 판정을 **그대로** 따라간다
  (엔드포인트·payload 를 추측하지 말고 그 파일을 읽어라). 실패 시 버튼 복구, 성공 시 reload.
- CSS 는 `static/css/measurement/complete-order-btn.css` 에 최소 규칙만 추가(인라인 스타일 금지).
  CSS 핀은 `?v=20260914a` 로 올린다.

## 5. 검증 명령 (통합 검증자가 전량 재실행)

```
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_state_controls.py tests/domains/test_regional_dashboard_buckets.py tests/domains/test_regional_dashboard_erp_sync.py tests/domains/test_as_overlay_status_write_guard.py tests/domains/test_measurement_search_xss.py tests/domains/test_erp_orders_structured_put.py tests/domains/test_auth_quest_approve.py tests/domains/test_state_quest.py tests/domains/test_measure_approval_teams.py tests/domains/test_order_status_stage_sync.py -q
python -m pytest tests/domains/test_measurement_drawing_transfer_button.py -q
node --check static/js/measurement/drawing-transfer-btn.js
```

## 6. 파일 소유권 (겹치면 안 된다)

| 워커 | 편집 허용 파일 |
|---|---|
| W1 서버 | `foms/services/measurement/drawing_transfer_cta.py`(신규, 필요 시 `__init__.py`), `foms/web/measurement/dashboard.py`, `foms/api/quest.py`(권한 술어 추출만), 술어를 옮길 새 서비스 파일 1개 |
| W2 마크업 | `templates/partials/shared/status_select_options.html`, `templates/measurement/self_measurement_dashboard.html`, `templates/measurement/regional_dashboard.html` — **JS·CSS 핀 줄도 W2 가 단독으로 편집한다** |
| W3 클라이언트 | `static/js/measurement/drawing-transfer-btn.js`(신규), `static/css/measurement/complete-order-btn.css` |
| W4 테스트 | `tests/domains/test_measurement_drawing_transfer_button.py`(신규) |

**모든 워커 금지**: git 명령, 위 표 밖 파일 편집, 워킹트리의 기존 미커밋 변경
(`foms/api/drawing/erp_orders_drawing.py`, `static/js/foms/wizard*.js`, `templates/orders/wizard/*`,
`docs/AI_*`, `tests/domains/test_state_drawing.py`) 손대기.
공통: CRLF 보존, 첫 명령은 `cd C:/DEV/FOMS && pwd`, docs 를 읽는 테스트 작성 금지.

## 7. 함정

1. **"도면 전달" 이름이 이미 다른 뜻으로 쓰인다.** `foms/api/drawing/erp_orders_drawing.py:329` 의
   도면 전달 = 도면팀이 **도면 파일**을 넘기는 것이고 `drawing_status` 축이며 **stage 를 바꾸지 않는다**
   (`:276-278`, `:601`). 우리 버튼은 본공정 stage 축이다. 코드·주석·테스트 이름에서 둘을 섞지 마라.
2. **`test_state_controls.py:225-234` 는 `complete_order_control(order.id` 등장 횟수 == 1 을 강제한다.**
   새 매크로는 다른 이름이라 안전하지만, 기존 호출을 옮기거나 복제하면 red.
3. **`test_regional_dashboard_buckets.py:90-95` 의 `_order_ids_in_card_class` 정규식은 div 중첩 깊이에
   민감하다**(`.*?</div></div></div>`). 버튼 때문에 섹션 카드의 div 층을 늘리지 마라.
   `:204-218` 은 regional 본문에 `<select ... data-field="status">` 가 없어야 함을 강제한다.
4. `test_as_overlay_status_write_guard.py:167-183` 은 `checkAllCompleted` ~ `syncStatusToShippingDate`
   사이 인라인 JS 본문을 슬라이스해서 검사한다. 그 구간에 새 코드를 끼워 넣지 마라(새 JS 는 외부 파일).
5. `regional_dashboard.html:2195-2197` 에 `erp-stage-override.js` 와 모달이 이미 로드돼 있으나
   트리거가 없어 죽어 있다. **강제 이동(override) 길로 우회하지 마라** — ADMIN/MANAGER 전용이고
   `reason` 을 요구하며 감사 의미가 다르다.
6. **stage 진입 알림은 지금 실제로 배달되지 않는다.** `order_transition_service.py:405-419` 이
   `STAGE_NOTIFICATION` outbox 행을 쓰지만 `tools/ops/run_domain_side_effect_outbox.py:209-217` 에
   핸들러가 없어 DEAD 로 간다. 이번 범위에서 **고치지 않는다**. 발견 사실로 원장에만 남긴다.
7. MEASURE quest 는 `approval_mode="assignee"` 라 담당자 1인 승인으로 완료된다
   (`erp_policy_quests.py:181-193`). 팀 승인 UI 를 새로 그리지 마라.
8. 대시보드 행은 stage 가 MEASURE 가 아닌 주문도 섞여 있다. `visible` 판정은
   `read_main_stage` 결과로만 한다. `order.status`(레거시 축)로 판정하지 마라.
9. Windows: 한글 출력은 UTF-8 강제. 테스트에서 템플릿 문자열 비교 시 CRLF 주의.

## 8. 산출 원장

CEO 판정과 리뷰 findings 는 `docs/plans/2026-09-14-measure-to-drawing-transfer-ledger.md` 에
총괄이 기록한다(워커는 쓰지 않는다).
