# 실측 대시보드 → 도면 전달 버튼 (STATE-CONTROLS-04) — 산출 원장

작성 2026-09-14 · 브랜치 `deploy` · 브리프 `docs/plans/2026-09-14-measure-to-drawing-transfer-button-brief.md`

한 줄 요약: 실측 대시보드 2곳(자가·지방)의 미완료 행에 **본공정 stage 를 MEASURE → DRAWING 으로
넘기는 버튼**을 붙였다. 새 API·새 전이 함수는 없다 — 기존
`POST /api/orders/<id>/quest/approve` 를 그대로 부른다.

---

## 1. 확정 계약 전문

### 1.1 서버 — 권한 술어 SSOT

`foms/services/orders/quest_approve_authz.py` (신규). `foms/api/quest.py` 안에만 있던 판정을
옮긴 **순수 리팩터**다. 화면과 라우트가 같은 함수를 부른다(화면이 서버보다 넓은 버튼을
내밀면 403 사고가 난다 — 2026-09-14 실측 403 과 같은 축).

```python
QUEST_APPROVE_ROLES: tuple[str, ...] = ("ADMIN", "MANAGER", "STAFF")

def find_stage_quest(sd: dict | None, stage_name: str, stage_code: str) -> tuple[dict | None, int]
def required_teams_for_stage(current_quest: dict | None, stage_code: str) -> list[str]
def authorize_quest_approve(
    db, user, order, stage_code: str, current_quest: dict | None, *,
    emergency_override: bool = False, override_reason: str = "",
) -> tuple[bool, int, str]
```

- `foms/api/quest.py` 는 `_authorize_quest_approve` / `_required_teams_for_stage` /
  `_find_stage_quest` 라는 **옛 이름을 같은 객체로 유지**한다(T1 이 못박는다 —
  `tests/domains/test_measure_approval_teams.py` 가 옛 경로로 import 한다).
- `QUEST_APPROVE_ROLES` 비교는 **대소문자 정규화 없이 원문 `in` 튜플**이다.
  `role_required`(`foms/web/auth/routes.py`)가 그렇게 비교하므로 화면도 같아야 답이 같다.

### 1.2 서버 — CTA 빌더

`foms/services/measurement/drawing_transfer_cta.py` (신규, 패키지 `__init__.py` 동반).

```python
def build_drawing_transfer_ctas(db, orders, current_user) -> dict[int, dict]
```

주문 id → `{'visible','enabled','label','confirm','blocked_reason'}` (키 5개 고정, 숨김도
항목은 있다). 판정 순서는 라우트가 실제로 밟는 길과 1:1 이다.

| 단계 | 판정 | 어긋나면 |
|---|---|---|
| 0 | `current_user.role in QUEST_APPROVE_ROLES` | 전부 숨김(라우트는 302 redirect 라 JS 가 못 읽는다) |
| 1 | `get_stage(sd)` 원문 존재 | 숨김(라우트 400) |
| 2 | `STAGE_NAME_TO_CODE` 정규화 결과 == `MEASURE` | 숨김 |
| 3 | `read_main_stage(order) == "MEASURE"` | 숨김(전이 엔진이 `expected_from` 과 비교, 어긋나면 409) |
| 3-b | **`read_as_status(order) not in ("RECEIVED","IN_PROGRESS")`** | 숨김 — 아래 §5 P1-A |
| 4 | 현 단계 quest(없으면 템플릿으로 **표시 전용** 합성, 저장하지 않는다) | 숨김 |
| 5 | `authorize_quest_approve(...)` — 라우트와 같은 술어 | `enabled=False` + `blocked_reason` = 서버 거부 문구 |
| 6 | `quest.approval_mode == "assignee"` | `enabled=False` + `TEAM_MODE_BLOCKED_REASON`(팀 승인은 1인 승인으로 안 넘어간다 — "도면 전달"이라 쓰면 거짓말) |

`label` = `DRAWING_TRANSFER_LABEL` = `"도면 전달"`, `confirm` =
`quest_approve_cta.build_approve_cta(stage_code, order)["approve_confirm"]`.

**추가 DB 쿼리 0회.** MEASURE 가 아닌 행은 stage 판정에서 끊기고, `authorize_quest_approve`
는 `CONSTRUCTION` 일 때만 DB 를 본다. T7 이 `before_cursor_execute` 카운터로 못박는다.

라우트 `foms/web/measurement/dashboard.py` 의 `self_measurement_dashboard()` /
`regional_dashboard()` 두 곳이 render 컨텍스트에 `drawing_ctas` 를 넣는다(버킷 전부 한 번에).

### 1.3 마크업

`templates/partials/shared/status_select_options.html`:

```jinja
{%- macro drawing_transfer_control(order_id, cta) -%}
```

- `cta` 가 없거나 `cta.visible` 이 거짓이면 **아무것도 출력하지 않는다**.
- 출력은 `<button>` **하나뿐** — 새 `<div>` 래퍼 금지(지방 버킷 테스트의 div 깊이 정규식).
- 클래스 `btn btn-sm btn-outline-primary js-drawing-transfer`, 아이콘 `fa-arrow-right`.
  **`btn-outline-info` · `fa-drafting-compass` 는 금지** — 같은 행의 도면 **파일** 뷰어가
  그 조합이다(아래 §5 P2-A).
- `cta.enabled` 가 거짓이면 `disabled` + `title="{{ cta.blocked_reason }}"`.
- 삽입 지점 5곳: self = pending·scheduled(2), regional = 상차알림·진행중·설치예정(3).
  완료·AS 섹션에는 넣지 않는다.

### 1.4 클라이언트

- `static/js/measurement/drawing-transfer-btn.js` (신규, 핀 `?v=20260914a`).
  전역 위임 + `window.__FOMS_DRAWING_TRANSFER_BTN_BOUND` 재바인딩 방지.
  요청은 `POST /api/orders/<id>/quest/approve`, 본문 `{}`. `emergency_override` /
  `override_reason` 는 **보내지 않는다**(ADMIN 전용·감사 의미가 다르다).
  `res.json()` 은 try 로 감싼다(아래 §5 P2-B).
- CSS 는 `static/css/measurement/complete-order-btn.css` 에만 추가(인라인 스타일 금지),
  핀 `?v=20260914a`. 전용 색 `#3949ab`(남보라). 스택 안에서는 `margin-top: 0`.

### 1.5 이름 축 분리 (절대 규칙)

`foms/api/drawing/erp_orders_drawing.py` 의 "도면 전달" = 도면팀이 도면 **파일**을 넘기는
`drawing_status` 축이고 **stage 를 바꾸지 않는다**. 이 기능은 본공정 stage 축이다.
T12 가 JS·서비스 코드 본문에 `drawing_status` / `erp_orders_drawing` 이 없음을 못박는다.

---

## 2. 게이트 원문 결과 (2026-09-14, fix 반영 후 전량 재실행)

```
$ python -c "import app; print('APP_OK')"
APP_OK

$ python -m pytest tests/domains/test_state_controls.py tests/domains/test_regional_dashboard_buckets.py \
    tests/domains/test_regional_dashboard_erp_sync.py tests/domains/test_as_overlay_status_write_guard.py \
    tests/domains/test_measurement_search_xss.py tests/domains/test_erp_orders_structured_put.py \
    tests/domains/test_auth_quest_approve.py tests/domains/test_state_quest.py \
    tests/domains/test_measure_approval_teams.py tests/domains/test_order_status_stage_sync.py -q
130 passed in 5.81s

$ python -m pytest tests/domains/test_measurement_drawing_transfer_button.py -q
52 passed in 2.49s

$ node --check static/js/measurement/drawing-transfer-btn.js
exit=0

$ python -m pytest tests/domains/test_state_guard.py -q      # 원장 드리프트 확인용
11 passed in 10.46s

$ powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1   # 파이프 없이 exit 코드 직독
...
======================= 379 passed, 1 warning in 44.85s =======================
[OK] Pytest subset (21 targets)
=== PRE-PUSH SMOKE PASSED ===
EXIT=0
```

(문서 3개 반영 뒤 pre_push_smoke 를 한 번 더 돌려도 `EXIT=0` /
`=== PRE-PUSH SMOKE PASSED ===`. AI_STATUS 예산은 `tests/harness/test_hook_log_hygiene.py`
15 passed 로 따로 확인.)

음성 대조군(변이 검사): AS 게이트를 `if False:` 로 죽이고 돌리면
`test_cta_hidden_while_as_is_open[RECEIVED-AS_RECEIVED]` · `[IN_PROGRESS-AS]` **2 failed** —
게이트가 실제로 무언가를 막고 있음을 확인한 뒤 원복했다.

---

## 3. 원장(inventory) 파일 판정

| 파일 | 이번 커밋 | 근거 |
|---|---|---|
| `docs/harness/foms_order_mutation_writer_inventory.json` | **넣는다** | `foms/api/quest.py` 508→415 는 이번 세션이 quest.py 에서 권한 술어 93줄을 `quest_approve_authz.py` 로 뺀 결과다(415 는 `order.structured_data = sd`). lineno 를 고정 비교하는 `external_sites` 24건 중 미커밋 파일 entry 는 이 quest.py:415 **하나뿐**임을 직접 세어 확인했다. 같은 파일의 `erp_orders_drawing` 220/523/556 은 lineno 를 안 보는 `writers` 목록에만 있다 |
| `docs/harness/foms_state_writer_inventory.json` | **넣는다** | 워킹트리 판의 `foms/web/orders/listing.py` 346/347 → **353/354** 는 이미 커밋된 코드(커밋 `198d57592`)와 맞추는 순수 원장 복구다. HEAD 판 그대로 두면 `tests/domains/test_state_guard.py::test_no_new_external_writers` 가 red — 남의 red 를 이 푸시가 떠안는다. 워킹트리 기준으로 `test_state_guard.py` **11 passed** 확인 |
| `docs/harness/foms_failopen_inventory.json` | **뺀다** | 이번 작업은 이 파일을 **손대지 않았다**. 워킹트리 diff 는 naver_ingest·context_processors·listing·erp_quest_display·erp_orders_drawing 등 7개 파일의 전면 재생성이고 **다른 창 소유**다. 이 게이트는 lineno 를 보지 않으므로 HEAD 판으로 돌려도 통과한다(13 passed 확인 이력). 다음 사람이 헷갈리지 않도록 여기 남긴다 |

그 밖의 워킹트리 미커밋 변경(`foms/api/drawing/erp_orders_drawing.py`, `static/js/foms/wizard*.js`,
`templates/orders/wizard/*`, `tests/domains/test_state_drawing.py`)은 **이 기능과 무관**하며
손대지 않았다.

---

## 4. 발견 사실 — stage 진입 알림은 지금 배달되지 않는다 (브리프 7-6)

`foms/services/orders/order_transition_service.py:405-419` 이 stage 전이 때
`STAGE_NOTIFICATION` outbox 행을 쓰지만, `tools/ops/run_domain_side_effect_outbox.py:209-217`
에 그 종류의 **핸들러가 없어 DEAD 로 간다**. 즉 이 버튼을 눌러도 도면팀에게 새 알림이
가지는 않는다 — 기존 파이프라인이 하는 만큼만 한다(브리프가 요구한 그대로다).

**이번 범위에서 고치지 않았다.** 새 알림 채널을 만드는 것은 사용자 요구 밖이고, DEAD 로
가는 outbox 는 이 기능보다 넓은 축이다. 별건으로 다뤄야 한다.

---

## 5. 리뷰 findings 와 판정

CEO 가 검증한 fix_list 10건 전부 반영. **코드·문서 편집 8건 + 커밋 pathspec 판정 2건.**
기각한 것은 findings 자체가 아니라 그 안에서 제시된 **대안 구현 2가지**뿐이다(P1-A 의 템플릿
가드, P2-B 의 선례 답습).

### P1-A 채택 — AS 접수 중인 주문에 활성 버튼이 떴다

`foms/web/measurement/dashboard.py` 의 상차 예정 알림 버킷이 `as_orders` 를 다시 담고, AS
전이는 `workflow.stage` 를 건드리지 않는다(STATE-AS-01). 그래서 MEASURE 에서 AS 가 접수된
주문은 `stage=MEASURE` 로 남아 `{'visible': True, 'enabled': True}` 가 나왔고 확인 문구에
AS 라는 말이 한 글자도 없었다. 되돌리기 어려운 stage 전이가 계약 (e) 가 뺀 행에서 일어난다.

수정: `_build_one` 3단계 옆에 **AS 축 게이트**(`read_as_status` ∈ `OPEN_AS_STATUSES`
= `("RECEIVED","IN_PROGRESS")` 이면 `_hidden()`). `read_as_status` 는 `as_lifecycle` 이 없는
레거시 주문도 `status=AS_RECEIVED` 에서 `"RECEIVED"` 를 돌려주므로 두 세대 데이터가 다 막힌다.
DB 쿼리는 늘지 않는다(T7 그대로 0회).

**템플릿에서 `{% if order.status != 'AS_RECEIVED' %}` 로 막는 안은 기각** — 노출 잣대를 서버
한 곳에 모은다는 이 기능의 첫 원칙과 어긋나고, `as_lifecycle` 세대를 못 잡는다.

테스트: `test_cta_hidden_while_as_is_open`(legacy status × as_lifecycle 두 세대 × RECEIVED /
IN_PROGRESS) + 과잉 차단 방지 음성 대조군 `test_cta_visible_after_as_completed`
(`AS_COMPLETED` 는 다시 보인다).

### P1-B 채택 — 산출 원장 부재

이 문서 + `docs/AI_STATUS.md` · `docs/AI_CHANGELOG.md` 각 한 줄.
(AI_STATUS 상단 40줄 예산: 3,901 → 3,998자 / 한도 4,000자.)

### P1-C 채택 — `foms_state_writer_inventory.json` 이 HEAD 에서 이미 red

§3 참조. 워킹트리 판이 옳고, 이번 커밋 pathspec 에 함께 넣는다.

### P1-D 채택 — pre_push_smoke 미실행

돌렸다. `EXIT=0`, 원문 마지막 줄 `=== PRE-PUSH SMOKE PASSED ===` (§2).

### P2-A 채택 — 같은 행에 아이콘·클래스가 똑같은 버튼이 둘

도면 **파일** 뷰어(`btn btn-sm btn-outline-info` + `fa-drafting-compass` + "도면")와 새 버튼이
같은 `<tr>` 안에 나란히 섰다. 코드 축만 갈랐고 사용자 눈에는 안 갈렸다 — 오클릭이 stage 전이를
일으킨다.

수정: 아이콘 `fa-drafting-compass` → **`fa-arrow-right`**(단계 이동), 톤 `btn-outline-info` →
**`btn-outline-primary`** + CSS 에 전용 색 `#3949ab` 명시(hover 시 반전).
T8 의 클래스 검사 문자열 갱신 + 회귀 가드 신설
(`test_macro_button_is_visually_distinct_from_drawing_file_viewer` — `btn-outline-info` ·
`fa-drafting-compass` 부재, `fa-arrow-right` 존재, CSS 에 색, 인라인 스타일 부재).

### P2-B 채택 — `res.ok` 를 안 보고 곧장 `res.json()`

세션이 만료되면 `role_required` 가 JSON 이 아니라 로그인 페이지로 **redirect** 하고 fetch 가
따라가 HTML 을 받는다 → 사용자에게 `Unexpected token '<'` 가 alert 된다. 하루 종일 열어 두는
대시보드라 드문 경로가 아니다.

수정: 파싱을 try 로 감싸고 상태코드별 한글 문장으로 바꾼다
(`res.redirected || 401 || 403` → "로그인이 만료되었습니다. 새로고침 후 다시 시도하세요.",
그 밖은 "서버 응답을 읽을 수 없습니다 (HTTP n)"). 선례 `erp-quest-approve.js` 도 같은 모양이지만
그건 **기존 부채**이고 이번에 한 벌 더 늘리지 않았다(그 파일은 손대지 않았다 — 범위 밖).
테스트 `test_transfer_js_guards_non_json_response`.

### P2-C 채택 — `foms_failopen_inventory.json` 을 통째로 커밋하면 남의 원장을 가져간다

§3 표 참조. 이번 작업은 이 파일을 손대지 않았고, 게이트는 lineno 를 보지 않는다.
커밋 pathspec 에서 뺀다.

### P3-A 채택 — 스택 gap 4px 와 `margin-top` 4px 이 겹쳐 간격이 8px

`.foms-board-status-stack .js-drawing-transfer.btn { margin-top: 0; }` 한 줄.
지방 설치 예정 삽입 지점만 8px 이던 것이 나머지 4곳과 같아진다.
테스트 `test_transfer_button_margin_matches_status_stack_gap`.

### P3-B 채택 — 계약이 지정한 타입 주석 누락

`find_stage_quest` → `tuple[dict | None, int]`, `required_teams_for_stage` → `list[str]`,
`authorize_quest_approve` → `tuple[bool, int, str]`, `build_drawing_transfer_ctas` →
`dict[int, dict]`. `from __future__ import annotations` 가 이미 있어 런타임 영향 없음,
로직 무변경 — 기존 테스트 전량 green 유지.

### P3-C 채택 — T4 가 CTA 를 CTA 자신이 부르는 함수와 비교했다

`test_cta_enabled_matches_server_authorization` 을 다시 썼다. `_MATRIX` 6종을 **케이스마다 새
주문**으로 `client.post('/api/orders/<id>/quest/approve', json={})` 에 실제로 태우고
`cta['enabled'] == (resp.status_code == 200)` 을 확인한다. 허용이면 200 + 전이 후
`read_main_stage == 'DRAWING'`, 거부면 403 + `MEASURE` 유지까지 함께 못박는다.
결과: 허용 4(ADMIN/DELIVERY, MANAGER/SALES, STAFF/CS, STAFF/SALES) · 거부 2(STAFF/DELIVERY,
STAFF/PRODUCTION) — 음성 대조군 2건 이상 강제는 그대로 남겼다.

### 조건부 2건 (커밋 시점의 행위이지 파일 편집이 아니다)

- P1-C·P2-C(원장 pathspec): fix 워커는 git 을 쓰지 않는다. 커밋하는 쪽이 §3 표대로
  `foms_state_writer_inventory.json` · `foms_order_mutation_writer_inventory.json` 은 넣고
  `foms_failopen_inventory.json` 은 빼야 한다.

---

## 6. 실측 성능 수치

CTA 빌더 자체 비용(합성 2,000행, 5회 최소값, `PYTHONPATH=C:/DEV/FOMS`):

| 모집단 2,000행 | AS 게이트 적용 후 | (참고) CEO 사전 실측 |
|---|---|---|
| 전부 MEASURE + quest(최악) | **58.0 ms** | 합성 63.4 ms |
| 전부 비-MEASURE(3단계에서 끊김) | **1.2 ms** | 1.2 ms |
| 전부 AS 접수(3-b 에서 끊김) | **3.1 ms** | — |
| (참고) 실데이터 시드 2,000행 | — | 36.6 ms · `nt.stat` 2,000회 |

- AS 게이트는 비용을 늘리지 않는다 — 오히려 AS 행을 4단계(quest 합성) 앞에서 끊어 3.1ms 로
  떨어뜨린다.
- 실제 대시보드 한 화면의 행 수는 2,000행보다 훨씬 적고, 추가 SQL 은 0회다(T7).
- 성능 축 게이트는 `pre_push_smoke.ps1` 이 강제하며 exit 0 이다(§2).

---

## 7. 다음 사람이 알아야 할 것

1. 노출 잣대는 **서버 한 곳**(`drawing_transfer_cta._build_one`)이다. 템플릿·JS 에 조건을
   새로 만들지 마라. 화면이 서버보다 넓으면 403 사고가 난다.
2. 버튼 톤·아이콘은 계약이다(§1.3). 도면 **파일** 뷰어와 같아지면 오클릭이 stage 를 옮긴다.
3. AS 축이 열려 있으면 stage 컨트롤을 내밀지 않는다 — 대시보드 버킷이 AS 행을 다시 담는다는
   사실을 기억하라(§5 P1-A).
4. `STAGE_NOTIFICATION` outbox 는 여전히 DEAD 다(§4). "도면팀이 알림을 못 받는다"는 제보가
   오면 이 버튼이 아니라 outbox 핸들러 부재를 봐라.
5. 강제 이동(`erp-stage-override.js`)으로 우회하지 마라 — ADMIN/MANAGER 전용이고 `reason` 을
   요구하며 감사 의미가 다르다.

## 운영 반영 (2026-09-14)

- deploy `97adf68e7` CI ALL GREEN. production `4e0e5c24d`(PR #379) 병합, PR 체크 4종(test·harness·perf-gate·pg-lane) pass.
- 스테이징(lahom-dev) 실서버 확인: 자가 보드 버튼 1개·지방 보드 12개 렌더, 실제 왕복 `auto_transitioned: true` / `next_stage: 도면` 확인 후 stage-override 로 원상 복구(주문 #4382).
- 운영 배포 확인: `/static/js/measurement/drawing-transfer-btn.js?v=20260914a` 200, 핸들러·엔드포인트 문자열 포함. 운영 실화면 로그인 확인은 계정 정책상 미실시.
- 승격 경로: `promote_own_to_production.py` 가 `INCOMPLETE: missing baseline deps=228` 로 중단 → origin/production 기준 워크트리에서 직접 cherry-pick(충돌은 AI_STATUS·AI_CHANGELOG 2건뿐, 코드 무충돌) → APP_OK·계약 153 passed·pre_push_smoke EXIT=0 확인 후 PR.
- 푸시 뒤 CI 가 잡은 결함 2건(로컬 게이트가 못 본 것): ① layer dependency ratchet — 술어 추출로 함수 안 지연 import 가 새 위반이 됐다(모듈 상단으로 올림). ② file size ratchet — 새 테스트 860줄 > 임계 500줄(기준선 등록 대신 헬퍼·T1~T7·T8~T12 셋으로 분할). **둘 다 로컬에 없는 게이트였다 — 로컬 deploy 가 원격보다 277 커밋 뒤였기 때문.**
