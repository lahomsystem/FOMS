# 네이버 수집 — 필드 인벤토리 (무엇이 오고, 무엇을 쓰고, 무엇을 버리는가)

> 2026-08-25 작성. 근거는 **추정이 아니라 스테이징 실데이터 전수**다
> (`external_order_links.raw_snapshot` 281건 · 상품주문 단위). 옆의 `n/281` 은
> "그 필드에 빈 값이 아닌 값이 실제로 들어온 건수"다.

## 0. 세 줄 요약

- 네이버 원본은 **통째로 보관**된다(`raw_snapshot` JSONB). 즉 **버리는 값은 없고**,
  "안 쓴다"는 건 화면·ERP 필드로 **올리지 않았다**는 뜻이다. 나중에 재처리로 살릴 수 있다.
- 지금 ERP 로 올라가는 것은 **사람·주소·품목·금액·상태** 축이다.
- 안 올린 것 중 값나가는 것은 **정산 축**(수수료·정산예정액 분해)과 **부분취소 잔여 축**
  (`remain*`), 그리고 **배송 축**(`delivery.*`)이다.

---

## 1. 지금 쓰는 것 (수집 → ERP/화면)

### 1.1 사람 · 연락처

| 원본 필드 | 실데이터 | 어디로 가나 |
|---|---|---|
| `productOrder.shippingAddress.name` | 281/281 | 고객명(`Order.customer_name`) |
| `productOrder.shippingAddress.tel1` | 281/281 | 고객 전화(`Order.phone`) |
| `productOrder.shippingAddress.tel2` | 8/281 | `parties.customer.phone2`(도크에 복사 버튼) |
| `order.ordererName` · `ordererTel` | 281/281 | `parties.buyer` — 대리주문 판별 |

### 1.2 주소 · 좌표

| 원본 필드 | 실데이터 | 어디로 가나 |
|---|---|---|
| `shippingAddress.baseAddress` + `detailedAddress` | 281/281 | `site.address_full`(합본 1벌 — 정본 형태) |
| `shippingAddress.zipCode` | 281/281 | `site.zip_code` |
| `shippingAddress.latitude` · `longitude` | 281/281 | `naver.latitude/longitude`(참고용. `Order.lat/lng` 에는 안 넣는다) |
| `productOrder.shippingMemo` | 82/281 | 배송메모 — **실위치·요청사항이 여기 온다**(도크 표시) |

### 1.3 품목 · 금액

| 원본 필드 | 실데이터 | 어디로 가나 |
|---|---|---|
| `productName` · `productOption` | 281 / 280 | 품목명·옵션 원문(규격은 사람이 읽고 채운다 — 자동 파싱 금지) |
| `quantity` · `totalPaymentAmount` | 281/281 | 수량·금액 |
| `unitPrice` · `optionPrice` | 281/281 | 결제 상세(옵션가는 **음수도 온다**: 실데이터 `-27500`) |
| `productDiscountAmount` | 281/281 | 할인 합계 |
| `expectedSettlementAmount` | 281/281 | 정산예정액 |
| **`appliedCoupons[]`** | **50/281** | **쿠폰 — 2026-08-25 부터 장수·할인액·판매자 부담분을 화면에 낸다** |
| `appliedCardPromotion` | 1/281 | 카드사 프로모션(2026-08-25 추가) |
| `productClass` | 281/281 | 본품 / 추가구성상품 판정 |
| `sellerProductCode` | 219/281 | 판매자 상품코드 |
| `productId` · `originalProductId` · `itemNo` | 281/281 | 상품 식별자(자동화 기초) |
| `inflowPath` | 281/281 | 유입경로 |

### 1.4 상태 · 일정

| 원본 필드 | 실데이터 | 어디로 가나 |
|---|---|---|
| `order.orderDate` | 281/281 | 접수일·접수시각 |
| `order.paymentDate` · `paymentMeans` · `payLocationType` | 281/281 | 결제 시각·수단·기기 |
| `productOrderStatus` | 281/281 | 상품주문 상태 |
| `placeOrderStatus` (+`placeOrderDate` 104/281) | 281/281 | **발주확인 여부** — 컬럼 사본까지 둔다(목록 필터) |
| `shippingDueDate` | 281/281 | 발송기한 |
| 클레임(`claimStatus`·`claimType`·`cancelReason`·`returnReason`·`claimRequestDate`) | 42/281 | 취소·반품 배지와 잠금 판정 |

---

## 2. 안 쓰는 것 (원본에는 오는데 ERP·화면으로 안 올림)

### 2.1 정산 · 수수료 — **가장 값나가는 미사용 축**

| 원본 필드 | 실데이터 | 뜻 |
|---|---|---|
| `paymentCommission` | 281/281 | 결제수수료(실측 1,815원 표본) |
| `knowledgeShoppingSellingInterlockCommission` | 281/281 | 지식쇼핑 연동수수료(1,500원 표본) |
| `channelCommission` · `saleCommission` | 281/281 | 채널·판매 수수료(대부분 0) |
| `commissionRatingType` · `commissionPrePayStatus` | 281/281 | 수수료 부과 기준·선결제 여부 |

> `expectedSettlementAmount`(정산예정액)만 쓰고 **분해는 안 쓴다.** "왜 이 금액만
> 들어오나"를 화면에서 설명하려면 이 넷이 필요하다.

### 2.2 할인 분해 — 지금은 합계 하나만 쓴다

| 원본 필드 | 실데이터 |
|---|---|
| `productImediateDiscountAmount` | 77/281 (즉시할인) |
| `productProductDiscountAmount` | 44/281 (상품할인) |
| `sellerBurdenDiscountAmount` · `sellerBurdenImediateDiscountAmount` · `sellerBurdenProductDiscountAmount` · `sellerBurdenStoreDiscountAmount` | 77 / 77 / 44 / 281 |
| `order.orderDiscountAmount` | 281/281 (주문 단위 할인) |
| `order.naverMileagePaymentAmount` | 281/281 (네이버페이 포인트 사용액) |
| `order.chargeAmountPaymentAmount` · `generalPaymentAmount` · `payLaterPaymentAmount` | 281/281 (충전금·일반결제·후불) |

> 쿠폰만 2026-08-25 에 꺼냈다. **판매자 부담 축(`sellerBurden*`)은 쿠폰 밖에도 있다** —
> 정산 화면을 만들 때 같이 올릴 자리다.

### 2.3 부분취소 잔여(`remain*`) · 최초값(`initial*`)

| 계열 | 실데이터 | 뜻 |
|---|---|---|
| `remainQuantity` · `remainPaymentAmount` · `remainProductAmount` · `remainProductDiscountAmount` 외 4종 | 281/281 | **부분취소 뒤 남은** 수량·금액 |
| `initialQuantity` · `initialPaymentAmount` · `initialProduct*` · `initialSellerBurden*` | 281/281 | 최초 주문 시점 값 |

> 지금 화면은 `quantity`·`totalPaymentAmount`(현재값)만 본다. **한 집에서 일부만
> 취소된 경우 "원래 몇 개였는지"를 화면이 말하지 못한다.** 부분취소가 실제로 생기면
> 여기가 첫 번째로 필요해진다.

### 2.4 배송 축 (`delivery.*`) — 108/281 건에 존재

| 필드 | 뜻 |
|---|---|
| `delivery.deliveryMethod` | 배송수단(실데이터 `DIRECT_DELIVERY` = 자사 직접 전달) |
| `delivery.deliveryStatus` | 배송 상태(`NOT_TRACKING`) |
| `delivery.sendDate` | 발송처리 시각 |
| `delivery.isWrongTrackingNumber` | 송장 오류 표식 |
| `productOrder.expectedDeliveryMethod` · `deliveryPolicyType`(무료) · `deliveryAttributeType`(NORMAL) | 예상 배송수단·배송비 정책·속성 |
| `deliveryFeeAmount` · `deliveryDiscountAmount` · `sectionDeliveryFee` | 배송비 3종(전부 0) |

> **발송처리를 우리가 눌러 놓고, 그 결과 시각(`sendDate`)을 화면이 안 읽는다.**
> "언제 발송처리가 나갔나"를 지금은 FOMS 쪽 기록으로만 안다.

### 2.5 클레임 상세 (배지에 쓰는 5개 말고 나머지)

| 필드 | 뜻 |
|---|---|
| `collectAddress.*`(회수지 이름·전화·주소·우편) | 반품 회수지 — 15/281 |
| `returnReceiveAddress.*` | 반품 수취지(우리 물류) |
| `collectDeliveryMethod` · `collectCompletedDate` | 회수 방법·회수 완료 시각 |
| `refundExpectedDate` · `refundStandbyStatus` · `refundStandbyReason` | 환불 예정일·대기 상태·사유 |
| `requestChannel`(구매회원/판매자) · `requestQuantity` | 누가 몇 개를 요청했나 |
| `cancelDetailedReason` · `returnDetailedReason` | **고객이 직접 쓴 사유 원문**(실데이터: "일시불 재결제 예정") |
| `completedClaims[]` | 과거 클레임 이력 전체 |

> `cancelDetailedReason` 은 **재결제 판정의 결정적 근거**인데 화면이 안 읽는다.
> 지금은 사람이 네이버에서 확인한다.

### 2.6 그 밖

| 필드 | 실데이터 | 뜻 |
|---|---|---|
| `order.isMembershipSubscribed` | 281/281 | 네이버 멤버십 구독자 여부 |
| `order.ordererId`(마스킹) · `ordererNo` | 281/281 | 주문자 계정 식별자 |
| `order.paymentDueDate` | 1/281 | 입금기한(무통장) |
| `order.isDeliveryMemoParticularInput` | 281/281 | 배송메모 직접입력 여부 |
| `productOrder.packageNumber` | 281/281 | 묶음배송 번호 |
| `mallId` · `merchantChannelId` | 281/281 | 스토어 식별자 |
| `taxType` | 281/281 | 과세 구분 |
| `decisionDate` | 12/281 | 구매확정일 |
| `inflowPathAdd` | 205/281 | 유입경로 보조(값이 문자열 `undefined` 로 온다 — 쓸 때 걸러야 한다) |
| `takingAddress.*` | 281/281 | 출고지(우리 주소라 쓸 일 없음) |
| `shippingAddress.buildingManagementNo` | 281/281 | 건물관리번호(주소 매칭 고도화용) |
| `shippingAddress.addressType` · `isRoadNameAddress` | 281/281 | 국내/해외 · 도로명 여부 |

---

## 3. 다음에 올린다면 우선순위 (내 판단)

1. **`cancelDetailedReason` / `returnDetailedReason`** — 재결제·반품 판정을 사람이 네이버에서
   확인하는 그 자리를 없앤다. 비용 거의 0(원본에 이미 있다).
2. **`delivery.sendDate` · `deliveryStatus`** — 발송처리 결과를 우리 화면이 되읽는다.
3. **`remain*` 계열** — 부분취소가 생기는 순간 필요하다. 지금은 화면이 "원래 몇 개"를 모른다.
4. **정산 축**(`paymentCommission` 외 3종 + `sellerBurden*`) — 정산 대사 화면을 만들 때.
