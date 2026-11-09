# 협력사 "도면 확인했어요" 때 진행할 도면 고르기 — 설계서 (2026-11-09)

판정: 승인(사용자 2026-11-09 "이대로 만들기") · 구현 deploy

## 1. 왜

정명근라운즈(협력사)가 채널톡으로 "김세아 2개 중 1번 지워 주세요, 2번 슬라이딩만 진행" 을 보냈다.
우리 영업은 "도면 수령 확인" 확정 창에서 최종 생산 도면을 고를 수 있다
(`foms/api/drawing/erp_orders_draftsman.py:344`, `plan_partial_confirm`).
협력사 "도면 확인했어요"(`foms/services/partners/drawing_confirm.py:173`)는 같은 `record_drawing_receipt`
를 타지만 `partial_plan` 을 넘기지 않는다 — 받은 도면이 전부 최종이 된다.

## 2. 바꾸는 것

### 2.1 서버
- `POST /partner/api/orders/<id>/drawing-receipt` 가 JSON 본문 `{"final_drawing_keys": [...]}` 를 받는다(선택).
  본문이 없거나 키가 없으면 지금과 똑같다(전체 확정).
- `confirm_partner_drawing_receipt(db, user, order_id, final_drawing_keys=None)`:
  1. 협력사가 고를 수 있는 key = `final_drawings_for_partner(order)` 의 key 뿐. 그 밖의 key 가 오면 400
     "지금 도면 목록에 없는 도면이 있어요. 화면을 새로 고쳐 주세요."
  2. 협력사 화면에 안 보이는 줄(`_is_drawing_key` 가 거짓인 `drawing_current_files` 줄 — 협력사 초안 등)은
     협력사 선택과 무관하게 **자동으로 선택에 넣는다** — 협력사가 못 보는 줄을 지우지 않게.
  3. `plan_partial_confirm(sd, 합친 key, None)` → `record_drawing_receipt(..., partial_plan=plan)`.
     품목 취소(`cancel_items`)는 이번 범위 밖 — 협력사에게 열지 않는다.
  4. `PartialConfirmError` 는 `PartnerConfirmError`(400, 같은 문구)로 바꿔 화면에 보인다.
  5. 감사 `PARTNER_DRAWING_RECEIVED` detail 에 `final_drawing_keys`·`excluded_keys` 를 남긴다.
- 뺀 도면 처리는 영업 확정과 같다(`apply_partial_confirm` — 현재본에서 빠지고 이력엔 남음,
  2026-09-30 "ERP 에는 최종본만" 결정과 같은 축).

### 2.2 화면 (협력사 주문 상세)
- 도면이 **2장 이상**일 때만 도면 목록 바로 아래에 "진행할 도면" 체크 줄(`N번 · 파일명`, 기본 전부 켜짐)을 둔다.
  새 창을 띄우지 않는다 — 그림은 바로 위 갤러리에 이미 번호와 함께 보인다(기존 칸 하나만 바꾸기).
  "도면 확인했어요" 를 누르면 확인 문구가 "1번 도면만 진행합니다. 2번 도면은 빠지고 만들지 않습니다." 로 바뀐다.
  하나도 안 고르면 보내지 않고 "진행할 도면을 하나 이상 골라 주세요." (`static/js/partner/partner-receive-pick.js`).
- 1장이면 지금처럼 바로 확인 문구만.
- 목록 화면(`turn_board.html`)의 "확인했어요" 는 도면 2장 이상이면 상세 도면 탭으로 보낸다(목록에서 고르기 창은 안 만든다).
- 기존 칸·모양을 쓴다. 인라인 스타일 없이 `erp-pro.css`/협력사 CSS 에 클래스만.

## 3. 안 바꾸는 것
- "이대로 만들어 주세요"(`approve_partner_drawing`) — 그대로.
- 우리 영업 확정 창·API — 그대로.
- 이미 받음을 누른 주문은 대상 아님(그때는 지금처럼 채널톡 → 우리 처리 또는 수정 요청).

## 4. 시험 (완료 기준)
- 단위: 본문 없음 = 전체 확정(회귀) · 2장 중 1장 선택 → 현재본 1장·제외 1장 · 협력사 초안 줄은 선택 없이도 남음 ·
  남의/없는 key → 409 · 빈 목록 → 400 `NO_FINAL_DRAWING`.
- 바뀐 파일에 닿는 기존 시험: `tests/` 의 partner drawing confirm·partial confirm 묶음.
- 실화면: 스테이징 협력사 계정으로 2장 주문 받음 → 1장만 남는지, 우리 ERP 도면 목록·생산 화면에서 1장만 보이는지.
- `python -c "import app; print('APP_OK')"`.

## 5. 고칠 파일(예상)
- `foms/services/partners/drawing_confirm.py`, `foms/api/partner/__init__.py`
- `templates/partner/partials/order_actions.html`, `templates/partner/partials/turn_board.html`
- 협력사 JS 한 개(받음 단추 처리하는 곳) + CSS 클래스
- 새 시험 파일 1개
