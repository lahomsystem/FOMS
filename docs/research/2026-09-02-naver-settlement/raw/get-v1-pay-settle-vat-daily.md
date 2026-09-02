# GET /v1/pay-settle/vat/daily - 일별 부가세 내역 조회

네이버페이 결제건의 일별 부가세 집계 내역을 조회하는 API로, 부가가치세 신고와 회계 마감 워크플로우에서 일자별 매출·세액 합계를 적재하는 데 사용합니다. 호출 시 startDate·endDate·pageNumber·pageSize 네 가지 query 파라미터가 모두 필수이며, 조회 가능한 기간은 전월 말일까지로 제한되므로 당월 데이터는 다음 달 마감 이후에만 조회됩니다. 응답은 정산 기준일(settleBasisDate) 별로 총 매출 금액·과세 매출·면세 매출·신용카드 금액·현금영수증 소득공제/지출 증빙/발행 제외 금액·기타 금액과 가맹점 ID/가맹점명을 포함한 페이지 목록을 반환하며, pagination 의 totalPages·totalElements 를 기준으로 다음 페이지 호출 여부를 결정합니다. 대량 적재 시에는 pageSize 최대 1000 을 활용해 페이지 호출 횟수를 줄이는 것이 효율적이며, 가맹점이 여러 곳일 경우 응답의 가맹점 ID 별로 그룹핑해 자사 회계 항목과 매칭합니다. 400 응답은 날짜 범위·기간 제약(전월 말일 초과)·페이지 파라미터의 유효성을 점검해 재호출하고, 500 응답은 서버·DB 일시 오류이므로 백오프 후 동일 페이지를 재시도해 누락을 방지합니다.

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

### 호출 예시

```bash
curl -X GET 'https://api.commerce.naver.com/external/v1/pay-settle/vat/daily?startDate={startDate}&endDate={endDate}&pageNumber={pageNumber}&pageSize={pageSize}' \
  -H 'Authorization: Bearer {access_token}'
```