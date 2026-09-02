# GET /v1/pay-settle/settle/commission-details - 수수료 상세 내역 조회

네이버페이 정산건의 수수료를 상세 항목 단위(상품 주문·수수료 유형·결제 수단별)로 조회하는 API로, 일별/건별 정산 헤더만으로는 분해되지 않는 네이버페이 수수료·매출 연동 수수료·무이자 할부 수수료 등 세부 비용 항목을 회계 분개와 수익성 분석에 적재할 때 사용합니다. 조회 범위를 좁히려면 searchDate·orderId·productOrderId·periodType(정산 예정일·기준일·완료일·결제일·세금 신고 기준일)·settleType·settleDecisionType 을 조합해 호출합니다. periodType 이 SETTLE_CASEBYCASE_PAY_DATE 인 경우에만 settleDecisionType(SETTLED/UNSETTLED/BEFORE_CANCEL) 이 의미를 가지므로 결제일 기준 조회 시 정산 확정 상태와 함께 명시하는 것이 권장됩니다. 응답은 주문 번호·상품 주문 번호·정산 대상 구분(productOrderType)·정산 상태(settleType)·정산 기준/예정/완료/세금 신고 기준일·수수료 기준 금액·수수료 타입(commissionType: SALE_COMMISSION·PAY_COMMISSION·CHNL_COMMISSION·PLATFORM_COMMISSION·VERTICAL_COMMISSION 등)·결제 수단(payMeansType)·수수료 금액·최대 과금 매출 연동 수수료 금액·가맹점·구매자명을 포함한 페이지 목록을 반환합니다. 동일 상품 주문에 대해 수수료 유형이 여러 줄로 분해되므로 분개 시 productOrderId 와 commissionType 조합을 기본 키로 사용하고, 빠른정산 회수·정산 후 취소 등의 settleType 행은 부호가 반대인 차감 분개로 처리합니다. 400 응답은 날짜·페이지·enum 조합 유효성을 점검해 재호출하고, 500 응답은 백오프 후 동일 페이지 재시도로 적재 누락을 방지합니다.

> Base URL: https://api.commerce.naver.com/external

### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:----:|------|
| searchDate | query | string(date) |  | 조회일 |
| orderId | query | string |  | 주문 번호 |
| productOrderId | query | string |  | 상품 주문 번호 |
| periodType | query | string |  | 조회 기간 기준<br>- SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE(정산 예정일)<br>- SETTLE_CASEBYCASE_SETTLE_BASIS_DATE(정산 기준일)<br>- SETTLE_CASEBYCASE_SETTLE_COMPLETE_DATE(정산 완료일)<br>- SETTLE_CASEBYCASE_PAY_DATE(결제일)<br>- SETTLE_CASEBYCASE_TAXRETURN_BASIS_DATE(세금 신고 기준일). 허용값: `SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE`, `SETTLE_CASEBYCASE_SETTLE_BASIS_DATE`, `SETTLE_CASEBYCASE_SETTLE_COMPLETE_DATE`, `SETTLE_CASEBYCASE_PAY_DATE`, `SETTLE_CASEBYCASE_TAXRETURN_BASIS_DATE` |
| settleDecisionType | query | string |  | 결제일 구분(periodType 값이 SETTLE_CASEBYCASE_PAY_DATE인 경우)<br>- SETTLED(정산 확정 건)<br>- UNSETTLED(정산 미확정 건)<br>- BEFORE_CANCEL(정산 전 취소 건). 허용값: `SETTLED`, `UNSETTLED`, `BEFORE_CANCEL` |
| settleType | query | string |  | 정산 구분<br>- NORMAL_SETTLE_ORIGINAL(일반 정산)<br>- NORMAL_SETTLE_AFTER_CANCEL(정산 후 취소)<br>- NORMAL_SETTLE_BEFORE_CANCEL(정산 전 취소)<br>- QUICK_SETTLE_ORIGINAL(빠른정산)<br>- QUICK_SETTLE_CANCEL(빠른정산 회수)<br>- QUANTITY_CANCEL_DEDUCTION(수량 취소 정산(공제))<br>- QUANTITY_CANCEL_RESTORE(수량 취소 정산(환급)). 허용값: `NORMAL_SETTLE_ORIGINAL`, `NORMAL_SETTLE_AFTER_CANCEL`, `NORMAL_SETTLE_BEFORE_CANCEL`, `QUICK_SETTLE_ORIGINAL`, `QUICK_SETTLE_CANCEL`, `QUANTITY_CANCEL_DEDUCTION`, `QUANTITY_CANCEL_RESTORE` |
| pageNumber | query | integer(int32) | 필수 | 페이지 번호. 최소 1 |
| pageSize | query | integer(int32) | 필수 | 페이지 크기(1000 이하). 최대 1000 |

### 응답 스키마

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:----:|------|
| elements | - | array | 필수 |  |
| elements.orderNo | - | string | 필수 | 주문 번호 |
| elements.productOrderId | - | string | 필수 | 상품 주문 번호, 배송비 번호, 기타 비용 번호 |
| elements.productOrderType | - | string | 필수 | 정산 대상 구분(상품 주문, 배송비, 기타 비용)<br>- PROD_ORDER(상품 주문)<br>- DELIVERY(배송비)<br>- EXTRAFEE(기타 비용)<br>- WITHDRAW(결제 수단 출금)<br>- REFUND(구매자 환불)<br>- PL_REFUND(후불 결제 환불)<br>- DEDUCTION_RESTORE(기타 공제 환급)<br>- PROD_PAY(상품 결제)<br>- PURCHASE_REVIEW(텍스트 리뷰)<br>- PREMIUM_PURCHASE_REVIEW(포토/동영상 리뷰)<br>- REGULAR_PURCHASE_REVIEW(알림받기 동의 회원 리뷰 추가 적립)<br>- ONE_MONTH_PURCHASE_REVIEW(한 달 사용 텍스트 리뷰)<br>- ONE_MONTH_PREMIUM_PURCHASE_REVIEW(한 달 사용 포토/동영상 리뷰)<br>- REVIEW(리뷰 적립)<br>- ETC_COUPON(기타 할인)<br>- QUICK_SETTLE(빠른정산)<br>- QUANTITY_CANCEL(수량 취소)<br>- DIFFERENCE_SETTLE(차액 정산)<br>- DEPOSIT_SETTLE(보증금)<br>- RENTAL_ORDER(렌탈 주문)<br>- MANUAL_ORDER(수기 주문)<br>- RENTAL_SCHEDULED_ORDER(월 렌탈료 주문)<br>- PREFERENTIAL_COMMISSION(우대 수수료 환급)<br>- POINT_ACCUMULATION(포인트 적립)<br>- POST_ORDER_ADJUSTMENT_AMOUNT(주문 후 변동 금액)<br>- CSF(통관 대행료)<br>- CONCESSION(구매자 보상). 허용값: `PROD_ORDER`, `DELIVERY`, `EXTRAFEE`, `WITHDRAW`, `REFUND`, `PL_REFUND`, `DEDUCTION_RESTORE`, `PROD_PAY`, `PURCHASE_REVIEW`, `PREMIUM_PURCHASE_REVIEW`, `REGULAR_PURCHASE_REVIEW`, `ONE_MONTH_PURCHASE_REVIEW`, `ONE_MONTH_PREMIUM_PURCHASE_REVIEW`, `REVIEW`, `ETC_COUPON`, `QUICK_SETTLE`, `QUANTITY_CANCEL`, `DIFFERENCE_SETTLE`, `DEPOSIT_SETTLE`, `RENTAL_ORDER`, `MANUAL_ORDER`, `RENTAL_SCHEDULED_ORDER`, `PREFERENTIAL_COMMISSION`, `POINT_ACCUMULATION`, `POST_ORDER_ADJUSTMENT_AMOUNT`, `CSF`, `CONCESSION` |
| elements.productId | - | string |  | 상품 번호 |
| elements.productName | - | string |  | 상품명 |
| elements.merchantId | - | string | 필수 | 가맹점 ID |
| elements.merchantName | - | string | 필수 | 가맹점명 |
| elements.purchaserName | - | string |  | 구매자명 |
| elements.settleType | - | string | 필수 | 정산 상태 구분(정산, 정산 전 취소, 정산 후 취소)<br>- NORMAL_SETTLE_ORIGINAL(일반 정산)<br>- NORMAL_SETTLE_AFTER_CANCEL(정산 후 취소)<br>- NORMAL_SETTLE_BEFORE_CANCEL(정산 전 취소)<br>- QUICK_SETTLE_ORIGINAL(빠른정산)<br>- QUICK_SETTLE_CANCEL(빠른정산 회수)<br>- QUANTITY_CANCEL_DEDUCTION(수량 취소 정산(공제))<br>- QUANTITY_CANCEL_RESTORE(수량 취소 정산(환급)). 허용값: `NORMAL_SETTLE_ORIGINAL`, `NORMAL_SETTLE_AFTER_CANCEL`, `NORMAL_SETTLE_BEFORE_CANCEL`, `QUICK_SETTLE_ORIGINAL`, `QUICK_SETTLE_CANCEL`, `QUANTITY_CANCEL_DEDUCTION`, `QUANTITY_CANCEL_RESTORE` |
| elements.settleBasisDate | - | string(date) |  | 정산 기준일(yyyy-MM-dd) |
| elements.settleExpectDate | - | string(date) |  | 정산 예정일(yyyy-MM-dd) |
| elements.settleCompleteDate | - | string(date) |  | 정산 완료일(yyyy-MM-dd) |
| elements.taxReturnDate | - | string(date) |  | 세금 신고 기준일(yyyy-MM-dd) |
| elements.commissionBasisAmount | - | number | 필수 | 수수료 기준 금액 |
| elements.commissionType | - | string | 필수 | 수수료 타입<br>- SALE_COMMISSION((구)판매 수수료)<br>- PAY_COMMISSION(Npay 수수료)<br>- CHNL_COMMISSION(채널 수수료)<br>- ISTLM_COMMISSION(무이자 할부 수수료)<br>- PUBLISHING_COMMISSION(퍼블리싱 수수료)<br>- INFLOW_COMMISSION(유입 수수료)<br>- SERVICE_COMMISSION(솔루션 사용료)<br>- CONTRACT_COMMISSION(계약 수수료)<br>- PACKAGE_COMMISSION(패키지 사용료)<br>- PARTNER_COMMISSION(제휴 사용료)<br>- PLATFORM_COMMISSION(판매 수수료)<br>- VERTICAL_COMMISSION(버티컬 사용료)<br>- PURCHASER_COMMISSION(구매자 수수료)<br>- PRICE_COMPARISON_COMMISSION(가격비교 수수료). 허용값: `SALE_COMMISSION`, `PAY_COMMISSION`, `CHNL_COMMISSION`, `ISTLM_COMMISSION`, `PUBLISHING_COMMISSION`, `INFLOW_COMMISSION`, `SERVICE_COMMISSION`, `CONTRACT_COMMISSION`, `PACKAGE_COMMISSION`, `PARTNER_COMMISSION`, `PLATFORM_COMMISSION`, `VERTICAL_COMMISSION`, `PURCHASER_COMMISSION`, `PRICE_COMPARISON_COMMISSION` |
| elements.payMeansType | - | string |  | 결제 수단<br>- PAYMEANS_TYPE_ALL(전체)<br>- PAYMEANS_TYPE_BANK(실시간 계좌 이체)<br>- PAYMEANS_TYPE_CCARD(신용카드)<br>- PAYMEANS_TYPE_CHAMT((구)구매자충전금)<br>- PAYMEANS_TYPE_CHKAC((구)체크아웃적립금)<br>- PAYMEANS_TYPE_DON((구)네이버캐쉬)<br>- PAYMEANS_TYPE_MOBIL(휴대폰 결제)<br>- PAYMEANS_TYPE_NCASH(네이버페이 포인트·머니)<br>- PAYMEANS_TYPE_POINT(포인트 결제)<br>- PAYMEANS_TYPE_VACCT(무통장입금)<br>- PAYMEANS_TYPE_SKIP(나중에결제)<br>- PAYMEANS_TYPE_PAYLATER(후불 결제)<br>- PAYMEANS_TYPE_GIFTCARD(기프트 카드)<br>- PAYMEANS_TYPE_NONE(주결제 수단 없음)<br>- PAYMEANS_TYPE_NMP_DISCOUNT(네이버 할인지원금)<br>- PAYMEANS_TYPE_OVERSEAS_CARD(해외 카드). 허용값: `PAYMEANS_TYPE_ALL`, `PAYMEANS_TYPE_BANK`, `PAYMEANS_TYPE_CCARD`, `PAYMEANS_TYPE_CHAMT`, `PAYMEANS_TYPE_CHKAC`, `PAYMEANS_TYPE_DON`, `PAYMEANS_TYPE_MOBIL`, `PAYMEANS_TYPE_NCASH`, `PAYMEANS_TYPE_POINT`, `PAYMEANS_TYPE_VACCT`, `PAYMEANS_TYPE_SKIP`, `PAYMEANS_TYPE_PAYLATER`, `PAYMEANS_TYPE_GIFTCARD`, `PAYMEANS_TYPE_NONE`, `PAYMEANS_TYPE_NMP_DISCOUNT`, `PAYMEANS_TYPE_OVERSEAS_CARD` |
| elements.commissionAmount | - | number | 필수 | 수수료 금액 |
| elements.maximumSellingInterlockCommissionAmount | - | number |  | 최대 과금 매출 연동 수수료 금액 |
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

- 파라미터 `periodType`: `SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE`, `SETTLE_CASEBYCASE_SETTLE_BASIS_DATE`, `SETTLE_CASEBYCASE_SETTLE_COMPLETE_DATE`, `SETTLE_CASEBYCASE_PAY_DATE`, `SETTLE_CASEBYCASE_TAXRETURN_BASIS_DATE`
- 파라미터 `settleDecisionType`: `SETTLED`, `UNSETTLED`, `BEFORE_CANCEL`
- 파라미터 `settleType`: `NORMAL_SETTLE_ORIGINAL`, `NORMAL_SETTLE_AFTER_CANCEL`, `NORMAL_SETTLE_BEFORE_CANCEL`, `QUICK_SETTLE_ORIGINAL`, `QUICK_SETTLE_CANCEL`, `QUANTITY_CANCEL_DEDUCTION`, `QUANTITY_CANCEL_RESTORE`
- 응답 `elements[].productOrderType`: `PROD_ORDER`, `DELIVERY`, `EXTRAFEE`, `WITHDRAW`, `REFUND`, `PL_REFUND`, `DEDUCTION_RESTORE`, `PROD_PAY`, `PURCHASE_REVIEW`, `PREMIUM_PURCHASE_REVIEW`, `REGULAR_PURCHASE_REVIEW`, `ONE_MONTH_PURCHASE_REVIEW`, `ONE_MONTH_PREMIUM_PURCHASE_REVIEW`, `REVIEW`, `ETC_COUPON`, `QUICK_SETTLE`, `QUANTITY_CANCEL`, `DIFFERENCE_SETTLE`, `DEPOSIT_SETTLE`, `RENTAL_ORDER`, `MANUAL_ORDER`, `RENTAL_SCHEDULED_ORDER`, `PREFERENTIAL_COMMISSION`, `POINT_ACCUMULATION`, `POST_ORDER_ADJUSTMENT_AMOUNT`, `CSF`, `CONCESSION`
- 응답 `elements[].settleType`: `NORMAL_SETTLE_ORIGINAL`, `NORMAL_SETTLE_AFTER_CANCEL`, `NORMAL_SETTLE_BEFORE_CANCEL`, `QUICK_SETTLE_ORIGINAL`, `QUICK_SETTLE_CANCEL`, `QUANTITY_CANCEL_DEDUCTION`, `QUANTITY_CANCEL_RESTORE`
- 응답 `elements[].commissionType`: `SALE_COMMISSION`, `PAY_COMMISSION`, `CHNL_COMMISSION`, `ISTLM_COMMISSION`, `PUBLISHING_COMMISSION`, `INFLOW_COMMISSION`, `SERVICE_COMMISSION`, `CONTRACT_COMMISSION`, `PACKAGE_COMMISSION`, `PARTNER_COMMISSION`, `PLATFORM_COMMISSION`, `VERTICAL_COMMISSION`, `PURCHASER_COMMISSION`, `PRICE_COMPARISON_COMMISSION`
- 응답 `elements[].payMeansType`: `PAYMEANS_TYPE_ALL`, `PAYMEANS_TYPE_BANK`, `PAYMEANS_TYPE_CCARD`, `PAYMEANS_TYPE_CHAMT`, `PAYMEANS_TYPE_CHKAC`, `PAYMEANS_TYPE_DON`, `PAYMEANS_TYPE_MOBIL`, `PAYMEANS_TYPE_NCASH`, `PAYMEANS_TYPE_POINT`, `PAYMEANS_TYPE_VACCT`, `PAYMEANS_TYPE_SKIP`, `PAYMEANS_TYPE_PAYLATER`, `PAYMEANS_TYPE_GIFTCARD`, `PAYMEANS_TYPE_NONE`, `PAYMEANS_TYPE_NMP_DISCOUNT`, `PAYMEANS_TYPE_OVERSEAS_CARD`

### 호출 예시

```bash
curl -X GET 'https://api.commerce.naver.com/external/v1/pay-settle/settle/commission-details?pageNumber={pageNumber}&pageSize={pageSize}' \
  -H 'Authorization: Bearer {access_token}'
```
