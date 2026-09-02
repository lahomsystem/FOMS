# GET /v1/pay-settle/settle/daily - 일별 정산 내역 조회

네이버페이 정산의 일별 합계 내역을 조회하는 API로, 가맹점·내부 회계 시스템에서 일자별 정산 적재 마감과 입금 대사(은행 이체·충전금) 워크플로우의 헤더 데이터를 가져오는 데 사용합니다. 호출 시 startDate·endDate·pageNumber·pageSize 네 가지가 모두 필수이며, 응답은 정산 기준 시작/종료일·정산 예정일·정산 완료일과 함께 정산 금액·결제 정산 금액(=정산 기준 금액)·수수료/혜택/공제 환급 정산 금액·지급 보류·마이너스 충전금 상계·차액 정산·반품안심케어 정산·일반/빠른정산 금액·우대 수수료 환급·한도 보류/해제 금액·정산 방법(ACCOUNT/CHARGE_AMT)·은행(bankType)·예금주·계좌번호·가맹점 정보로 구성된 페이지 목록을 반환합니다. 정산 방법이 ACCOUNT 인 경우 bankType·depositorName·accountNo 로 실제 입금 채널을 확인할 수 있고, CHARGE_AMT 의 경우 마이너스 충전금 상계 금액과 함께 충전금 잔액 흐름을 추적합니다. 적재 시 settleCompleteDate 기준으로 누락 없이 가져오려면 pagination 의 totalPages 까지 순회하며, 빠른정산·일반정산 금액을 별도 컬럼으로 보존해 자금 일정 분석에 활용합니다. 400 응답은 날짜·페이지 파라미터를, 500 응답은 서버·DB 일시 오류로 보고 백오프 후 동일 페이지를 재시도하여 적재 누락을 방지합니다.

> Base URL: https://api.commerce.naver.com/external

### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:----:|------|
| startDate | query | string(date) | 필수 | 시작일 |
| endDate | query | string(date) | 필수 | 종료일 |
| pageNumber | query | integer(int32) | 필수 | 페이지 번호. 최소 1 |
| pageSize | query | integer(int32) | 필수 | 페이지 크기(1000 이하). 최대 1000 |

### 응답 스키마

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:----:|------|
| elements | - | array | 필수 |  |
| elements.settleBasisStartDate | - | string(date) |  | 정산 기준 시작일(yyyy-MM-dd) |
| elements.settleBasisEndDate | - | string(date) |  | 정산 기준 종료일(yyyy-MM-dd) |
| elements.settleExpectDate | - | string(date) |  | 정산 예정일(yyyy-MM-dd) |
| elements.settleCompleteDate | - | string(date) |  | 정산 완료일(yyyy-MM-dd) |
| elements.settleAmount | - | number |  | 정산 금액 |
| elements.paySettleAmount | - | number |  | 결제 정산 금액(=정산 기준 금액) |
| elements.commissionSettleAmount | - | number |  | 수수료 정산 금액 |
| elements.benefitSettleAmount | - | number |  | 혜택 정산 금액 |
| elements.deductionRestoreSettleAmount | - | number |  | 공제 환급 정산 금액 |
| elements.payHoldbackAmount | - | number |  | 지급 보류 금액 |
| elements.minusChargeAmount | - | number |  | 마이너스 충전금 상계 금액 |
| elements.differenceSettleAmount | - | number |  | 차액 정산 금액 |
| elements.returnCareSettleAmount | - | number | 필수 | 반품안심케어 정산 금액 |
| elements.normalSettleAmount | - | number |  | 일반 정산 금액 |
| elements.quickSettleAmount | - | number |  | 빠른정산 금액 |
| elements.preferentialCommissionAmount | - | number |  | 우대 수수료 환급 금액 |
| elements.settlementLimitAmount | - | number |  | 한도 보류/해제 금액 |
| elements.settleMethodType | - | string |  | 정산 방법(계좌 이체, 충전금)<br>- ACCOUNT(계좌 이체)<br>- CHARGE_AMT(충전금). 허용값: `ACCOUNT`, `CHARGE_AMT` |
| elements.bankType | - | string |  | 은행<br>- KDB(산업은행)<br>- IBK(기업은행)<br>- KB(KB국민은행)<br>- KEB_OLD(외환은행)<br>- SUHYUP(수협은행)<br>- KOREAEXIM(수출입은행)<br>- NH(NH농협은행)<br>- LNH(지역농.축협)<br>- WOORI(우리은행)<br>- SC(SC제일은행)<br>- CITI(한국씨티은행)<br>- IM(iM뱅크)<br>- BUSAN(부산은행)<br>- KWANGJU(광주은행)<br>- JEJU(제주은행)<br>- JEONBUK(전북은행)<br>- KYONGNAM(경남은행)<br>- SAEMAUL(새마을금고)<br>- SHINHYUP(신협)<br>- FSB(저축은행)<br>- HSBC(HSBC은행)<br>- DEUTSCHE_BANK(도이치은행)<br>- JP_MORGAN(제이피모간체이스)<br>- BOA(BOA은행)<br>- BNP(비엔피파리바은행)<br>- ICBC(중국공상은행)<br>- NFCF(산림조합중앙회)<br>- POST(우체국)<br>- KEB_HANA(하나은행)<br>- SHINHAN(신한은행)<br>- KBANK(케이뱅크)<br>- KKOBANK(카카오뱅크)<br>- TOSS(토스뱅크)<br>- DAISHIN_BANK(대신저축은행)<br>- SBISB(에스비아이저축은행)<br>- HK_BANK(에이치케이저축은행)<br>- WELCOME_BANK(웰컴저축은행)<br>- SHINHAN_SAVING(신한저축은행)<br>- DONGYANG_SEC(유안타증권)<br>- HYNDAI_SEC(KB증권)<br>- IBK_IVST_SEC(IBK투자증권)<br>- MIRAEASSET(미래에셋대우)<br>- MIRAEASSET_DAEWOO(미래에셋대우)<br>- SANSUNG_SEC(삼성증권)<br>- HANGKOOK_IVST_SEC(한국투자증권)<br>- WOORI_IVST_SEC(NH투자증권)<br>- KYOBO_IVST_SEC(교보증권)<br>- HI_IVST_SEC(하이투자증권)<br>- HMC_IVST_SEC(현대자증권)<br>- KIWOOM_IVST_SEC(키움증권)<br>- EBEST_IVST_SEC(이베스트투자증권)<br>- SK_SEC(SK증권)<br>- DAESHIN_SEC(대신증권)<br>- HANWHA_SEC(한화투자증권)<br>- HANA_DAETOO_SEC(하나금융투자)<br>- SHINHAN_IVST(신한금융투자)<br>- DONGBU_SEC(DB금융투자)<br>- EUGENE_IVST_SEC(유진투자증권)<br>- MERITZ_SEC(메리츠증권)<br>- NH_NONGHYUP_SEC(NH농협증권)<br>- BOOKOOK_SEC(부국증권)<br>- SHINYOUNG_SEC(신영증권)<br>- LIG_IVST_SEC(케이프투자증권)<br>- KSFC(한국증권금융). 허용값: `KDB`, `IBK`, `KB`, `KEB_OLD`, `SUHYUP`, `KOREAEXIM`, `NH`, `LNH`, `WOORI`, `SC`, `CITI`, `IM`, `BUSAN`, `KWANGJU`, `JEJU`, `JEONBUK`, `KYONGNAM`, `SAEMAUL`, `SHINHYUP`, `FSB`, `HSBC`, `DEUTSCHE_BANK`, `JP_MORGAN`, `BOA`, `BNP`, `ICBC`, `NFCF`, `POST`, `KEB_HANA`, `SHINHAN`, `KBANK`, `KKOBANK`, `TOSS`, `DAISHIN_BANK`, `SBISB`, `HK_BANK`, `WELCOME_BANK`, `SHINHAN_SAVING`, `DONGYANG_SEC`, `HYNDAI_SEC`, `IBK_IVST_SEC`, `MIRAEASSET`, `MIRAEASSET_DAEWOO`, `SANSUNG_SEC`, `HANGKOOK_IVST_SEC`, `WOORI_IVST_SEC`, `KYOBO_IVST_SEC`, `HI_IVST_SEC`, `HMC_IVST_SEC`, `KIWOOM_IVST_SEC`, `EBEST_IVST_SEC`, `SK_SEC`, `DAESHIN_SEC`, `HANWHA_SEC`, `HANA_DAETOO_SEC`, `SHINHAN_IVST`, `DONGBU_SEC`, `EUGENE_IVST_SEC`, `MERITZ_SEC`, `NH_NONGHYUP_SEC`, `BOOKOOK_SEC`, `SHINYOUNG_SEC`, `LIG_IVST_SEC`, `KSFC` |
| elements.depositorName | - | string |  | 예금주 |
| elements.accountNo | - | string |  | 계좌 번호 |
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

- 응답 `elements[].settleMethodType`: `ACCOUNT`, `CHARGE_AMT`
- 응답 `elements[].bankType`: `KDB`, `IBK`, `KB`, `KEB_OLD`, `SUHYUP`, `KOREAEXIM`, `NH`, `LNH`, `WOORI`, `SC`, `CITI`, `IM`, `BUSAN`, `KWANGJU`, `JEJU`, `JEONBUK`, `KYONGNAM`, `SAEMAUL`, `SHINHYUP`, `FSB`, `HSBC`, `DEUTSCHE_BANK`, `JP_MORGAN`, `BOA`, `BNP`, `ICBC`, `NFCF`, `POST`, `KEB_HANA`, `SHINHAN`, `KBANK`, `KKOBANK`, `TOSS`, `DAISHIN_BANK`, `SBISB`, `HK_BANK`, `WELCOME_BANK`, `SHINHAN_SAVING`, `DONGYANG_SEC`, `HYNDAI_SEC`, `IBK_IVST_SEC`, `MIRAEASSET`, `MIRAEASSET_DAEWOO`, `SANSUNG_SEC`, `HANGKOOK_IVST_SEC`, `WOORI_IVST_SEC`, `KYOBO_IVST_SEC`, `HI_IVST_SEC`, `HMC_IVST_SEC`, `KIWOOM_IVST_SEC`, `EBEST_IVST_SEC`, `SK_SEC`, `DAESHIN_SEC`, `HANWHA_SEC`, `HANA_DAETOO_SEC`, `SHINHAN_IVST`, `DONGBU_SEC`, `EUGENE_IVST_SEC`, `MERITZ_SEC`, `NH_NONGHYUP_SEC`, `BOOKOOK_SEC`, `SHINYOUNG_SEC`, `LIG_IVST_SEC`, `KSFC`

### 호출 예시

```bash
curl -X GET 'https://api.commerce.naver.com/external/v1/pay-settle/settle/daily?startDate={startDate}&endDate={endDate}&pageNumber={pageNumber}&pageSize={pageSize}' \
  -H 'Authorization: Bearer {access_token}'
```
