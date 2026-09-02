# 네이버 커머스 정산 API 5종 — 소스 인용 스펙 (2026-09-02)

## 결론 (요약 10줄)
1. **Base URL**(호출용, 문서 도메인과 다름) = `https://api.commerce.naver.com/external` — 인증은 `Authorization: Bearer {access_token}`, 발급은 `POST /v1/oauth2/token`(WORKER 전용 호출 기존 제약과 별개로 무관).
2. **날짜 범위 제한**: `settle/case`·`settle/commission-details`는 **기간 조회 자체가 불가**(단일일 `searchDate`만 있음, `startDate`/`endDate` 파라미터 없음) — GitHub #3709에서 네이버 담당자가 직접 확인("해당 API는 기간 범위 조회를 지원하지 않아 하루씩 조회"). `settle/daily`는 `startDate`/`endDate` 필수(최대 폭 문서 미기재, NOT IN DOCS). `vat/case`·`vat/daily`는 **전월 말일까지만 조회 가능**(당월 데이터는 익월 마감 후 조회, 문서 명기).
3. **페이지네이션**: 5종 전부 `pageNumber`(최소 1)·`pageSize`(필수, 최대 1000) + 응답 `pagination.{page,size,totalPages,totalElements}` 동일 패턴.
4. **정산 예정일 vs 정산 완료일**: GitHub #414(공식 FAQ) — 완료일은 은행 입금이 실제로 끝나야 채워지는 값이라 **완료건 조회는 예정일(`SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE`) 기준을 권장**, 완료일 기준은 더 느림.
5. **데이터 소급 변경**: GitHub #3123 실사례 — 특정 날짜 정산건이 이후 조회 시 다른 정산일로 옮겨간 것이 확인됨. 공식 답변(#3674)은 "변경 가능성은 매우 낮음"이라면서도 **직전 1일만 배치 수집하지 말고 일정 기간 과거를 롤링 재조회**할 것을 권장 — 완결 시점은 API로 별도 제공되지 않음(NOT IN DOCS).
6. **`settle/daily`의 startDate/endDate 필터 기준일**: 문서에는 명시 안 됨, GitHub #1481 공식 답변으로 **정산 예정일(settleExpectDate) 기준**임을 확인(NOT IN DOCS→ Discussion으로 확정).
7. **레이트리밋/쿼터**: 일반 판매자용 "내스토어 애플리케이션"은 원칙적으로 Quota 제한 없음(#2999, 대행사만 해당). 단, `POST /v1/oauth2/token` 요청이 기술 규격(form-urlencoded, 필수 파라미터 body 포함, grant_type=client_credentials, SELF 타입엔 account_id 미포함)을 위반하면 **토큰 발급 자체가 시간당 1회로 제한**되고 그 여파로 정산 API가 HTTP 429(`GW.QUOTA_LIMIT`)를 반환할 수 있음(#3709, #3751) — 실운영 장애 원인 1순위 후보.
8. **앱 종류 주의**: "내스토어 애플리케이션"과 "API데이터솔루션(통계) 애플리케이션"은 **토큰이 분리**되어 있고 서로의 API 그룹을 호출 못함(#2788, 403 GW.AUTHN 실사례) — FOMS는 반드시 "내스토어 애플리케이션" 토큰으로 정산 API를 호출해야 하며, 해당 애플리케이션에 **[정산] API 그룹 권한**이 등록돼 있어야 함(#1013, #1205).
9. **타임존**: 커머스API 전체가 **한국 표준시(UTC+9)** 기준으로 응답을 생성(#32, 정산 API 개별 확인 문서는 없으나 플랫폼 공통 규약).
10. **충전금 정산 vs 계좌이체 정산**: `settle/daily.settleMethodType`이 `ACCOUNT`(계좌 이체 — bankType/depositorName/accountNo로 실제 입금 채널 확인)와 `CHARGE_AMT`(충전금 — 마이너스 충전금 상계, 실제 은행 입금이 발생하지 않음)로 나뉨. 입금 대사 워크플로는 `ACCOUNT` 행만 은행 거래와 매칭하고 `CHARGE_AMT` 행은 잔액 흐름으로 별도 추적해야 함.

## 조사 방법 메모
- `WebFetch` 도구가 `apicenter.commerce.naver.com` 도메인 자체를 차단하여(`Claude Code is unable to fetch from apicenter.commerce.naver.com`), `curl`(User-Agent 지정)로 5종 API 문서 원문 마크다운을 전량 그대로 가져왔다. 5건 모두 HTTP 200.
- 브리프에 적힌 `https://apicenter.commerce.naver.com/llms.txt`는 실제로는 **404**이며, 올바른 색인 URL은 `https://apicenter.commerce.naver.com/llms/llms.txt`(HTTP 200)이다. 다음 세션은 이 경로로 정정해서 참조할 것.
- GitHub Discussions는 `gh api graphql`(search type:DISCUSSION + 개별 discussion 쿼리)로 조회. 계정 인증 상태였음.

---

## 공통 사항 (5종 API 공통)
- Base URL: `https://api.commerce.naver.com/external` (문서 사이트 `apicenter.commerce.naver.com`과는 다른 도메인)
- 인증: `Authorization: Bearer {access_token}` 헤더 필수, 토큰은 `POST /v1/oauth2/token`으로 발급.
- 페이지네이션 응답 스키마 공통: `pagination.page`(integer int32) · `pagination.size`(integer int32) · `pagination.totalPages`(integer int32) · `pagination.totalElements`(integer int64).
- 에러 코드는 5종 전부 문서상 `400 Bad Request` / `500 Internal Server Error` 두 가지만 명시. 실측 GitHub 사례에서 추가로 확인된 코드: `401`+`GW.AUTHN`("요청을 보낼 권한이 없습니다" — 토큰의 API 그룹 권한 누락 또는 앱 종류 불일치), `429`+`GW.QUOTA_LIMIT`("할당된 시간당 요청량을 초과하였습니다" — 문서에는 없는 코드, NOT IN DOCS이나 Discussion #3709로 실증됨).
- 날짜 필드 포맷: `string(date)` = `yyyy-MM-dd`. 시각(시간대) 필드는 정산 API 응답에 없음(전부 날짜만). 커머스API 플랫폼 공통 규약상 모든 응답은 한국 표준시(KST, UTC+9) 기준(Discussion #32, 정산 API 한정 확인 문서는 없음 — NOT IN DOCS로 표시하되 플랫폼 공통 규약으로 사실상 확정).
- `productOrderType`·`settleType` enum은 `settle/case`·`settle/commission-details`·`vat/case` 3종이 동일 카탈로그를 공유(총 26개 값, `PROD_ORDER`~`CONCESSION`).

---

## 1. GET /v1/pay-settle/settle/case — 건별 정산 내역 조회
출처: https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-settle-case.md

### 목적
네이버페이 정산 내역을 상품 주문(또는 배송비·기타 비용) 단위 **건별**로 조회. 일별 정산 헤더(`settle/daily`)를 구성 요소로 분해한 원장(ledger) 레벨 데이터로, 회계 보조부·정산 명세서 생성에 사용.

### 요청 파라미터
| 이름 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| searchDate | query | string(date) | - | 조회일. **기간 범위 파라미터 없음**(startDate/endDate 미제공 — Discussion #3709로 실증: 하루 단위로만 조회 가능) |
| orderId | query | string | - | 주문 번호 |
| productOrderId | query | string | - | 상품 주문 번호 |
| periodType | query | string | - | 조회 기간 기준. 허용값: `SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE`(정산 예정일) · `SETTLE_CASEBYCASE_SETTLE_BASIS_DATE`(정산 기준일) · `SETTLE_CASEBYCASE_SETTLE_COMPLETE_DATE`(정산 완료일) · `SETTLE_CASEBYCASE_PAY_DATE`(결제일) · `SETTLE_CASEBYCASE_TAXRETURN_BASIS_DATE`(세금 신고 기준일) |
| settleDecisionType | query | string | - | `periodType=SETTLE_CASEBYCASE_PAY_DATE`일 때만 의미 있음. 허용값: `SETTLED`(정산 확정 건) · `UNSETTLED`(정산 미확정 건) · `BEFORE_CANCEL`(정산 전 취소 건) |
| settleType | query | string | - | 정산 구분. 허용값: `NORMAL_SETTLE_ORIGINAL`(일반 정산) · `NORMAL_SETTLE_AFTER_CANCEL`(정산 후 취소) · `NORMAL_SETTLE_BEFORE_CANCEL`(정산 전 취소) · `QUICK_SETTLE_ORIGINAL`(빠른정산) · `QUICK_SETTLE_CANCEL`(빠른정산 회수) · `QUANTITY_CANCEL_DEDUCTION`(수량 취소 정산(공제)) · `QUANTITY_CANCEL_RESTORE`(수량 취소 정산(환급)) |
| pageNumber | query | integer(int32) | **필수** | 최소 1 |
| pageSize | query | integer(int32) | **필수** | 최대 1000 |

### 응답 필드 (`elements[]`)
| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| settleBasisDate | string(date) | - | 정산 기준일(구매확정·반품/교환완료 등으로 정산 대상건이 확정된 날짜) |
| settleExpectDate | string(date) | - | 정산 예정일(은행 처리 예정일) |
| settleCompleteDate | string(date) | - | 정산 완료일(은행 처리 완료 이후에만 값 존재) |
| payDate | string(date) | - | 결제일 |
| orderId | string | - | 주문 번호 |
| productOrderId | string | - | 상품 주문 번호 / 배송비 번호 / 기타 비용 번호(productOrderType에 따라 의미 다름 — 아래 "모호한 점" 참고) |
| productOrderType | string | **필수** | 정산 대상 구분, 26개 enum(아래 카탈로그) |
| settleType | string | - | 정산 상태 구분, 7개 enum |
| productId | string | - | 상품 번호 |
| productName | string | - | 상품명 |
| purchaserName | string | - | 구매자명 |
| paySettleAmount | number | **필수** | 결제 정산 금액(=정산 기준 금액) |
| totalPayCommissionAmount | number | - | 총 네이버페이 관리 수수료 금액 |
| freeInstallmentCommissionAmount | number | - | 판매자 부담 무이자 할부 수수료 |
| sellingInterlockCommissionAmount | number | - | 매출 연동 수수료 |
| benefitSettleAmount | number | **필수** | 혜택 정산 금액(주의: 항목별 상세 없이 합산값만 — Discussion #3649) |
| settleExpectAmount | number | **필수** | 정산 예정 금액 |
| merchantId | string | - | 가맹점 ID |
| merchantName | string | - | 가맹점명 |
| contractNo | string | - | 계약 번호 |
| pagination.* | - | **필수** | 공통 페이지네이션(위 참고) |

**`productOrderType` 26개 값**: `PROD_ORDER`(상품 주문) · `DELIVERY`(배송비) · `EXTRAFEE`(기타 비용) · `WITHDRAW`(결제 수단 출금) · `REFUND`(구매자 환불) · `PL_REFUND`(후불 결제 환불) · `DEDUCTION_RESTORE`(기타 공제 환급) · `PROD_PAY`(상품 결제) · `PURCHASE_REVIEW`(텍스트 리뷰) · `PREMIUM_PURCHASE_REVIEW`(포토/동영상 리뷰) · `REGULAR_PURCHASE_REVIEW`(알림받기 동의 회원 리뷰 추가 적립) · `ONE_MONTH_PURCHASE_REVIEW`(한 달 사용 텍스트 리뷰) · `ONE_MONTH_PREMIUM_PURCHASE_REVIEW`(한 달 사용 포토/동영상 리뷰) · `REVIEW`(리뷰 적립) · `ETC_COUPON`(기타 할인) · `QUICK_SETTLE`(빠른정산) · `QUANTITY_CANCEL`(수량 취소) · `DIFFERENCE_SETTLE`(차액 정산) · `DEPOSIT_SETTLE`(보증금) · `RENTAL_ORDER`(렌탈 주문) · `MANUAL_ORDER`(수기 주문) · `RENTAL_SCHEDULED_ORDER`(월 렌탈료 주문) · `PREFERENTIAL_COMMISSION`(우대 수수료 환급) · `POINT_ACCUMULATION`(포인트 적립) · `POST_ORDER_ADJUSTMENT_AMOUNT`(주문 후 변동 금액 — Discussion #3780: 배송비/배송비할인 변동, productName="배송비금액변동"/"배송비할인금액변동"으로 식별) · `CSF`(통관 대행료) · `CONCESSION`(구매자 보상)

**`settleType` 7개 값**: `NORMAL_SETTLE_ORIGINAL`(일반 정산) · `NORMAL_SETTLE_AFTER_CANCEL`(정산 후 취소) · `NORMAL_SETTLE_BEFORE_CANCEL`(정산 전 취소) · `QUICK_SETTLE_ORIGINAL`(빠른정산) · `QUICK_SETTLE_CANCEL`(빠른정산 회수) · `QUANTITY_CANCEL_DEDUCTION`(수량 취소 정산(공제)) · `QUANTITY_CANCEL_RESTORE`(수량 취소 정산(환급)). **부호 규칙**: `NORMAL_SETTLE_AFTER_CANCEL`·`NORMAL_SETTLE_BEFORE_CANCEL`·`QUICK_SETTLE_CANCEL`·`QUANTITY_CANCEL_RESTORE` 등 차감/환급 계열은 금액 부호가 반대이므로 원거래(`NORMAL_SETTLE_ORIGINAL`·`QUICK_SETTLE_ORIGINAL`)와 시계열로 묶어 합산해야 함(문서 원문 명시).

### 에러 코드
| 코드 | 설명 |
|---|---|
| 400 | Bad Request(날짜·페이지·enum 조합 유효성) |
| 500 | Internal Server Error(백오프 후 동일 페이지 재시도) |

### 모호한 점 / NOT IN DOCS
- 대량 적재 가이드로 "pageSize 최대 1000 활용" 문구는 있으나 **일별 총 건수 상한**은 문서에 없음(NOT IN DOCS).
- `productOrderId`가 `productOrderType`에 따라 상품주문번호/배송비번호/기타비용번호로 의미가 바뀐다는 점은 이 문서(settle/case)엔 명시 안 됨 — 자매 API인 `vat/case` 문서와 Discussion #2818에서 확정.
- 데이터 소급 변경 가능성·완결 시점 미제공은 이 문서에 없음 — Discussion #3123/#3674로 확정(위 결론 5번).

---

## 2. GET /v1/pay-settle/settle/commission-details — 수수료 상세 내역 조회
출처: https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-settle-commission-details.md

### 목적
정산건의 수수료를 **상품 주문 × 수수료 유형 × 결제 수단** 단위로 상세 조회. `settle/case`의 `totalPayCommissionAmount` 등 합산 수수료를 항목별로 분해한 데이터로, 회계 분개·수익성 분석용.

### 요청 파라미터
`settle/case`와 **완전히 동일**: `searchDate`(기간 범위 없음, 단일일만) · `orderId` · `productOrderId` · `periodType`(5종 동일 enum) · `settleDecisionType`(periodType=PAY_DATE일 때만) · `settleType`(7종 동일 enum) · `pageNumber`(필수, 최소 1) · `pageSize`(필수, 최대 1000).

### 응답 필드 (`elements[]`)
| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| orderNo | string | **필수** | 주문 번호 |
| productOrderId | string | **필수** | 상품 주문 번호 / 배송비 번호 / 기타 비용 번호 |
| productOrderType | string | **필수** | 정산 대상 구분(26종, settle/case와 동일 카탈로그) |
| productId | string | - | 상품 번호 |
| productName | string | - | 상품명 |
| merchantId | string | **필수** | 가맹점 ID |
| merchantName | string | **필수** | 가맹점명 |
| purchaserName | string | - | 구매자명 |
| settleType | string | **필수** | 정산 상태 구분(7종, settle/case와 동일 카탈로그) |
| settleBasisDate | string(date) | - | 정산 기준일 |
| settleExpectDate | string(date) | - | 정산 예정일 |
| settleCompleteDate | string(date) | - | 정산 완료일 |
| taxReturnDate | string(date) | - | 세금 신고 기준일 |
| commissionBasisAmount | number | **필수** | 수수료 기준 금액(수수료율이 적용되는 원금) |
| commissionType | string | **필수** | 수수료 타입, 14개 enum(아래) |
| payMeansType | string | - | 결제 수단, 16개 enum(아래) |
| commissionAmount | number | **필수** | 수수료 금액(실제 부과분) |
| maximumSellingInterlockCommissionAmount | number | - | 최대 과금 매출 연동 수수료 금액(실부과 아님, 상한값. 값 없으면 상한 미설정 — Discussion #3447) |
| pagination.* | - | **필수** | 공통 페이지네이션 |

**`commissionType` 14개 값**: `SALE_COMMISSION`((구)판매 수수료) · `PAY_COMMISSION`(Npay 수수료) · `CHNL_COMMISSION`(채널 수수료) · `ISTLM_COMMISSION`(무이자 할부 수수료) · `PUBLISHING_COMMISSION`(퍼블리싱 수수료) · `INFLOW_COMMISSION`(유입 수수료) · `SERVICE_COMMISSION`(솔루션 사용료) · `CONTRACT_COMMISSION`(계약 수수료) · `PACKAGE_COMMISSION`(패키지 사용료) · `PARTNER_COMMISSION`(제휴 사용료) · `PLATFORM_COMMISSION`(판매 수수료) · `VERTICAL_COMMISSION`(버티컬 사용료) · `PURCHASER_COMMISSION`(구매자 수수료) · `PRICE_COMPARISON_COMMISSION`(가격비교 수수료)

**`payMeansType` 16개 값**: `PAYMEANS_TYPE_ALL`(전체) · `PAYMEANS_TYPE_BANK`(실시간 계좌 이체) · `PAYMEANS_TYPE_CCARD`(신용카드) · `PAYMEANS_TYPE_CHAMT`((구)구매자충전금) · `PAYMEANS_TYPE_CHKAC`((구)체크아웃적립금) · `PAYMEANS_TYPE_DON`((구)네이버캐쉬) · `PAYMEANS_TYPE_MOBIL`(휴대폰 결제) · `PAYMEANS_TYPE_NCASH`(네이버페이 포인트·머니) · `PAYMEANS_TYPE_POINT`(포인트 결제) · `PAYMEANS_TYPE_VACCT`(무통장입금) · `PAYMEANS_TYPE_SKIP`(나중에결제) · `PAYMEANS_TYPE_PAYLATER`(후불 결제) · `PAYMEANS_TYPE_GIFTCARD`(기프트 카드) · `PAYMEANS_TYPE_NONE`(주결제 수단 없음) · `PAYMEANS_TYPE_NMP_DISCOUNT`(네이버 할인지원금) · `PAYMEANS_TYPE_OVERSEAS_CARD`(해외 카드)

### 에러 코드
문서상 `400`/`500` 동일. 실측: 429(`GW.QUOTA_LIMIT`, Discussion #3709는 이 엔드포인트가 아니라 settle/case 사례지만 인증 토큰 발급 규격 문제로 정산 API 전체에 영향 가능).

### 모호한 점 / NOT IN DOCS
- 동일 `productOrderId`가 `commissionType`별로 여러 행으로 분해된다는 사실은 문서 서술부에만 있고 스키마 표에는 명시 안 됨(분개 시 `productOrderId + commissionType` 조합을 키로 쓰라고 서술부가 안내).
- 2026-08-19부로 `sellingInterlockCommissionType`(매출 연동 수수료 타입) 필드가 **응답에서 제거 예정**이었음(Discussion #3590, 공지일 2026-07-20) — 오늘(2026-09-02) 기준 이미 지난 시점이라 현재 응답 스키마엔 해당 필드가 없음(이번에 fetch한 문서에도 없음, 정합). 과거 연동 코드가 이 필드를 참조 중이라면 깨졌을 것.

---

## 3. GET /v1/pay-settle/settle/daily — 일별 정산 내역 조회
출처: https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-settle-daily.md

### 목적
정산의 **일별 합계 헤더**를 조회. 일자별 정산 마감 적재·입금 대사(은행 이체·충전금) 워크플로의 시작점.

### 요청 파라미터
| 이름 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| startDate | query | string(date) | **필수** | 시작일. 필터 기준일은 문서 미기재 — Discussion #1481로 **정산 예정일(settleExpectDate) 기준**임을 확인(NOT IN DOCS→Discussion 확정) |
| endDate | query | string(date) | **필수** | 종료일(동일 기준) |
| pageNumber | query | integer(int32) | **필수** | 최소 1 |
| pageSize | query | integer(int32) | **필수** | 최대 1000 |

날짜 범위 최대 폭은 문서에 명시 없음(NOT IN DOCS, `settle/case`처럼 하루 제한인지 여부도 불명 — 다른 endpoint와 달리 startDate/endDate가 있으므로 범위 조회 자체는 가능해 보이나 상한 폭은 실측 필요).

### 응답 필드 (`elements[]`)
| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| settleBasisStartDate | string(date) | - | 정산 기준 시작일 |
| settleBasisEndDate | string(date) | - | 정산 기준 종료일 |
| settleExpectDate | string(date) | - | 정산 예정일 |
| settleCompleteDate | string(date) | - | 정산 완료일 |
| settleAmount | number | - | 정산 금액 |
| paySettleAmount | number | - | 결제 정산 금액(=정산 기준 금액) |
| commissionSettleAmount | number | - | 수수료 정산 금액(commission-details 합계에 대응) |
| benefitSettleAmount | number | - | 혜택 정산 금액(항목별 상세는 API로 미제공, Discussion #3649) |
| deductionRestoreSettleAmount | number | - | 공제 환급 정산 금액 |
| payHoldbackAmount | number | - | 지급 보류 금액 |
| minusChargeAmount | number | - | 마이너스 충전금 상계 금액 |
| differenceSettleAmount | number | - | 차액 정산 금액 |
| returnCareSettleAmount | number | **필수** | 반품안심케어 정산 금액 |
| normalSettleAmount | number | - | 일반 정산 금액 |
| quickSettleAmount | number | - | 빠른정산 금액 |
| preferentialCommissionAmount | number | - | 우대 수수료 환급 금액 |
| settlementLimitAmount | number | - | 한도 보류/해제 금액 |
| settleMethodType | string | - | 정산 방법: `ACCOUNT`(계좌 이체) · `CHARGE_AMT`(충전금) |
| bankType | string | - | 은행 코드, 63개 enum(국내 은행·증권사 전체 목록, 아래 요약) |
| depositorName | string | - | 예금주 |
| accountNo | string | - | 계좌 번호 |
| merchantId | string | - | 가맹점 ID |
| merchantName | string | - | 가맹점명 |
| pagination.* | - | **필수** | 공통 페이지네이션 |

**`bankType`(63개)**: 시중은행(`KB`·`SHINHAN`·`WOORI`·`KEB_HANA`·`NH`·`IBK`·`SC`·`CITI` 등) + 지방은행(`BUSAN`·`KWANGJU`·`JEJU`·`JEONBUK`·`KYONGNAM`·`IM` 등) + 인터넷은행(`KBANK`·`KKOBANK`·`TOSS`) + 상호금융(`SAEMAUL`·`SHINHYUP`·`LNH`·`NFCF`·`POST`) + 저축은행(`FSB`·`SBISB`·`WELCOME_BANK` 등) + 증권사(`MIRAEASSET`·`SANSUNG_SEC`·`KIWOOM_IVST_SEC` 등 20여 개) + 해외은행(`HSBC`·`DEUTSCHE_BANK`·`JP_MORGAN`·`BOA`·`BNP`·`ICBC`). 전체 값 목록은 원문서 표 참고(63개 전량 이 문서 본문에 이미 기재).

### 에러 코드
`400`/`500` 문서 명시. `startDate`/`endDate` 미기재 시 400 추정(NOT IN DOCS, 둘 다 필수이므로 논리적으로 당연).

### 모호한 점 / NOT IN DOCS
- **결론 6번**: `startDate`/`endDate`가 어떤 날짜 필드(기준일/예정일/완료일) 기준으로 필터링되는지 표에 없음 → Discussion #1481로 "정산 예정일 기준" 확정.
- 일별 총 건수는 가맹점(merchantId)별로 나뉘어 여러 행이 나올 수 있음(문서 서술: "가맹점이 여러 곳일 경우 응답의 가맹점 ID 별로 그룹핑") — 즉 하루에 여러 `elements` 행이 나올 수 있다는 뜻이나 정확한 카디널리티(가맹점 수 = 행 수인지, 정산방법별로도 나뉘는지)는 스키마만으로는 불명(NOT IN DOCS).
- 혜택 정산 금액(`benefitSettleAmount`) 항목별 세부내역 API 미제공 확정(Discussion #3649) — 스마트스토어센터 엑셀 다운로드로만 확인 가능.

---

## 4. GET /v1/pay-settle/vat/case — 건별 부가세 내역 조회
출처: https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-vat-case.md

### 목적
결제건의 부가세 내역을 **주문(상품 주문) 단위 건별**로 조회. 세금계산서·전표 작성, 세무 신고 보조 자료용. `settle/case`와 달리 "정산 금액"이 아니라 "매출·세액" 관점의 원장.

### 요청 파라미터
| 이름 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| startDate | query | string(date) | **필수** | 시작일. **전월 말일까지 조회 가능**(당월 데이터는 익월 마감 후 조회) |
| endDate | query | string(date) | **필수** | 종료일(동일 제약) |
| pageNumber | query | integer(int32) | **필수** | 최소 1 |
| pageSize | query | integer(int32) | **필수** | 최대 1000 |

### 응답 필드 (`elements[]`)
| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| settleBasisDate | string(date) | - | 정산 기준일 |
| orderId | string | **필수** | 주문 번호 |
| productOrderId | string | - | 상품 주문 번호/배송비 번호/기타 비용 번호. **`productOrderType`값에 따라 의미가 다름**: `DELIVERY`→배송비 번호(원 상품주문번호와 매핑 안 됨, 별도 채번), `PROD_ORDER`→기존 상품 주문 번호, 그 외→기타 비용 번호 (Discussion #2818로 확정, 문서 서술은 간략함) |
| productOrderType | string | - | 정산 대상 구분(26종, settle/case와 동일 카탈로그) |
| detailType | string | - | 상세 유형, 11개 enum(아래) |
| status | string | - | 증빙 상태, 4개 enum: `VOUCH_PUBLICATION`(원주문 매출) · `VOUCH_CANCEL`(주문 취소) · `VOUCH_RSTOR_PUBLICATION`(공제/환급) · `VOUCH_RSTOR_CANCEL`(환급 취소) |
| productName | string | - | 상품명 |
| totalSalesAmount | number | **필수** | 총 매출 금액 |
| taxationSalesAmount | number | **필수** | 과세 매출 금액 |
| taxExemptionSalesAmount | number | **필수** | 면세 매출 금액 |
| creditCardAmount | number | **필수** | 신용카드 금액 |
| cashInComeDeductionAmount | number | **필수** | 현금영수증 소득공제 금액 |
| cashOutGoingEvidenceAmount | number | **필수** | 현금영수증 지출 증빙 금액 |
| cashExclusionIssuanceAmount | number | **필수** | 현금영수증 발행 제외 금액 |
| otherAmount | number | **필수** | 기타 금액 |
| merchantId | string | - | 가맹점 ID |
| merchantName | string | - | 가맹점명 |
| pagination.* | - | **필수** | 공통 페이지네이션 |

**`detailType` 11개 값**: `VOUCH_DETAIL_PAYMENT_SETL`(결제 대금 정산) · `VOUCH_DETAIL_PRODUCT_COUPON_SETL`(혜택 정산(상품 할인)) · `VOUCH_DETAIL_ORDER_COUPON_SETL`(혜택 정산(스토어 할인)) · `VOUCH_DETAIL_DLVFEE_COUPON_SETL`(혜택 정산(배송비 할인)) · `VOUCH_DETAIL_RTNDLV`(공제/환급(반품 배송비)) · `VOUCH_DETAIL_ETCDLV`(공제/환급(기타)) · `VOUCH_DETAIL_DCCNCL`(공제/환급(복수구매 할인 취소)) · `VOUCH_DETAIL_DLVREC`(공제/환급(배송비 금액 변동)) · `VOUCH_DETAIL_DLCNCL`(공제/환급(배송비 할인 금액 변동)) · `VOUCH_DETAIL_COUPON_SETL`(혜택 정산) · `VOUCH_DETAIL_DDTN_RSTOR`(공제/환급)

### 에러 코드
`400`(날짜·기간 제약·페이지)/`500`. 실측: `GW.AUTHN`(401) — 애플리케이션에 [정산] API 그룹 권한 누락 시(Discussion #1205).

### 모호한 점 / NOT IN DOCS
- "전월 말일까지"의 정확한 판정 기준 시각(호출 시점 KST 자정 기준인지 등)은 문서·Discussion 모두 명확한 문구 없음(NOT IN DOCS).
- 날짜 범위 자체의 최대 폭(예: 최대 몇 개월)은 문서 미기재(NOT IN DOCS) — "전월 말일까지"라는 상한만 있고 하한(과거 몇 년까지)은 불명.

---

## 5. GET /v1/pay-settle/vat/daily — 일별 부가세 내역 조회
출처: https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-vat-daily.md

### 목적
결제건의 **일별 부가세 집계**. 부가가치세 신고·회계 마감 워크플로의 헤더 데이터.

### 요청 파라미터
`vat/case`와 동일: `startDate`(필수, 전월 말일까지) · `endDate`(필수, 전월 말일까지) · `pageNumber`(필수, 최소 1) · `pageSize`(필수, 최대 1000).

### 응답 필드 (`elements[]`)
| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| settleBasisDate | string(date) | - | 정산 기준일 |
| totalSalesAmount | number | **필수** | 총 매출 금액 |
| taxationSalesAmount | number | **필수** | 과세 매출 금액 |
| taxExemptionSalesAmount | number | **필수** | 면세 매출 금액 |
| creditCardAmount | number | **필수** | 신용카드 금액 |
| cashInComeDeductionAmount | number | **필수** | 현금영수증 소득공제 금액 |
| cashOutGoingEvidenceAmount | number | **필수** | 현금영수증 지출 증빙 금액 |
| cashExclusionIssuanceAmount | number | **필수** | 현금영수증 발행 제외 금액 |
| otherAmount | number | **필수** | 기타 금액 |
| merchantId | string | - | 가맹점 ID |
| merchantName | string | - | 가맹점명 |
| pagination.* | - | **필수** | 공통 페이지네이션 |

이 문서는 5종 중 유일하게 **"사용 enum 카탈로그" 섹션이 없음**(응답에 enum 필드가 없어서 — status/detailType 등은 vat/case 전용).

### 에러 코드
`400`(날짜 범위·전월 말일 초과·페이지)/`500`.

### 모호한 점 / NOT IN DOCS
- `vat/case`처럼 `productOrderType`/`orderId`가 없어 **개별 주문으로 드릴다운이 불가능** — 일별 합계만 존재. 세무 신고 마감 후 특정 주문의 세액을 찾으려면 `vat/case`를 별도로 조회해야 함(문서에 명시 없으나 스키마상 자명).

---

## llms.txt "## 정산" 섹션 — 인접 문서 목록 (딥페치 안 함)
정본 색인(정정된 URL) `https://apicenter.commerce.naver.com/llms/llms.txt`의 `## 정산` 섹션에는 정확히 이 5종만 등재되어 있음(추가 정산 전용 문서 없음 — 충전금 잔액 조회, 정산 예정 별도 API 등은 존재하지 않음, 확인됨).

간접적으로 "정산"을 언급하지만 다른 도메인 섹션(커머스솔루션)에 속해 있어 딥페치하지 않은 문서:
| 문서 | URL | 정산과의 관계 |
|---|---|---|
| GET /v1/commerce-solutions/transactions - 비즈월렛 결제 내역 조회 | https://apicenter.commerce.naver.com/llms/get-v1-commerce-solutions-transactions.md | "정기 매출 동기화나 정산 검수에 활용" — 비즈월렛(외부 솔루션 결제) 전용, FOMS는 커머스솔루션마켓 입점사가 아니므로 무관 |
| POST /v1/commerce-solutions/external-transactions - 외부 개발사 자체 결제 내역 전송 | https://apicenter.commerce.naver.com/llms/post-v1-commerce-solutions-external-transactions.md | "솔루션 외부 매출을 판매자 정산에 합산" — 쓰기(POST) API, FOMS 무관 |
| PUT /v1/commerce-solutions/subscriptions/{accountUid}/unsubscription 등 구독 해지 API 2종 | (생략) | "정산 마감 확인 후 호출" 정도의 부수 언급, 정산 데이터 자체와 무관 |

## GitHub Discussions 조사 결과 (commerce-api-naver/commerce-api)
검색: `gh api graphql`(search type:DISCUSSION)로 `pay-settle`·`정산 제한`·`부가세`·`시간대 KST` 등 질의. 관련 스레드 및 요지:

| 주제 | Discussion | 핵심 내용 |
|---|---|---|
| 정산 기준일/예정일/완료일 차이 | [#414](https://github.com/commerce-api-naver/commerce-api/discussions/414) | 기준일=정산대상 확정일, 예정일=은행처리 예정일, 완료일=은행처리 완료일(입금 완료 후에만 존재). 완료건 조회는 예정일 기준 권장 |
| 건별 정산 조회 가능 시점 | [#3028](https://github.com/commerce-api-naver/commerce-api/discussions/3028) | 결제완료(상품주문번호 발번) 즉시 조회 가능하나, **실제 정산은 주문종료(구매확정/반품교환완료) 후 1영업일째** 진행. 미종료 주문은 3개 정산일 필드가 전부 null |
| 정산 데이터 소급 변경 | [#3123](https://github.com/commerce-api-naver/commerce-api/discussions/3123), [#3674](https://github.com/commerce-api-naver/commerce-api/discussions/3674) | 실사례로 정산 기준일 소속이 이후 바뀐 것이 확인됨. 공식 답변: 변경 가능성 낮다면서도 롤링 재조회 권장, 완결 시점 API 미제공 |
| 일별 정산 필터 기준일 | [#1481](https://github.com/commerce-api-naver/commerce-api/discussions/1481) | `settle/daily`는 **정산 예정일 기준**으로 합산. 일별 공제/환급만 별도 조회하는 API는 없음 |
| RateLimit 429 (QUOTA_LIMIT) | [#3709](https://github.com/commerce-api-naver/commerce-api/discussions/3709) | `settle/case` 호출 중 HTTP 429 + `gncp-gw-quota-limit: 5`(HOURS) 수신 사례. 원인=토큰 발급 API가 OAuth2 표준 미준수 → 벌칙성 제한. 또한 **settle/case는 기간 조회 미지원**이라 일 단위 호출만 가능함이 이 스레드에서 재확인 |
| 토큰 발급 규격 강화 공지 | [#3751](https://github.com/commerce-api-naver/commerce-api/discussions/3751) | `/v1/oauth2/token` 요청이 규격(form-urlencoded body, grant_type=client_credentials, SELF타입엔 account_id 미포함 등) 미준수 시 **토큰 발급 자체가 시간당 1회로 제한**. 등록된 IP 중 하나라도 비표준 호출하면 전체 제한 유지 |
| Rate Limit/Quota 정책 문의 | [#2999](https://github.com/commerce-api-naver/commerce-api/discussions/2999) | 공식 답변: **"내스토어 애플리케이션"은 Quota limit 미적용**(대행사 앱만 해당) |
| IP 등록 개수 제한 | [#2096](https://github.com/commerce-api-naver/commerce-api/discussions/2096) | 2024-09-11부터 내스토어 애플리케이션은 호출 IP **최대 3개**로 제한(FOMS 메모리의 "Railway static egress IP 3개" 제약과 일치) |
| 앱 종류별 토큰 분리 | [#2788](https://github.com/commerce-api-naver/commerce-api/discussions/2788) | "API데이터솔루션(통계)" 앱 토큰으로 `settle/daily` 호출 시 403(`GW.AUTHN`). **"내스토어 애플리케이션" 토큰만 사용해야 함** |
| [정산] API 그룹 권한 누락 | [#1013](https://github.com/commerce-api-naver/commerce-api/discussions/1013), [#1205](https://github.com/commerce-api-naver/commerce-api/discussions/1205) | `GW.AUTHN` 오류 시 커머스API센터에서 애플리케이션에 [정산] API 그룹 권한이 등록돼 있는지 확인 필요 |
| vat/case의 productOrderId 의미 | [#2818](https://github.com/commerce-api-naver/commerce-api/discussions/2818) | `productOrderType=DELIVERY`면 `productOrderId`는 배송비 번호(원 상품주문번호와 별도 채번), `PROD_ORDER`면 기존 상품주문번호 |
| maximumSellingInterlockCommissionAmount 의미 | [#3447](https://github.com/commerce-api-naver/commerce-api/discussions/3447) | 실부과 아닌 상한값. 값 없으면 상한 미설정 |
| 혜택 정산 금액 상세 미제공 | [#3649](https://github.com/commerce-api-naver/commerce-api/discussions/3649) | `benefitSettleAmount`는 합산값만 제공, 스마트스토어센터 엑셀의 항목별 금액과 API로 매칭 불가 |
| 매출 연동 수수료 타입 필드 폐지 | [#3590](https://github.com/commerce-api-naver/commerce-api/discussions/3590) | `sellingInterlockCommissionType` 필드가 2026-08-19부로 응답에서 제거(이미 지난 시점, 현재 문서에도 필드 없음과 정합) |
| POST_ORDER_ADJUSTMENT_AMOUNT 의미 | [#3780](https://github.com/commerce-api-naver/commerce-api/discussions/3780) | 부분취소/반품에 따른 배송비 변동 정산건. `productName`="배송비금액변동"/"배송비할인금액변동"으로 식별 |
| 날짜/시간 포맷 규약 | [#32](https://github.com/commerce-api-naver/commerce-api/discussions/32) | 커머스API 전체가 **한국 표준시(UTC+9)** 기준으로 응답 생성(정산 API 개별 확인은 아니나 플랫폼 공통 규약) |

검색했으나 정산 API에 특정되는 내용을 찾지 못한 주제: **데이터 보관/보존 기간**(정산 한정 스레드 없음, NOT IN DOCS — 참고로 FOMS 메모리엔 네이버 피드 전반 보존 1년 실측치가 있으나 정산 API 전용 확인은 아님), **명시적 초당 Rate Limit 수치**(정산 API 한정 수치는 문서·Discussion 어디에도 없음, #3709의 "시간당 5회"는 정상치가 아니라 규격 위반 벌칙치).

---

## 교차 엔드포인트 분석

### 조인 키
| 키 | 등장 엔드포인트 | 비고 |
|---|---|---|
| `orderId` / `orderNo` | settle/case(`orderId`), commission-details(`orderNo`), vat/case(`orderId`) | 필드명이 `settle/commission-details`만 `orderNo`로 다름(주의) |
| `productOrderId` | settle/case, commission-details, vat/case | **`productOrderType`에 따라 번호 체계가 다름**(#2818) — DELIVERY/EXTRAFEE는 상품주문번호와 별개 채번이므로 단순 문자열 매칭만으론 상품 마스터와 조인 불가, `productOrderType=PROD_ORDER`인 행만 FOMS 주문 테이블과 직접 매칭 가능 |
| `productOrderType` | settle/case, commission-details, vat/case | 26종 enum 공유 — 3개 endpoint가 같은 원장을 서로 다른 관점(정산금액/수수료/부가세)으로 절단한 것 |
| `settleType` | settle/case, commission-details | 7종 enum 공유(정산/취소/환급 방향) — vat/case에는 없고 대신 `status`(4종)가 유사 역할 |
| `settleBasisDate`/`settleExpectDate`/`settleCompleteDate` | settle/case, commission-details, settle/daily(범위형: Start/End) | settle/daily는 `startDate`/`endDate` 파라미터가 **예정일(settleExpectDate) 기준**(#1481)이므로, 건별 API를 정확히 합산 대조하려면 `periodType=SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE`로 맞춰 조회해야 함 |
| `merchantId`/`merchantName` | 5종 전부 | 복수 스토어(가맹점) 운영 시 그룹핑 키. FOMS는 단일 스토어로 추정되나 확인 필요 |
| `commissionType` + `productOrderId` | commission-details 단독 | 동일 `productOrderId`가 수수료 유형별로 여러 행으로 쪼개짐 — 분개 시 복합키로 사용(문서 서술 명시) |

### 일별 합계(settle/daily) ↔ 건별(settle/case) 관계
- `settle/daily.paySettleAmount`/`commissionSettleAmount`/`benefitSettleAmount`/`deductionRestoreSettleAmount` 등은 `settle/case`의 대응 필드를 **같은 정산 예정일**로 합산한 것으로 추정(설계상 자연스러움, 문서에 명시적 "합계=합산" 문구는 없어 NOT IN DOCS로 표기하되 필드명 대응이 1:1이라 사실상 확정적).
- 단, `settle/case`는 기간 조회가 안 되므로(단일일만) 한 달치 검증을 하려면 하루씩 반복 호출 후 클라이언트에서 합산·대조해야 함(운영 비용 큼 — #3709에서 사용자가 지적한 바로 "한달치 수집에 6시간" 문제와 직결).
- `settle/daily`에는 `commissionType`/`payMeansType` 분해가 없으므로, 수수료 항목별 브레이크다운이 필요하면 반드시 `commission-details`를 별도로 당겨야 함.

### VAT case/daily ↔ Settle case/daily 관계
- 두 계열은 **서로 다른 절단 축**: Settle 계열(`settleType`)은 "얼마가 정산(입금)되는가", VAT 계열(`status`: VOUCH_PUBLICATION/VOUCH_CANCEL/VOUCH_RSTOR_PUBLICATION/VOUCH_RSTOR_CANCEL)은 "세금계산서/영수증 증빙이 어떻게 발행·취소되는가"를 나타냄.
- `vat/case`에는 `settleType`이 없고 `detailType`(11종, 결제대금/혜택/공제환급 구분)과 `status`(4종, 발행/취소/공제환급/환급취소)로 대체 — 같은 `productOrderId`를 두 API에서 조회하면 Settle 쪽 부호(+/-)와 VAT 쪽 `status`가 대응 관계를 이루지만 **enum 값이 서로 다른 체계**라 자동 매핑 규칙은 문서에 없음(NOT IN DOCS, 매핑표는 실데이터로 역산 필요).
- `vat/case`·`vat/daily`는 "전월 말일까지"만 조회 가능 — 즉 **당월 실시간 매출은 부가세 관점에서 확인 불가**, 반면 `settle/case`·`settle/daily`는 그런 제약이 없어 실시간에 가깝게 조회 가능. 대시보드에서 "이번 달 매출"은 Settle 계열로, "지난달 확정 부가세"는 VAT 계열로 분리 설계해야 함.

### 충전금 정산 vs 계좌이체 정산
- `settle/daily.settleMethodType`: `ACCOUNT`(계좌 이체)면 `bankType`/`depositorName`/`accountNo`가 채워져 실제 은행 입금 채널을 특정할 수 있음. `CHARGE_AMT`(충전금)면 이 3개 필드가 비고, 대신 `minusChargeAmount`(마이너스 충전금 상계 금액)로 잔액 상계 흐름을 추적.
- 충전금은 네이버가 보유한 판매자의 선불 잔액(광고비 등 결제용)이며, 정산액이 이 잔액과 상계될 경우 실제 은행 이체가 발생하지 않음 — **입금 대사 시 `ACCOUNT` 행만 은행 거래내역과 매칭 대상**이고 `CHARGE_AMT` 행은 "정산은 됐지만 통장엔 안 찍히는" 금액이므로 별도 라벨링 필요.

### "일별 정산 마감·입금 대사" 워크플로 요구사항 (설계용 메모)
1. **소스**: `settle/daily`(헤더, settleMethodType별 총액) + `settle/case`(전표, productOrderId 단위) + `commission-details`(수수료 분해) 3종 조합 필요. `settle/daily` 단독으론 상품별 드릴다운 불가.
2. **적재 주기**: `settle/case`가 기간조회 불가이므로 **일 배치**(전일자 `searchDate` 1회 호출)가 기본형이나, #3123/#3674의 소급 변경 리스크 때문에 **최근 N일(예: 7~30일) 롤링 재조회**로 덮어써야 최종적으로 정확함 — "완결" 신호가 API에 없어 재조회 외에 확정 방법이 없음.
3. **매칭**: 은행 입금 대사는 `settle/daily`에서 `settleMethodType=ACCOUNT`인 행을 `bankType`+`accountNo`+`settleExpectDate`(또는 CompleteDate)로 실제 은행 거래와 매칭. `CHARGE_AMT` 행은 별도 "충전금 잔액 변동" 리포트로 분리.
4. **금액 검증**: 일별 헤더 합계와 건별 합계가 어긋나면(반올림/타이밍 차이 제외) 소급 변경 의심 → 재조회로 재검증.
5. **부가세 마감**: 월말 마감 후 `vat/daily`로 당월 확정치를 한 번 더 당겨 세무 신고용 스냅샷으로 별도 보관(사후 변경 가능성 배제를 위해 "확정본" 플래그 필요 — FOMS 쪽 설계 사항, 네이버 API가 확정 여부를 알려주지 않으므로 자체적으로 "익월 5일 이후 재조회분=확정"처럼 규칙을 정해야 함, NOT IN DOCS라 추정 설계).

---

## 데이터 카탈로그 (모든 획득 가능 데이터 포인트)

| # | 엔드포인트 | 필드 | 타입 | 의미 | 대시보드 활용 아이디어 |
|---|---|---|---|---|---|
| 1 | settle/case | settleBasisDate | date | 정산 대상 확정일 | 일자별 정산 확정 추이 차트 X축 |
| 2 | settle/case | settleExpectDate | date | 은행 처리 예정일 | 입금 예정 캘린더/알림 |
| 3 | settle/case | settleCompleteDate | date | 은행 처리 완료일 | 입금 완료 여부 뱃지 |
| 4 | settle/case | payDate | date | 결제일 | 결제~정산 리드타임 계산 |
| 5 | settle/case | orderId | string | 주문 번호 | FOMS 주문 매칭 키(1차) |
| 6 | settle/case | productOrderId | string | 상품주문/배송비/기타비용 번호 | FOMS 주문 매칭 키(2차, productOrderType=PROD_ORDER 한정) |
| 7 | settle/case | productOrderType | enum(26) | 정산 대상 구분 | 항목 유형별 필터(상품/배송비/리뷰적립/렌탈 등) |
| 8 | settle/case | settleType | enum(7) | 정산/취소/환급 구분 | 취소·환급 비중 KPI, 부호 반전 로직 |
| 9 | settle/case | productId, productName | string | 상품 정보 | 상품별 정산액 랭킹 |
| 10 | settle/case | purchaserName | string | 구매자명 | 고객별 정산 내역 조회(개인정보 취급 주의) |
| 11 | settle/case | paySettleAmount | number | 결제 정산 금액(=기준금액) | 총 매출 정산액 합계 |
| 12 | settle/case | totalPayCommissionAmount | number | 총 네이버페이 수수료 | 수수료 총액 KPI |
| 13 | settle/case | freeInstallmentCommissionAmount | number | 무이자 할부 수수료(판매자 부담) | 할부 프로모션 비용 분석 |
| 14 | settle/case | sellingInterlockCommissionAmount | number | 매출 연동 수수료 | 수수료 구성 파이차트 |
| 15 | settle/case | benefitSettleAmount | number | 혜택 정산 금액(합산치) | 프로모션 비용 추정(상세는 불가) |
| 16 | settle/case | settleExpectAmount | number | 정산 예정 금액 | 입금 예정액 KPI |
| 17 | settle/case | merchantId, merchantName, contractNo | string | 가맹점/계약 정보 | 멀티 스토어 그룹핑 |
| 18 | commission-details | commissionBasisAmount | number | 수수료 기준 금액 | 수수료율 역산 검증 |
| 19 | commission-details | commissionType | enum(14) | 수수료 유형 | 수수료 유형별 스택 바 차트 |
| 20 | commission-details | payMeansType | enum(16) | 결제 수단 | 결제수단별 수수료 비교 |
| 21 | commission-details | commissionAmount | number | 실부과 수수료 | 수수료 유형×결제수단 매트릭스 |
| 22 | commission-details | maximumSellingInterlockCommissionAmount | number | 매출연동수수료 상한 | 상한 도달 임박 경고 |
| 23 | commission-details | taxReturnDate | date | 세금 신고 기준일 | 세무 마감 캘린더 |
| 24 | settle/daily | settleBasisStartDate/EndDate | date | 정산 기준 구간 | 일별 마감 헤더 타임라인 |
| 25 | settle/daily | settleAmount | number | 정산 금액(순액) | 일별 순정산액 라인 차트(대시보드 핵심 지표) |
| 26 | settle/daily | commissionSettleAmount | number | 수수료 정산 합계 | 일별 수수료 추이 |
| 27 | settle/daily | deductionRestoreSettleAmount | number | 공제 환급 합계 | 공제/환급 추이 |
| 28 | settle/daily | payHoldbackAmount | number | 지급 보류 금액 | 보류 알림/예외 처리 큐 |
| 29 | settle/daily | minusChargeAmount | number | 마이너스 충전금 상계 | 충전금 잔액 변동 추적 |
| 30 | settle/daily | differenceSettleAmount | number | 차액 정산 | 차액 조정 내역 |
| 31 | settle/daily | returnCareSettleAmount | number | 반품안심케어 정산 | 반품케어 비용 KPI |
| 32 | settle/daily | normalSettleAmount vs quickSettleAmount | number | 일반정산/빠른정산 구분액 | 빠른정산 이용 비중·자금 조달 비용 분석 |
| 33 | settle/daily | preferentialCommissionAmount | number | 우대 수수료 환급 | 우대 수수료 혜택 추적 |
| 34 | settle/daily | settlementLimitAmount | number | 한도 보류/해제 | 한도 이슈 알림 |
| 35 | settle/daily | settleMethodType | enum(2) | ACCOUNT/CHARGE_AMT | **입금대사 분기 키**(계좌이체 vs 충전금) |
| 36 | settle/daily | bankType, depositorName, accountNo | string/enum(63) | 입금 계좌 정보 | 은행별 입금 확인, 계좌 마스킹 표시 |
| 37 | vat/case | detailType | enum(11) | 부가세 상세 유형 | 결제대금/혜택/공제환급 구분 차트 |
| 38 | vat/case | status | enum(4) | 증빙 상태 | 발행/취소/환급 상태 배지 |
| 39 | vat/case, vat/daily | totalSalesAmount | number | 총 매출 금액 | 세무 신고용 총매출 |
| 40 | vat/case, vat/daily | taxationSalesAmount | number | 과세 매출 | 부가세 신고 과세표준 |
| 41 | vat/case, vat/daily | taxExemptionSalesAmount | number | 면세 매출 | 면세 항목 분리 |
| 42 | vat/case, vat/daily | creditCardAmount | number | 신용카드 결제분 | 카드매출 비중 |
| 43 | vat/case, vat/daily | cashInComeDeductionAmount | number | 현금영수증 소득공제분 | 현금영수증 신고자료 |
| 44 | vat/case, vat/daily | cashOutGoingEvidenceAmount | number | 현금영수증 지출증빙분 | 지출증빙 신고자료 |
| 45 | vat/case, vat/daily | cashExclusionIssuanceAmount | number | 현금영수증 발행제외분 | 발행제외 사유 추적 |
| 46 | vat/case, vat/daily | otherAmount | number | 기타 금액 | 잔여 항목 검증용 |
| 47 | 전 5종 | pagination.totalElements | integer | 총 건수 | 대시보드 데이터 완전성 카운터(적재 검증) |

---

## 참고: 원문 fetch 파일 위치(로컬 임시)
- `%LOCALAPPDATA%\Temp\get-v1-pay-settle-settle-case.md` 외 4종 동일 디렉토리(세션 로컬, 저장소 미포함).
