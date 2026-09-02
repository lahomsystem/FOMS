# GET /v1/pay-settle/vat/case - 건별 부가세 내역 조회

네이버페이 결제건의 부가세 내역을 주문(상품 주문) 단위 건별로 조회하는 API로, 일별 집계만으로는 매출·세액 항목별 원천 분개를 확인하기 어려운 경우에 세금계산서·전표 작성·세무 신고 보조 자료로 활용합니다. 호출 시 startDate·endDate·pageNumber·pageSize 네 가지가 모두 필수이며 조회 가능 기간은 전월 말일까지로 제한됩니다. 응답은 정산 기준일·주문 번호·상품 주문 번호·정산 대상 구분(productOrderType: PROD_ORDER/DELIVERY/EXTRAFEE 등 25종)·상세 유형(detailType: 결제 수단 정산·혜택 정산·공제/환급 계열)·증빙 상태(status: VOUCH_PUBLICATION/VOUCH_CANCEL/VOUCH_RSTOR_PUBLICATION/VOUCH_RSTOR_CANCEL)·상품명과 함께 총 매출/과세/면세/신용카드/현금영수증 계열 금액·기타 금액·가맹점 정보를 반환합니다. 원주문 매출과 취소·공제/환급은 status 값으로 명확히 구분되므로 신고 마감 시 동일 주문에 대해 발행·취소·환급 흐름을 시계열로 합산하면 세액 정합성을 유지할 수 있습니다. 대량 적재 시 기간을 좁히고 pageSize 최대 1000 을 활용하며, pagination 의 totalPages·totalElements 로 다음 페이지 호출을 제어합니다. 400 응답은 날짜·기간 제약·페이지 파라미터를 점검해 재호출하고, 500 응답은 서버·DB 일시 오류이므로 백오프 후 동일 페이지를 재시도해 누락을 방지합니다.

> Base URL: https://api.commerce.naver.com/external

### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:----:|------|
| startDate | query | string(date) | 필수 | 시작일(전월 말일까지 조회 가능) |
| endDate | query | string(date) | 필수 | 종료일(전월 말일까지 조회 가능) |
| pageNumber | query | integer(int32) | 필수 | 페이지 번호. 최소 1 |
| pageSize | query | integer(int32) | 필수 | 페이지 크기(1000 이하). 최대 1000 |

### 응답 스키마

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:----:|------|
| elements | - | array | 필수 |  |
| elements.settleBasisDate | - | string(date) |  | 정산 기준일(yyyy-MM-dd) |
| elements.orderId | - | string | 필수 | 주문 번호 |
| elements.productOrderId | - | string |  | 상품 주문 번호, 배송비 번호, 기타 비용 번호 |
| elements.productOrderType | - | string |  | 정산 대상 구분(상품 주문, 배송비, 기타 비용)<br>- PROD_ORDER(상품 주문)<br>- DELIVERY(배송비)<br>- EXTRAFEE(기타 비용)<br>- WITHDRAW(결제 수단 출금)<br>- REFUND(구매자 환불)<br>- PL_REFUND(후불 결제 환불)<br>- DEDUCTION_RESTORE(기타 공제 환급)<br>- PROD_PAY(상품 결제)<br>- PURCHASE_REVIEW(텍스트 리뷰)<br>- PREMIUM_PURCHASE_REVIEW(포토/동영상 리뷰)<br>- REGULAR_PURCHASE_REVIEW(알림받기 동의 회원 리뷰 추가 적립)<br>- ONE_MONTH_PURCHASE_REVIEW(한 달 사용 텍스트 리뷰)<br>- ONE_MONTH_PREMIUM_PURCHASE_REVIEW(한 달 사용 포토/동영상 리뷰)<br>- REVIEW(리뷰 적립)<br>- ETC_COUPON(기타 할인)<br>- QUICK_SETTLE(빠른정산)<br>- QUANTITY_CANCEL(수량 취소)<br>- DIFFERENCE_SETTLE(차액 정산)<br>- DEPOSIT_SETTLE(보증금)<br>- RENTAL_ORDER(렌탈 주문)<br>- MANUAL_ORDER(수기 주문)<br>- RENTAL_SCHEDULED_ORDER(월 렌탈료 주문)<br>- PREFERENTIAL_COMMISSION(우대 수수료 환급)<br>- POINT_ACCUMULATION(포인트 적립)<br>- POST_ORDER_ADJUSTMENT_AMOUNT(주문 후 변동 금액)<br>- CSF(통관 대행료)<br>- CONCESSION(구매자 보상). 허용값: `PROD_ORDER`, `DELIVERY`, `EXTRAFEE`, `WITHDRAW`, `REFUND`, `PL_REFUND`, `DEDUCTION_RESTORE`, `PROD_PAY`, `PURCHASE_REVIEW`, `PREMIUM_PURCHASE_REVIEW`, `REGULAR_PURCHASE_REVIEW`, `ONE_MONTH_PURCHASE_REVIEW`, `ONE_MONTH_PREMIUM_PURCHASE_REVIEW`, `REVIEW`, `ETC_COUPON`, `QUICK_SETTLE`, `QUANTITY_CANCEL`, `DIFFERENCE_SETTLE`, `DEPOSIT_SETTLE`, `RENTAL_ORDER`, `MANUAL_ORDER`, `RENTAL_SCHEDULED_ORDER`, `PREFERENTIAL_COMMISSION`, `POINT_ACCUMULATION`, `POST_ORDER_ADJUSTMENT_AMOUNT`, `CSF`, `CONCESSION` |
| elements.detailType | - | string |  | 상세 유형(결제 대금 정산, 혜택 정산, 공제/환급)<br>- VOUCH_DETAIL_PAYMENT_SETL(결제 대금 정산)<br>- VOUCH_DETAIL_PRODUCT_COUPON_SETL(혜택 정산(상품 할인))<br>- VOUCH_DETAIL_ORDER_COUPON_SETL(혜택 정산(스토어 할인))<br>- VOUCH_DETAIL_DLVFEE_COUPON_SETL(혜택 정산(배송비 할인))<br>- VOUCH_DETAIL_RTNDLV(공제/환급(반품 배송비))<br>- VOUCH_DETAIL_ETCDLV(공제/환급(기타))<br>- VOUCH_DETAIL_DCCNCL(공제/환급(복수구매 할인 취소))<br>- VOUCH_DETAIL_DLVREC(공제/환급(배송비 금액 변동))<br>- VOUCH_DETAIL_DLCNCL(공제/환급(배송비 할인 금액 변동))<br>- VOUCH_DETAIL_COUPON_SETL(혜택 정산)<br>- VOUCH_DETAIL_DDTN_RSTOR(공제/환급). 허용값: `VOUCH_DETAIL_PAYMENT_SETL`, `VOUCH_DETAIL_PRODUCT_COUPON_SETL`, `VOUCH_DETAIL_ORDER_COUPON_SETL`, `VOUCH_DETAIL_DLVFEE_COUPON_SETL`, `VOUCH_DETAIL_RTNDLV`, `VOUCH_DETAIL_ETCDLV`, `VOUCH_DETAIL_DCCNCL`, `VOUCH_DETAIL_DLVREC`, `VOUCH_DETAIL_DLCNCL`, `VOUCH_DETAIL_COUPON_SETL`, `VOUCH_DETAIL_DDTN_RSTOR` |
| elements.status | - | string |  | 상태(원주문 매출, 주문 취소, 공제/환급, 환급 취소, 수량 취소 정산(공제), 수량 취소 정산(환급))<br>- VOUCH_PUBLICATION(원주문 매출)<br>- VOUCH_CANCEL(주문 취소)<br>- VOUCH_RSTOR_PUBLICATION(공제/환급)<br>- VOUCH_RSTOR_CANCEL(환급 취소). 허용값: `VOUCH_PUBLICATION`, `VOUCH_CANCEL`, `VOUCH_RSTOR_PUBLICATION`, `VOUCH_RSTOR_CANCEL` |
| elements.productName | - | string |  | 상품명 |
| elements.totalSalesAmount | - | number | 필수 | 총 매출 금액 |
| elements.taxationSalesAmount | - | number | 필수 | 과세 매출 금액 |
| elements.taxExemptionSalesAmount | - | number | 필수 | 면세 매출 금액 |
| elements.creditCardAmount | - | number | 필수 | 신용카드 금액 |
| elements.cashInComeDeductionAmount | - | number | 필수 | 현금영수증 소득공제 금액 |
| elements.cashOutGoingEvidenceAmount | - | number | 필수 | 현금영수증 지출 증빙 금액 |
| elements.cashExclusionIssuanceAmount | - | number | 필수 | 현금영수증 발행 제외 금액 |
| elements.otherAmount | - | number | 필수 | 기타 금액 |
| elements.merchantId | - | string |  | 가맹점 ID |
| elements.merchantName | - | string |  | 가맹점명 |
| pagination | - | object | 필수 |  |
| pagination.page | - | integer(int32) |  |  |
| pagination.size | - | integer(int32) |  |  |
| pagination.totalPages | - | integer(int32) |  |  |
| pagination.totalElements | - | integer(int64) |  |  |

### 에러 코드

| 상태 코드 | 설명 |
|-----------|------|
| 400 | Bad Request |
| 500 | Internal Server Error |

### 사용 enum 카탈로그

- 응답 `elements[].productOrderType`: `PROD_ORDER`, `DELIVERY`, `EXTRAFEE`, `WITHDRAW`, `REFUND`, `PL_REFUND`, `DEDUCTION_RESTORE`, `PROD_PAY`, `PURCHASE_REVIEW`, `PREMIUM_PURCHASE_REVIEW`, `REGULAR_PURCHASE_REVIEW`, `ONE_MONTH_PURCHASE_REVIEW`, `ONE_MONTH_PREMIUM_PURCHASE_REVIEW`, `REVIEW`, `ETC_COUPON`, `QUICK_SETTLE`, `QUANTITY_CANCEL`, `DIFFERENCE_SETTLE`, `DEPOSIT_SETTLE`, `RENTAL_ORDER`, `MANUAL_ORDER`, `RENTAL_SCHEDULED_ORDER`, `PREFERENTIAL_COMMISSION`, `POINT_ACCUMULATION`, `POST_ORDER_ADJUSTMENT_AMOUNT`, `CSF`, `CONCESSION`
- 응답 `elements[].detailType`: `VOUCH_DETAIL_PAYMENT_SETL`, `VOUCH_DETAIL_PRODUCT_COUPON_SETL`, `VOUCH_DETAIL_ORDER_COUPON_SETL`, `VOUCH_DETAIL_DLVFEE_COUPON_SETL`, `VOUCH_DETAIL_RTNDLV`, `VOUCH_DETAIL_ETCDLV`, `VOUCH_DETAIL_DCCNCL`, `VOUCH_DETAIL_DLVREC`, `VOUCH_DETAIL_DLCNCL`, `VOUCH_DETAIL_COUPON_SETL`, `VOUCH_DETAIL_DDTN_RSTOR`
- 응답 `elements[].status`: `VOUCH_PUBLICATION`, `VOUCH_CANCEL`, `VOUCH_RSTOR_PUBLICATION`, `VOUCH_RSTOR_CANCEL`

### 호출 예시

```bash
curl -X GET 'https://api.commerce.naver.com/external/v1/pay-settle/vat/case?startDate={startDate}&endDate={endDate}&pageNumber={pageNumber}&pageSize={pageSize}' \
  -H 'Authorization: Bearer {access_token}'
```
