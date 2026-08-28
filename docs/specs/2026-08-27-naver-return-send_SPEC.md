# T8 — 네이버 반품 전송 (FOMS → 커머스API) 설계

> 2026-08-27 작성. 앞선 판정: `docs/plans/2026-08-26-naver-followup-multiagent-ledger.md`
> §T8 착수 게이트(1차 "통로 모름" → 2차 "절반" → **3차 "4개 중 3개 열림"**).
> 값어치 판정은 사용자 답으로 이미 끝났다 — **연 10건 이상**.

## 0. 한 줄

> **2026-08-27 갱신 — 게이트 4개가 전부 닫혔고 R1~R9 를 배선했다.** Q1(권한 화면)은
> 사용자 확인으로 열렸다(§1). 아래 본문은 착수 시점 기록이며, 구현 결과는 원장
> `docs/plans/2026-08-26-naver-followup-multiagent-ledger.md` §4차 세션에 있다.

**착수를 막던 것은 게이트 ② 하나(권한 화면 1회 확인)였다.** 나머지 물리적 조건
셋은 스테이징 실데이터가 답했다. 다만 **FOMS 버튼 하나로 반품이 끝나는 갈래는 없다** —
네이버가 `요청`과 `승인`을 갈라 놓았고, 그 사이에 **우리 차량 회수와 사람 검수**가 있다.

## 1. 게이트 현황

| 게이트 | 판정 | 근거 |
|---|---|---|
| ① 판매자가 **먼저 접수**할 수 있는가 | **확인** | [실측] `return` 33건 중 **24건이 `requestChannel:"판매자"`** · [문서] #2281·#3106·#1457 |
| ② 우리 앱 권한 그룹에 반품 포함인가 | **확인 (2026-08-27)** | [화면] `주문 판매자` 그룹 · 리소스 유형 `모든 리소스 유형` · 엔드포인트 목록에 **`POST /v1/pay-order/seller/product-orders/{productOrderId}/claim/return/request`** 명시(`return/approve`·`reject`·`holdback`·`holdback/release` 도 함께). 인증 기한 2027-02-10~02-23. **설명 문구에는 '반품'이라는 낱말이 없다 — 문구로 판정했으면 오판했을 자리다** |
| ③ **자사 회수**(택배사·송장 없음)를 받는가 | **확인** | [실측] `collectDeliveryMethod: RETURN_INDIVIDUAL` 28건, `collectTrackingNumber` **33건 전부 없음**, 전부 `RETURN_DONE` 완주 |
| ④ `DIRECT_DELIVERY`/`NOT_TRACKING` 이 조건을 만족하는가 | **확인** | [실측] 배송 블록 **177건 전부** 그 조합, 그중 33건 반품 완료 |

**[실측]은 판매자센터(사람) 경로의 결과다 — API 통로의 가능성을 증명하지 않는다.**
물리적 가능성이 닫혔고, ②가 화면으로 닫히면서 통로도 닫혔다. **남은 것은 실호출 1건**
(§6 Q4) — 권한이 붙어 있다는 것과 우리 body 가 200 을 받는다는 것은 아직 다른 사실이다.

## 2. 설계를 강제하는 사실 4가지

1. **2단계다.** #3106 네이버 답변 — 판매자 반품 요청은 `RETURN_REQUEST` 까지고
   "이후 **자동으로 반품 완료 처리 되지 않습니다**". 실측 33건이 전부 `RETURN_DONE` 인 것은
   **사람이 센터에서 승인**했기 때문이다.
2. **코드 오값 = 불가역 사고.** #2580 — `RETURN_DESIGNATED`/`RETURN_DELIVERY` 를 보내면
   **API 값이 무시되고 상품에 설정된 택배사가 고객 집으로 자동 수거**를 간다.
   `RETURN_INDIVIDUAL` 만 이 동작에서 제외된다.
3. **접수 후 API 정정 불가.** #3656 — "반품 요청된 경우 커머스API 로 수거 송장 정보를
   변경할 수 없습니다." 기존 불가역 3종과 동급 이상.
4. **`requestChannel` 로 우리 것을 구분할 수 없다.** #3106 에서 질문자가 정확히 그것을
   물었고 네이버는 "판매자가 요청해도 **구매자 요청과 동일하게** 신규 클레임 생성"이라
   답한 뒤 후속 구분 질문에는 무답. `returnReason` 도 취소 7종과 값이 다르다.

## 3. 범위 — 무엇을 만들고 무엇을 안 만드는가

전체 흐름: `접수` → `수거정보` → **`실제 회수(우리 차량)`** → **`검수(사람)`** → `승인·환불`.
**가운데 셋은 버튼으로 못 만든다.** 그래서 이번 범위는 **맨 앞 한 칸**이다.

| 단계 | 이번 범위 | 이유 |
|---|---|---|
| 반품 **요청** (`RETURN_REQUEST`) | **만든다** | 판매자센터를 열지 않고 FOMS 에서 접수. 관측된 반품 33건 중 24건이 판매자 접수였다 — 다만 **그 33건은 접수→완료 median 60초·min 16초라 시험 거래로 보인다.** 비율을 업무량 근거로 쓰지 마라(연 건수는 사용자 답 "10건 이상"이 정본) |
| 수거 (우리 차량) | 안 만든다 | 물리 행위 |
| 검수 | 안 만든다 | 사람 판단 |
| 반품 **승인**(환불 확정) | **안 만든다 (이번엔)** | 돈이 나가는 자리. 사람이 판매자센터에서. → §6 Q5 |
| 보류/보류해제/거부 | 안 만든다 | 요청 경로가 안정된 뒤 |

**읽기(S0)는 이미 운영에 있다** — 반품 축 표시·라벨 7종. 그것을 먼저 배포한 것이 옳았다.

## 4. 조각 (T4 다시 읽기와 같은 골격)

네이버 HTTP 는 **WORKER 전용**이다(호출 IP 3슬롯 계약). web 은 enqueue 만 한다.

| # | 조각 | 자리 | 비고 |
|---|---|---|---|
| R1 | `RETURN_REASONS` 화이트리스트 + `COLLECT_METHOD = "RETURN_INDIVIDUAL"` **상수 1값 고정** | `naver_commerce/fulfillment.py` | `CANCEL_REASONS` 패턴. **다른 회수방법 코드는 코드에 존재조차 시키지 않는다**(§2-2). **구현 완료 — 2026-08-27 갱신.** Q3 이 11종 공식 범례로 답하면서 최초 목록의 `WRONG_DELAYED_DELIVERY` 가 **범례 밖(못 보내는 코드)**임이 드러났다 — 스테이징에서 실측됐다는 것은 네이버가 **읽기로 준** 값이었을 뿐이다(§6 Q3). 최종 `RETURN_REASONS` 는 실제 업무 3종을 2코드로 담는다: 변심·주문취소·재결제는 `INTENT_CHANGED`, 색상·사이즈 변경은 `COLOR_AND_SIZE`(사용자 결정 2026-08-27). 범례 11종 전체는 `OFFICIAL_RETURN_REASONS` 로 별도 상수화, 계약 테스트 3종(범례 포함 검사·`WRONG_DELAYED_DELIVERY` 재유입 금지·업무 사유만)이 재발을 막는다 |
| R2 | `request_return(session, client, *, link_id, reason, detail, actor_user_id)` | `naver_commerce/fulfillment.py` | `cancel_order`(`:704`) 를 본뜬다. 응답이 취소와 동형(`successProductOrderIds`/`failProductOrderInfos`)이라 **`_split_result`(`:320`) 재사용** |
| R3 | 가드 3겹 | 같은 파일 | ① 이미 클레임 진행 중이면 거절(`_claim_guard`) ② **발송처리 전이면 거절** — 안 나간 물건은 반품이 아니라 취소다(`cancel_order:741` 의 거울) ③ **우리 표식 멱등**(`triage_state['return']['requested_at']`) |
| R4 | 자기표식 | `triage_state['return']` | **`requestChannel` 에 기대지 않는다**(§2-4). 취소의 `_is_our_cancel`(`claim_watch.py:201·349`) 과 같은 방식 — 안 그러면 우리가 넣은 반품이 우리에게 클레임 알림으로 되돌아온다 |
| R5 | 큐 | `jobs/queue.py` `enqueue_naver_return` | **구현 완료.** 별도 태스크를 파지 않고 **취소와 같은 `run_naver_fulfillment_task` 에 `action="return"`** 으로 태웠다 — 그 자리의 `except FulfillmentError` 커밋 규율(실패 사유를 DB 에 남긴다)을 두 벌로 만들지 않으려는 것이다 |
| R6 | 라우트 | `POST /admin/naver-ingest/<link_id>/return` | **구현 완료.** 신규 mutation 계약은 4종이 아니라 **5종**이었다: policy manifest · write guard manifest · audit coverage inventory · 감사 라벨 `NAVER_INGEST_RETURN_ENQUEUE` · **그 테스트가 `docs/` 를 읽으면 `ci.yml` 문서 전용 서브셋 등재**(CI-DOCSCOPE-01). 다섯째는 `pre_push_smoke` 사각이라 CI 가 처음 잡았다 |
| R7 | 화면 | pane 버튼 + **확인 모달** | 모달이 재진술할 것: **되돌릴 수 없다 · 접수 후 API 로 정정 불가(§2-3) · 승인은 판매자센터에서 사람이 · 회수는 우리 차량** |
| R8 | 진행 표시 | `_fulfillment_state.rev` 지문에 `return.requested_at` 추가 | **구현 완료.** T4 가 `claim_sync.refreshed_at` 로 한 것과 같은 수법 — **새 엔드포인트 0**. `returned` 카운트도 함께 나간다(폴링 키 집합 계약 테스트 갱신) |
| R9 | 테스트 | 서비스(가드 3겹 · 멱등 · 화이트리스트 거절) · 라우트(권한·계약) · 큐 | 빨강 먼저 |

**핵심 규율**: `refresh_claims` 는 이번에도 **한 줄도 안 고친다**. 반품 접수 뒤 상태 추적은
이미 있는 클레임 동기화가 한다.

## 5. 불가역 등급

발송처리·취소와 **같은 등급 이상**이다. 접수하면 구매자에게 반품 진행이 보이고,
API 로는 되돌릴 수 없다(§2-3). 그래서:

- 확인 모달 **필수**(T4 다시 읽기와 다르다 — 그건 되돌릴 게 없어 모달이 없었다)
- 실패 사유는 **막힌 건에만** 찍는다(`_mark_failures` 규율)
- `RETURN_INDIVIDUAL` 외의 값은 **화이트리스트에서 튕긴다** — 코드에 상수로도 두지 않는다

## 6. 착수 전 사용자가 답해야 할 것

> **Q1 하나만 착수를 막는다.** 나머지는 구현 입력값·업무 규칙이다.

**Q1 — 답 나왔다 (2026-08-27, §1 게이트 ② 참조). 아래는 물었던 내용이다.** 커머스API센터 → [애플리케이션 관리] → 우리 앱 → [API 그룹]
에서 `주문 판매자` 행을 편다. (a) 리소스 유형이 **`모든 리소스 유형`** 인가 (b) 그룹 이름·설명이
**'반품'을 포함**하는가 (c) **만료일**은 언제인가(스테이징 `NAVER_COMMERCE_APP_EXPIRES_ON`
미등록 → D-7 경고 미발동).

**Q2 (구현 전제) — [API 문서] `[주문] 반품 요청` 의 '사전 조건' 절.** 어떤
`productOrderStatus` 에서 호출 가능한가(구매확정 후 불가 문장이 있는가). `collectDeliveryMethod`
가 required 인가.

**Q3 — 답함 (2026-08-27).** `returnReason` 코드 표 전체는 취소 7종(`CANCEL_REASONS`)과
**완전히 다른 목록**이었다. 네이버 직원 답변 [#639](https://github.com/commerce-api-naver/commerce-api/discussions/639) 가
판매자가 **보낼 수 있는** 반품 사유 범례 11종을 제시했다:

| # | 코드 | 우리가 보내는가 |
|---|---|---|
| 1 | `INTENT_CHANGED` | **보낸다** — 변심·주문 취소·재결제 |
| 2 | `COLOR_AND_SIZE` | **보낸다** — 색상·사이즈 변경 |
| 3 | `WRONG_ORDER` | 안 보낸다(실물 없음) |
| 4 | `PRODUCT_UNSATISFIED` | 안 보낸다 |
| 5 | `DELAYED_DELIVERY` | 안 보낸다 |
| 6 | `SOLD_OUT` | 안 보낸다 |
| 7 | `DROPPED_DELIVERY` | 안 보낸다 |
| 8 | `BROKEN` | 안 보낸다 |
| 9 | `INCORRECT_INFO` | 안 보낸다 |
| 10 | `WRONG_DELIVERY` | 안 보낸다 |
| 11 | `WRONG_OPTION` | 안 보낸다 |

**`WRONG_DELAYED_DELIVERY` 는 이 범례에 없다** — 스테이징 실측 18건은 네이버가 **읽기로 준**
값이었을 뿐, 판매자가 보낼 수 있는 코드가 아니었다. R1 최초 구현이 이 값을 "실물로 관측된 2개"
중 하나로 넣었던 것이 바로 이 함정이다(스냅샷에서 봤다 ≠ 보낼 수 있다 —
[#1137](https://github.com/commerce-api-naver/commerce-api/discussions/1137)). 릴리즈 노트
[#705](https://github.com/commerce-api-naver/commerce-api/discussions/705) 는 이런 사고가 실제로
있었다고 확인한다: "반품 요청 또는 취소 요청 시 대상 주문건의 클레임 요청 사유 중 **실제 사용이
불가능한 코드가 포함되어 제공된 것을 확인**하였습니다." 우리는 반품 접수 실호출이 0회라 이 400 을
아직 만난 적이 없다.

**반품 배송비 귀책은 사유 코드로 갈린다** — 이건 코드가 아니라 업무 규칙이었다.
[#1170](https://github.com/commerce-api-naver/commerce-api/discussions/1170): "클레임 사유에 따라
대상 클레임의 귀책 주체를 판별하며 귀책 주체에 따라 클레임 배송비의 부담자가 결정됩니다."
`INTENT_CHANGED`·`COLOR_AND_SIZE` 둘 다 **구매자 귀책** — 실물 회수가 없는데도 반품배송비가
구매자에게 청구될 수 있다는 뜻이다. 실제 청구 여부는 상세 응답의 `claimDeliveryFeeDemandAmount`
로만 판정한다(실물 1건 때 확인 — §6 Q5 와 연결).

최종 결론: 우리가 **보내는** `RETURN_REASONS` 는 여전히 2코드다(`INTENT_CHANGED`·
`COLOR_AND_SIZE`) — 다만 그 2코드의 정체가 바뀌었다(`WRONG_DELAYED_DELIVERY` 아웃,
`INTENT_CHANGED` 인). 11종 범례 전체는 `OFFICIAL_RETURN_REASONS` 로 상수화해 화이트리스트
확장의 상한선으로 남긴다.

**Q4 (검증) — 스테이징 실호출 1건.** 가상 주문에 WORKER 에서 `RETURN_INDIVIDUAL` 로 1회
접수 → 상세 재조회로 `requestChannel` 실값과 `claimStatus` 가 `RETURN_REQUEST` 에서 멈추는지.
**실주문이 필요하다(가상주문으로 못 한다) — 대상은 사용자가 고른다.**

**Q5 (업무 규칙 — 사람만 답한다)**
- 회수 뒤 **반품 승인(환불 확정)을 FOMS 가 누를 것인가**, 판매자센터에 남길 것인가?
  (`요청`만 API 로 보내고 `승인`은 사람이 — 가장 작고 되돌리기 쉬운 1단계)
- 반품 배송비를 누구 부담으로 접수하는가. 그 선택을 화면에서 고르게 할 것인가?
- 우리 스토어 상품의 **'반품/교환 택배사'** 설정값은 무엇인가?
  (`RETURN_INDIVIDUAL` 이면 무관하지만, 코드를 잘못 보냈을 때 **어디로 택배차가 가는지** 다.)

## 7. 아직 모르는 것 (정직하게)

- **`returnInfo`·`exchange` 블록은 여전히 미관측**(스테이징 0건). `return` 만 실물이다.
- **`COLLECTING`·`COLLECT_DONE` 진행 중 반품을 아직 못 봤다** — 관측된 33건은 전부
  `RETURN_DONE`(끝난 것). 진행 중 화면은 실물로 검증되지 않았다.
- `반품 요청` body 의 정확한 필수 필드 집합은 apicenter(로그인·JS 필요)라 **미확인** → Q2.
- `requestChannel` 이 API 접수분을 구분해 주는지 **미확인** → Q4. **구분해 주더라도 R4 자기표식은
  남긴다**(문서가 보증하지 않는 값에 불가역 경로를 걸지 않는다).
