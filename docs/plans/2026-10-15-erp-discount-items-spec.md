# ERP 주문 할인 항목별 입력 — Spec (2026-10-15)

목업: `docs/design/mockups/erp-discount-items-mockup.html`

## 목표
주문 편집(PC·모바일·실측 대시보드 편집)에서 할인을 "이름 + 금액" 줄로 여러 개 넣는다.

## 데이터
- `structured_data.payment.discounts = [{"label": str, "amount": int}, ...]` 를 새로 둔다.
- `payment.discount` 는 **항상 discounts 합계로 같이 저장**한다. 그래서 잔금·견적·정산·결제 동기화
  (`estimate_service._extract_discount_amount`, `order_payment_sync`, `structured_form_projection`,
  `erp_display`, `settlement_aggregation`)는 고치지 않는다.
- 옛 주문(discount 숫자만, discounts 없음): 화면에 "할인" 이름 한 줄로 보여 준다. 저장 전까지 데이터는 그대로.
- 빈 줄(금액 0)은 저장하지 않는다. 이름이 비면 "할인".
- 마이그레이션 없음(JSONB 안 키 추가).

## 서버
- 저장 경로(`foms/api/erp_orders_structured.py`): discounts 가 오면 정리(금액 정수화·음수/0 제거·최대 20줄·이름 64자)하고 discount 를 합계로 다시 계산한다(클라이언트 합계 불신).
- `structured_diff`: `payment.discounts` 변경을 "할인 내역" 한 줄로 요약(배열 원문 노출 금지).

## 화면
- PC `erp_order_tab.html`, 모바일 `erp_order_tab_mobile.html`, 실측 `measurement/partials/dashboard_main.html`:
  `#erp-discount-amount` 한 칸 → `#erp-discount-list` + "+ 할인 추가" 버튼 + 합계 표시.
  합계는 숨은 `#erp-discount-amount`(읽기 전용) 에 계속 써서 기존 계산·자동저장 코드가 그대로 돈다.
- 모바일: 줄마다 카드(이름 위·금액 아래·지우기 44px), 입력 16px. 목업의 이름 칩·하단 입력창은 1차에서 뺐다.
- `erp-order-shared.js`: 목록 그리기·읽기·저장 페이로드에 discounts 추가. `erp-order-autosave.js` 스냅샷 복원 포함.
- 태블릿 실측 폼(`tablet-measure-form.js`)은 이번 범위 밖 — 합계 칸 그대로. 합계를 안 바꾸고 저장하면 서버가 목록을 되살리고, 바꾸면 숫자가 이긴다(목록 삭제).
- 인라인 스타일 금지 → CSS 파일에.

## 변환·PUSH 텍스트
- 바꾸지 않는다. 지금 본문에는 할인 줄이 없고 출고가가 이미 할인을 뺀 값이다(구현 중 확인).

## 검증
- 단위: 서버 정리 함수, diff 요약, 옛 주문 호환.
- 계약 테스트: 템플릿 3곳 id, JS 페이로드, 자산 핀.
- 실화면: 로컬 dev 에서 PC·모바일 추가/삭제/저장/새로고침 후 잔금 일치.
