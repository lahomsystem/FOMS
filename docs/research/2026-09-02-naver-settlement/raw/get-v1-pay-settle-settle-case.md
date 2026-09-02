# GET /v1/pay-settle/settle/case - 건별 정산 내역 조회

네이버페이 정산 내역을 상품 주문(또는 배송비·기타 비용) 단위 건별로 조회하는 API로, 일별 정산 헤더를 그 구성 요소인 원장 건별로 분해해 회계 보조부·정산 명세서를 만들 때 사용합니다. 필수 파라미터는 pageNumber·pageSize 이며, 조회 범위를 좁히려면 searchDate·orderId·productOrderId·periodType(정산 예정일/기준일/완료일/결제일/세금 신고 기준일)·settleType·settleDecisionType 을 조합해 호출합니다. periodType 이 SETTLE_CASEBYCASE_PAY_DATE 인 경우에만 settleDecisionType(SETTLED/UNSETTLED/BEFORE_CANCEL) 이 의미를 가지므로 결제일 기준 조회 시 함께 지정하는 것이 권장됩니다. 응답은 정산 기준/예정/완료일·결제일·주문 번호·상품 주문 번호·정산 대상 구분(productOrderType)·정산 상태(settleType)·상품 정보·구매자명·결제 정산 금액·총 네이버페이 관리 수수료·판매자 부담 무이자 할부 수수료·매출 연동 수수료·혜택 정산 금액·정산 예정 금액·가맹점·계약 번호를 포함한 페이지 목록을 반환합니다. settleType 이 NORMAL_SETTLE_AFTER_CANCEL·NORMAL_SETTLE_BEFORE_CANCEL·QUICK_SETTLE_CANCEL·QUANTITY_CANCEL_RESTORE 등 차감/환급 계열인 경우 부호가 반대 방향이므로 합산 시 원거래(NORMAL_SETTLE_ORIGINAL·QUICK_SETTLE_ORIGINAL) 와 함께 시계열로 묶어 처리합니다. 대량 적재 시 pageSize 최대 1000 을 활용해 호출 횟수를 줄이고, pagination 의 totalPages·totalElements 로 다음 페이지 호출을 제어합니다. 400 응답은 날짜·페이지·enum 조합 유효성을, 500 응답은 서버·DB 일시 오류이므로 백오프 후 동일 페이지를 재시도해 적재 누락을 방지합니다.

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
| elements.settleBasisDate | - | string(date) |  | 정산 기준일(yyyy-MM-dd) |
| elements.settleExpectDate | - | string(date) |  | 정산 예정일(yyyy-MM-dd) |
| elements.settleCompleteDate | - | string(date) |  | 정산 완료일(yyyy-MM-dd) |
| elements.payDate | - | string(date) |  | 결제일(yyyy-MM-dd) |
| elements.orderId | - | string |  | 주문 번호 |
| elements.productOrderId | - | string |  | 상품 주문 번호, 배송비 번호, 기타 비용 번호 |
| elements.productOrderType | - | string | 필수 | 정산 대상 구분(상품 주문, 배송비, 기타 비용)<br>- PROD_ORDER(상품 주문)<br>- DELIVERY(배송비)<br>- EXTRAFEE(기타 비용)<br>- WITHDRAW(결제 수단 출금)<br>- REFUND(구매자 환불)<br>- PL_REFUND(후불 결제 환불)<br>- DEDUCTION_RESTORE(기타 공제 환급)<br>- PROD_PAY(상품 결제)<br>- PURCHASE_REVIEW(텍스트 리뷰)<br>- PREMIUM_PURCHASE_REVIEW(포토/동영상 리뷰)<br>- REGULAR_PURCHASE_REVIEW(알림받기 동의 회원 리뷰 추가 적립)<br>- ONE_MONTH_PURCHASE_REVIEW(한 달 사용 텍스트 리뷰)<br>- ONE_MONTH_PREMIUM_PURCHASE_REVIEW(한 달 사용 포토/동영상 리뷰)<br>- REVIEW(리뷰 적립)<br>- ETC_COUPON(기타 할인)<br>- QUICK_SETTLE(빠른정산)<br>- QUANTITY_CANCEL(수량 취소)<br>- DIFFERENCE_SETTLE(차액 정산)<br>- DEPOSIT_SETTLE(보증금)<br>- RENTAL_ORDER(렌탈 주문)<br>- MANUAL_ORDER(수기 주문)<br>- RENTAL_SCHEDULED_ORDER(월 렌탈료 주문)<br>- PREFERENTIAL_COMMISSION(우대 수수료 환급)<br>- POINT_ACCUMULATION(포인트 적립)<br>- POST_ORDER_ADJUSTMENT_AMOUNT(주문 후 변동 금액)<br>- CSF(통관 대행료)<br>- CONCESSION(구매자 보상). 허용값: `PROD_ORDER`, `DELIVERY`, `EXTRAFEE`, `WITHDRAW`, `REFUND`, `PL_REFUND`, `DEDUCTION_RESTORE`, `PROD_PAY`, `PURCHASE_REVIEW`, `PREMIUM_PURCHASE_REVIEW`, `REGULAR_PURCHASE_REVIEW`, `ONE_MONTH_PURCHASE_REVIEW`, `ONE_MONTH_PREMIUM_PURCHASE_REVIEW`, `REVIEW`, `ETC_COUPON`, `QUICK_SETTLE`, `QUANTITY_CANCEL`, `DIFFERENCE_SETTLE`, `DEPOSIT_SETTLE`, `RENTAL_ORDER`, `MANUAL_ORDER`, `RENTAL_SCHEDULED_ORDER`, `PREFERENTIAL_COMMISSION`, `POINT_ACCUMULATION`, `POST_ORDER_ADJUSTMENT_AMOUNT`, `CSF`, `CONCESSION` |
| elements.settleType | - | string |  | 정산 상태 구분(정산, 정산 전 취소, 정산 후 취소)<br>- NORMAL_SETTLE_ORIGINAL(일반 정산)<br>- NORMAL_SETTLE_AFTER_CANCEL(정산 후 취소)<br>- NORMAL_SETTLE_BEFORE_CANCEL(정산 전 취소)<br>- QUICK_SETTLE_ORIGINAL(빠른정산)<br>- QUICK_SETTLE_CANCEL(빠른정산 회수)<br>- QUANTITY_CANCEL_DEDUCTION(수량 취소 정산(공제))<br>- QUANTITY_CANCEL_RESTORE(수량 취소 정산(환급)). 허용값: `NORMAL_SETTLE_ORIGINAL`, `NORMAL_SETTLE_AFTER_CANCEL`, `NORMAL_SETTLE_BEFORE_CANCEL`, `QUICK_SETTLE_ORIGINAL`, `QUICK_SETTLE_CANCEL`, `QUANTITY_CANCEL_DEDUCTION`, `QUANTITY_CANCEL_RESTORE` |
| elements.productId | - | string |  | 상품 번호 |
| elements.productName | - | string |  | 상품명 |
| elements.purchaserName | - | string |  | 구매자명 |
| elements.paySettleAmount | - | number | 필수 | 결제 정산 금액(=정산 기준 금액) |
| elements.totalPayCommissionAmount | - | number |  | 총 네이버페이 관리 수수료 금액 |
| elements.freeInstallmentCommissionAmount | - | number |  | 판매자 부담 무이자 할부 수수료 |
| elements.sellingInterlockCommissionAmount | - | number |  | 매출 연동 수수료 |
| elements.benefitSettleAmount | - | number | 필수 | 혜택 정산 금액 |
| elements.settleExpectAmount | - | number | 필수 | 정산 예정 금액 |
| elements.merchantId | - | string |  | 가맹점 ID |
| elements.merchantName | - | string |  | 가맹점명 |
| elements.contractNo | - | string |  | 계약 번호 |
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

### 호출 예시

```bash
curl -X GET 'https://api.commerce.naver.com/external/v1/pay-settle/settle/case?pageNumber={pageNumber}&pageSize={pageSize}' \
  -H 'Authorization: Bearer {access_token}'
```
