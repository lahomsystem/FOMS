# 네이버 워크벤치 — 관계 축 이식 + 판매자 직접취소 (SPEC)

- 상태: 승인됨 (2026-08-22 사용자 결정 4건 + 2026-08-23 취소 범위 확정)
- 선행 스펙: `2026-08-19-naver-order-relation-and-fulfillment_SPEC.md`(관계 축·발주확인/발송처리),
  `2026-08-20-naver-ingest-workbench_SPEC.md`(워크벤치 본체)
- 원장: `docs/plans/2026-08-20-naver-workbench-ledger.md`

## 1. 문제

워크벤치(게이트 ON)에 **관계 축 UI 가 0건**이다(옛 `naver_triage.html` 은 21건). 라우트·판정
로직(`/attach`·`/detach`·`find_order_candidates`·`relation` 컬럼)은 살아 있는데 화면이 없어,
게이트를 켠 계정은 추가결제·재결제 업무를 아예 할 수 없다. 옛 화면으로 돌아갈 경로도 없다
(`/admin/naver-ingest` → 워크벤치 리다이렉트).

덧붙어 **취소**는 어느 화면에도 없다. 네이버 앱 권한에는 취소가 포함돼 있는데(§7.1 선행 스펙),
FOMS 는 발주확인·발송처리만 부른다 — 취소는 판매자센터로 나가야 한다.

## 2. 확정 사항 (사용자 결정)

| # | 결정 | 근거 |
|---|------|------|
| D1 | 발송처리 단독 호출은 **ADDON/REPAY 집에만** 연다. NEW 는 지금처럼 발주확인이 먼저다. | 네이버 발송관리 화면은 발주확인 없이 발송처리를 받는다(사용자 실화면). 다만 NEW 를 열어 두면 실제 출고 전 오조작이 그대로 불가역 호출이 된다. |
| D2 | NEW 집 발송처리는 **버튼을 열되 경고를 강하게** 한다(잠금·체크박스 없음). | 실제 출고 시점에 누를 자리가 이 화면뿐이다. |
| D3 | 붙이기 UI 는 상세 pane **대조표 아래 "관계" 섹션**. | 워크벤치는 대조표가 주인공이다. |
| D4 | 큐 줄 관계 배지는 **ADDON/REPAY 만**(NEW 는 무배지). | 214건 중 대부분이 NEW — 다 붙이면 배지가 무의미해진다. |
| D5 | 취소는 **판매자 직접취소만** 넣는다(구매자 취소요청 승인은 범위 밖). | 이번 세션 범위 확정. |

## 3. 설계

### 3.1 관계 배지 (T-R1)

- `_group_queue()` 결과에 `relation` 을 싣는다 — 집 안 링크 중 `ADDON`/`REPAY` 가 하나라도
  있으면 그 값(둘 다면 `ADDON` 우선). 관계는 집 단위로 붙기 때문에(`attach_link_to_order` 가
  형제 전체를 붙인다) 대표 링크만 봐도 되지만, 부분 백필분을 위해 멤버 전체를 본다.
- 표시: 큐 줄 3층 배지 자리 + 상세 pane 헤더. `NEW`/빈값은 **배지를 내지 않는다**(D4).
- 라벨: `ADDON` = "추가결제", `REPAY` = "재결제". 색은 파랑(info)/보라(secondary) 계열,
  클레임(빨강)·발주확인 전(노랑)과 겹치지 않게.

### 3.2 관계 섹션 — 후보·붙이기·되돌리기 (T-R2)

대조표(집 단위 → 상품주문) **아래** 새 섹션. 세 상태만 있다.

1. `relation` 이 비었고 `order_id` 도 없고 후보가 있다 → 후보 표 + 관계별 붙이기 버튼 2종.
   근거 문구는 옛 화면 그대로: "새 주문이 아니라 기존 주문의 추가결제(차액)거나 취소 후
   재결제일 수 있습니다."
2. `relation` 이 `ADDON`/`REPAY` → 붙어 있는 주문 링크 + [되돌리기].
3. 그 밖(후보 없음·이미 NEW 로 주문 생성) → 섹션을 렌더하지 않는다.

- 붙이기는 **모달 없이** 즉시 실행한다 — `/detach` 로 되돌릴 수 있는 조작이다(불가역 4종
  세트는 되돌릴 수 없는 것에만 쓴다).
- 취소·반품 집의 ADDON 붙이기는 서버가 이미 막는다(`attach_link_to_order`). 화면은 사유를
  그대로 보여준다.

### 3.3 발송처리 관계별 분기 (T-R3)

| 관계 | 발주확인 전 | 발주확인 후 |
|------|-------------|-------------|
| ADDON/REPAY | **[지금 닫기]** 열림 (네이버가 발주확인을 함께 처리한다) | [지금 닫기] |
| NEW | 회색 잠금 + 사유 | [발송처리] + "실제 출고·시공 시점에만" 경고 |

- 서버 가드(`dispatch_order`)도 같은 규칙으로 바꾼다: 집의 관계가 `ADDON`/`REPAY` 면
  발주확인 전이어도 통과, `NEW`(또는 빈값)면 지금처럼 막고 사유를 적는다.
- 네이버가 그래도 거절하면(`104443 발주 상태 확인 필요` 등) 실패 사유가 화면 빨간 줄에
  그대로 남는다 — 조용한 성공은 없다.
- 취소·반품 집은 여전히 아예 열지 않는다(`_claim_guard`).

### 3.4 판매자 직접취소 (T-R4)

**API 정본** (apicenter 2.86.0 `seller-request-cancel-pay-order-seller`):

```
POST /v1/pay-order/seller/product-orders/{productOrderId}/claim/cancel/request
body: { cancelReason*, cancelDetailedReason?, cancelQuantity? }
resp: data.successProductOrderIds[] / data.failProductOrderInfos[{productOrderId, code, message}]
```

- `cancelReason` 코드: `INTENT_CHANGED`(구매 의사 취소) · `COLOR_AND_SIZE`(색상 및 사이즈 변경) ·
  `WRONG_ORDER`(다른 상품 잘못 주문) · `PRODUCT_UNSATISFIED`(서비스 불만족) ·
  `DELAYED_DELIVERY`(배송 지연) · `SOLD_OUT`(상품 품절) · `INCORRECT_INFO`(상품 정보 상이).
- **상품주문 1건씩** 부른다(발주확인·발송처리와 달리 배치가 아니다). 집 단위로 돌며 건별
  성공/실패를 기록한다.
- 멱등: 링크 상태에 `canceled_at` 을 적고, 값이 있으면 다시 부르지 않는다(발주확인·발송처리와
  같은 규칙). 이미 발송처리된 집은 취소하지 않는다(네이버도 거절한다) — 화면에서 먼저 막는다.
- 출구는 WORKER 단일(IP 3슬롯). web 은 enqueue 만 한다.
- 화면: 상세 pane 헤더 [취소처리] + 불가역 4종 세트 모달(건수 재진술 · 되돌릴 수 없음 ·
  사후 경로 · 사유 선택). 사유는 select(7코드) + 상세 사유 입력(선택, 500자).
- 라우트: `POST /admin/naver-ingest/<link_id>/cancel` — 새 mutation 이므로
  write_guard·order_mutation_policy manifest 2종 + 감사 라벨(`NAVER_INGEST_CANCEL_ENQUEUE`) +
  audit coverage 재생성까지가 한 세트다.
- FOMS 주문이 붙어 있어도 **FOMS 주문은 건드리지 않는다**(네이버 쪽만 취소). 주문 취소는
  주문 화면의 일이다 — 두 곳에서 상태를 쓰면 SSOT 가 갈린다.

## 4. 비목표

- 구매자 취소요청 **승인/거부**(`claim/cancel/approve`) — 다음 세션.
- 반품·교환 처리, 발송지연 처리.
- 추가결제 금액의 출고가·잔금 자동 반영(선행 스펙 Q1 그대로 "기록만").

## 5. 위험

- **R1** 발송처리 단독 호출이 네이버에서 거절될 수 있다(문서에 자동 발주확인 명시 없음).
  → ADDON/REPAY 로만 한정했고, 실패는 사유와 함께 남는다. 실호출 1건으로 사용자가 확인한다.
- **R2** 취소는 되돌릴 수 없고 정산에 바로 영향을 준다. → 모달 4종 세트 + 발송처리 완료 집
  차단 + 집 단위 재진술.
- **R3** 화면이 늘어 상세 pane 이 길어진다. → 관계 섹션은 해당 상태에서만 렌더한다.

## 6. 완료 기준

- `pytest tests/services/integrations` 전건 green + PG 레인.
- 게이트 off(옛 화면) 경로 계약 테스트 그대로 green.
- `APP_OK` · `scripts/ops/pre_push_smoke.ps1` exit 0.
- 1440 실브라우저에서 관계 배지·붙이기·되돌리기·발송처리 분기·취소 모달 확인.
