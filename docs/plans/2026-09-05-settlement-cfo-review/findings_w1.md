# findings_w1 — 정확성(A)·기간 귀속(C) 감사 (W1, 2026-09-04/05)

- 워크트리 `C:/tmp/foms-s-settle-cfo` (branch session/settle-cfo, base 7100e2aa1). 코드 라인은 전부 이 트리 기준.
- 스테이징 스냅샷 2개를 다뤘다. **rev14** = 2026-09-04 16:43 KST(`sync.last_ok_at 2026-09-03T20:38:53`), **rev19** = 2026-09-05 05:38 KST 스케줄 동기화 뒤(`last_ok_at 2026-09-04T20:38:03`, `naver_settle_sync_runs` id 18·19·20 OK/SCHEDULE). 두 스냅샷 사이에 09-07 예정 파티션이 1건 524,535 → 30건 10,211,240 으로 바뀌었다. 층 간 대사는 **같은 스냅샷 안**에서만 견줬다.
- OUT = `C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo`. 아래 경로는 OUT 상대.
- 읽기 전용: DB 는 `postgresql_readonly=True` SELECT 만, API 는 GET 만, 버튼·POST 0회.

## 1. 축별 판정

| 축 | 판정 | 근거 한 줄 |
|---|---|---|
| A 정확성(3중 대사) | **WARN** | 4층(API·DB 일별·DB 건별·CSV 3종) 원 단위 전부 일치(rev14), rev19 도 API=DB 일치, 양끝 포함·취소 부호·NEGATIVE 양성/음성 대조군 전부 통과. WARN 은 숫자가 아니라 **숫자를 잇는 문구 3곳**(워터폴 마지막 단=완료+예정, 전기=같은 일수, 예정액 세부 계좌0·충전금0) |
| C 기간 귀속(축·월말) | **WARN** | 월 경계 KST 달력 날짜(원문↔컬럼 불일치 0/218·0/6,303, 시각 없음), 버킷 경계 정확. WARN 은 "8월 정산액" 3축을 한 화면에서 못 얻음(원장 축 전환 뒤 합계 줄 없음 + 금액 개념 미표기) |

## 2. 발견 목록 (심각도 순)

### W1-A-02 [WARN·기간귀속] 전기 비교가 "달력 전월"이 아니라 "같은 일수 직전 구간"이고 화면은 그 사실을 말하지 않는다
- 현상: `_previous_range`(`foms/services/settlement_channel.py:322-335`) = `(from−span, from−1)`, span=일수. 달 단위 조회에서 직전 달의 길이가 다르면 잘리거나 넘친다.
  - 2월 조회(02-01~02-28) → 전기 = 01-04~01-31. `kpi.prev.settled_amount` 210,426,677 = DB 01-04~01-31 합 210,426,677, 1월 전체 215,844,737 → **5,418,060원 과소**(01-02 행). `w1_a3_result.json` c·db_jan_full·db_jan_0104_0131, `w1_fresh_db_result.json` db_jan_1_to_3.
  - 5월 조회(05-01~05-31) → 전기 = 03-31~04-30. `daily_prev` 가 **두 버킷** `['2026-03-01' 9,334,671, '2026-04-01' 187,628,053]`, `kpi.prev.settled_amount` 196,962,724, 4월 전체 187,628,053 → **9,334,671원 과대(+5.0%)** + 차트에 유령 "전기 2026-03-01" 막대. `w1_api2_result.json` may_month, `w1_fresh_db_result.json` db_mar31_apr·db_apr_full.
  - 음성 대조군: 8월 조회(31일) → 전기 07-01~07-31 = 7월 전체 182,517,772 정확(`w1_a3_result.json` a·db_jul_full). 9월 조회 → 전기 08-02~08-31 = 8월 전체 34,013,589 와 같지만 이는 08-01(토) 행 0 인 우연(`db_0801` n=0).
- 라벨: `static/js/settlement/channel.js:1156` `' 전기 대비'`, `1199/1206/1215/1229` `'전기 비교 기준 없음'`, `1329` `'전기 비교(정산 금액)'`, `1366` `'전기 ' + prevRow.date`. "전월"도 "직전 N일"도 아닌 "전기". 화면 `w4_kpi.png` 상단 타일 "▼-80.2% 전기 대비".
- 같은 정산 화면의 다른 탭은 **달력 월 정렬**: `foms/services/settlement_aggregation.py:275 _previous_month_range` "직전의 동일 개월수 구간", `tests/domains/test_settlement_aggregation.py:833`. 채널 탭만 일수 규칙 → 두 탭의 "전기"가 다른 구간이다.
- 계약 테스트 없음: `tests/domains/test_settlement_channel_*.py` 에 `_previous_range` 의미를 고정한 테스트 없음(키 집합만 `test_settlement_channel_api.py:219-220`).
- 재무 영향(실측): 2월 화면 전기 −5,418,060원, 5월 화면 전기 +9,334,671원. 전기 대비 % 가 그만큼 틀린다.
- 권고(근본): 달 단위(`granularity=month`)일 때 전기를 달력 월(직전 동일 개월수)로 정렬해 집계 탭과 정의를 맞추거나, 최소한 라벨을 "직전 N일" 로. KPI 재집계가 아니라 비교 창 정의 문제. 노력 S.

### W1-C-01 [WARN·기간귀속/표시] "8월 정산액" 3축을 한 화면에서 얻을 수 없고, 원장 축을 바꿔 얻는 합은 KPI 와 다른 금액 개념이다
- 8월 3축 실측(`w1_c1_result.json`):
  - 예정일 8월(KPI): 정산 완료액 **34,013,589**(19행, expected 0). `api_aug.expect.kpi_settled` = DB `db_expect_aug`.
  - 완료일 8월: DB 일별 34,013,589(19행) — 스테이징은 완료 행 217/217 이 완료일=예정일이라 예정일 축과 동일(`db_daily_expect_ne_complete` n_diff 0). 건별 165,992,120(457건).
  - 결제일 8월(건별): **93,647,600**(259건). 기준일 8월(건별): **168,134,680**(468건) = 부가세 8월 total_sales 168,134,680 과 원 단위 일치(`w1_a5_result.json` vat_monthly 2026-08).
- 화면 조작 경로: 예정일 8월 = 상단 타일 즉시. 완료일·결제일·기준일 8월 = 원장 "표 날짜 축" 전환 → 날짜 그룹 19/25/28개 요약을 **손으로 합산**(KPI 없음). 그룹 요약·행은 `settle_expect_amount`(`_LEDGER_SPEC` `settlement_channel.py:229`) → 합 155,725,306 / 87,891,578 / 157,762,507 (API `ledger.groups` 합 = DB `expect_amt` 정확).
- 금액 개념 3가지가 화면에 설명 없이 섞인다: KPI 정산 완료액 = `settle_amount`(보류 반영 후 실입금) 34,013,589 / 대사 배너 = `pay_settle_amount`(결제 정산액) 165,992,120 / 원장 그룹 = `settle_expect_amount`(수수료 차감 후·보류 전) 155,725,306. 실측 항등식: Σ건별 settle_expect_amount 155,725,306 = 일별 pay+commission 155,725,306; + 보류 −121,711,717 = 정산 완료액 34,013,589 (`w1_fresh_db_result.json` db_aug_identity). 기준일 축에서 부가세 매출 168,134,680 을 찾으면 원장은 157,762,507(차이 10,372,173 = 수수료)로 보인다.
- 원장 머리 문구(`channel.js:1754-1766`): "표 날짜 축: … · 이 축 날짜가 조회 기간 밖인 N건 … · 위 KPI·차트는 늘 정산 예정일 기준" — 축·빠진 수는 말하지만 **이 축·이 기간 합계 금액**과 **금액 개념**은 없다. 바닥(`1831-1837`) "총 485건 · 60건 / 페이지". 파셜 `templates/cs/partials/settlement_channel_body.html:74` "정산 예정일 기준 · 매출 인식(완료일)과 다릅니다" 는 KPI 축만. 화면 `w4_kpi.png` 원장 구간.
- 음성 대조군: 예정일∩완료일 8월 교집합 34,013,589(19행)이 양쪽에 동일하게 들어감(`db_intersect_aug`), 예정일 8월인데 완료일 창 밖 0행·그 반대 0행(`db_expect_aug_complete_outside`·`db_complete_aug_expect_outside` 빈 목록). 결제일 축 `shifted_out 262` = DB `db_gap_pay_date.shifted_out 262`, 기준일 축 1 = 1.
- 재무 영향: 회계팀 오해 가능(같은 "8월"에 34.0M/155.7M/166.0M/168.1M 이 나란히 나올 수 있음). 금액 결함 아님.
- 권고(재집계 아님, 문구·한 줄 수준): 원장 축 머리에 "이 축·이 기간 합계 N건 · Σ정산 예정 금액 X원" 한 줄 + "원장 금액 = 정산 예정 금액(수수료 차감 후·보류 전), 위 KPI 정산 완료액 = 보류 반영 후 실입금" 한 문장. 노력 S.

### W1-A-01 [WARN·표시] 워터폴 마지막 단 "정산 금액"은 정산 완료액 타일이 아니라 완료액+예정액이며 화면이 그 관계를 말하지 않는다
- 실측: rev14 워터폴 Σ1~6단 49,654,030 = 7단 `settle_amount` 49,654,030 = Σdaily.settle_amount = **정산 완료액 49,129,495 + 정산 예정액 524,535**. rev19: 59,340,735 = 49,129,495 + 10,211,240. `w1_a1_result.json` api.waterfall·sum_waterfall_1to6, `w1_api2_result.json` default_fresh.
- 화면 `w4_kpi.png`: 타일 "정산 완료액 ₩49,129,495" 옆 "정산 예정액 ₩524,535", 워터폴 카드 "정산 구성 (기간 합계)" 표 마지막 "정산 금액 ₩49,654,030"(`w4_100_waterfall.png`). 캡션 `channel.js:1378` "결제 정산액에서 차감·가산을 거쳐 정산 금액까지" — 완료+예정 합이라는 말 없음.
- 코드: `_WATERFALL_STEPS` `settlement_channel.py:172-180` 방향 전부 +1, `_build_waterfall` 684-697 부호 그대로(재계산 금지 준수).
- 잔차·항등식(음성 대조군): 워터폴 밖 컬럼(difference·return_care·preferential·quick·limit·benefit·restore·minus_charge) 비영 행 **0/218**(전 기간 2025-10-01~2026-09-07), 6성분 항등식 218/218, normal+quick=settle_amount 218/218(`w1_fresh_db_result.json` db_identity_all, 창 안 `w1_a1_result.json` db_daily_identity 22/22). 잔차 0 이므로 "합이 안 맞는" 결함은 없다.
- 재무 영향: 회계팀 오해 가능(실측 차 524,535 → 10,211,240원, 예정 파티션 크기만큼).
- 권고: 워터폴 표 마지막 줄 아래 "정산 금액 = 정산 완료액 + 정산 예정액(미입금)" 한 줄, 또는 마지막 단을 완료/예정 두 조각으로. 노력 S.

### W1-A-03 [WARN·표시] 정산 예정액 타일 세부 "계좌 ₩0 · 충전금 상계 ₩0" 이 예정액과 맞지 않는다(입금 방식 미정분 미표기)
- 실측: rev14 `expected_amount 524,535`, `expected_account_amount 0`, `expected_charge_amount 0`; rev19 10,211,240 / 0 / 0 (`w1_a1_result.json` api, `w1_api2_result.json` default_fresh). DB 동일(`db_daily` expected_account 0·expected_charge 0). 원인: 네이버가 예정일 전 행의 `settleMethodType` 을 비워 보낸다 — 입금 채널 카드는 이를 "미정(정산 예정) ₩10,211,240 (1건)" 으로 낸다(`w1_api_default_fresh.json` deposit_channels, `_build_deposit_channels` `settlement_channel.py:714-720`).
- 화면 `w4_kpi.png` 타일: "정산 예정액 ₩524,535 / 아직 은행 미입금 · 계좌 ₩0 · 충전금 상계 ₩0". 문구 소스 `channel.js:1204-1210`.
- 음성 대조군: 정산 완료액 타일 49,129,495 = 입금 채널 "계좌 이체 ₩49,129,495 (8건)" 일치.
- 재무 영향: 회계팀 오해 가능(0+0≠예정액). 권고: 타일 세부에 "미정 X원" 을 더하거나 방식이 비면 세부를 "입금 방식 미정" 으로(카드와 같은 규칙). 노력 S.

### W1-A-04 [INFO·표시] 대사 배너 "일별 합계 / 건별 합계" 가 어느 금액인지 말하지 않는다
- 배너 값 177,512,360 은 `pay_settle_amount`(결제 정산액, 워터폴 1단과 같은 수)이지 KPI 의 정산 금액이 아니다. `_build_reconcile` `settlement_channel.py:734-744`, 문구 `channel.js:1509-1511`, 화면 `w4_kpi.png` "일별 합계 ₩177,512,360 vs 건별 합계 ₩177,512,360 → 차이 ₩0". 권고: "결제 정산액 기준" 낱말 추가. 노력 S.

### W1-C-02 [INFO·표시] 결제→지급 시차 지표가 없다 — "평균 지급 소요일" 타일 제안
- 부재 확인: `grep -n -i -E "lag|소요|days_to|elapsed|lead_time"` 커널·`channel.js` 0건(문서 주석 1줄 제외).
- 실측(`w1_c3_result.json`): NORMAL_SETTLE_ORIGINAL 결제일→정산 완료일 n=6,228, 평균 18.19일, 중앙값 17, 최소 1, 최대 74; 월별 평균 17.2~19.7일. 기준일→완료일 평균 1.48일(최대 8). 일별 예정일 vs 완료일: 217/217 같은 날(지연 0·조기 0).
- 제안: 타일 1개 "평균 지급 소요일(결제일→정산 완료일) 18일 · 중앙값 17일" — 날짜 차이라 금액 재계산 아님. 노력 S.

## 3. 통과한 검사 (근거)

### A-1 3중 대사 — PASS
- rev14 (`w1_a1_result.json`, 창 2026-08-05~2026-09-18, channel NAVER):

  | 항목 | API kpi | DB 일별 | CSV daily | DB 건별 | CSV case | CSV sheet |
  |---|---|---|---|---|---|---|
  | settled | 49,129,495 | 49,129,495 | 49,129,495 | — | — | — |
  | expected | 524,535 | 524,535 | 524,535 | — | — | — |
  | expected_account/charge | 0 / 0 | 0 / 0 | 0 / 0 | — | — | — |
  | commission | −10,889,232 | −10,889,232 | −10,889,232 | — | — | — |
  | holdback | −116,969,098 | −116,969,098 | −116,969,098 | — | — | — |
  | pay_settle(대사) | daily 177,512,360 = case 177,512,360, diff 0 | 177,512,360 | 177,512,360 | 177,512,360 | 177,512,360 | 177,512,360(정산기준금액) |
  | settle_amount 합 | Σdaily 49,654,030 | 49,654,030 | 49,654,030 | — | — | — |
  | case_count / unmatched | 485 / 482 | — | 22행 | 485 / 482 | 485행 / 482 | 485행 |
  | Σledger.groups.amount | 166,623,128 | — | — | expect_amt 166,623,128 | 166,623,128 | 166,623,128 |

- rev19 (`w1_api2_result.json` default_fresh ↔ `w1_fresh_db_result.json`): settled 49,129,495 / expected 10,211,240 / commission −11,551,567 / holdback −116,969,098 / 대사 187,861,400=187,861,400 / Σdaily 59,340,735 / case 514 / unmatched 511 / Σgroups 176,309,833 — API=DB 일별=DB 건별 전부 원 단위 일치. (CSV 는 rev19 에서 재수령하지 않음.)
- 양끝 포함(음성 대조군, rev19): `to=2026-09-06` → case_count 484 = 514−30(09-07 건 30), expected 0, commission −10,863,767 = −11,551,567+687,800, 대사 176,962,360 = 187,861,400−10,899,040, Σgroups 166,098,593 = 176,309,833−10,211,240. `from=2026-08-06` → case_count 421 = 514−93, commission −9,673,426(+1,878,141), holdback −89,003,279(+27,965,819), 대사 158,017,440(−29,843,960), settled 불변(08-05 settle_amount 0). 끝·시작 모두 하루치와 정확히 같은 만큼만 변함. (`to=2026-09-17` 대조군은 09-18 행 0 이라 무의미 — 위로 대체.)
- 채널: `naver_settle_daily`·`naver_settle_case` 모두 NAVER 외 0건. 창 안 `settle_expect_date NULL` 0건, 예정일≠조회일 0건.
- CSV: BOM 있음·CRLF, 파일명 `naver_settle_{daily|case|sheet}_20260805_20260918.csv`, 헤더 목록은 `w1_a1_result.json` csv.*.headers.

### A-2 워터폴·대사 — 숫자 PASS(문구는 W1-A-01·04)
- `_build_reconcile` 734-744: `Decimal` 정확 비교, `diff = daily − case`, 허용 오차 없음. `_run_exceptions` 958-963: `if reconcile["diff"]` 일 때만 COUNT_MISMATCH. 실측 diff 0 → 두 스냅샷 모두 exceptions 에 COUNT_MISMATCH 0건(음성 대조군). 양성 대조군은 읽기 전용이라 불가(§5).

### A-3 — W1-A-02 로 보고.

### A-4 취소·환급 부호 — PASS
- 표본 `product_order_id 2026080684513081`(NORMAL_SETTLE_AFTER_CANCEL, 예정일 08-12): DB pay_settle −1,000 / expect −934 / 수수료 +36; API `ledger=case&q=` 행 `pay_settle_amount −1000`, `settle_type_label "정산 후 취소"`, raw `paySettleAmount −1000`, groups [08-12 −934, 08-07 +934]; CSV case "결제 정산 금액 −1000 · 정산 예정 금액 −934 · 정산 후 취소"; 시트 "정산기준금액 −1000 · Npay 수수료 36 · 정산예정금액 −934". 세 층 부호·금액 동일, 상계·절대값 없음(`w1_a4_result.json`).
- 그 날(08-12) 건별 Σpay_settle 6,049,590(20건, 취소 1건 −1,000 포함) = 일별 `pay_settle_amount` 6,049,590 = API daily 버킷 6,049,590. 취소가 KPI 대사에 부호 그대로 들어간다. 창 안 취소 합 −101,000(2건)이 대사 187,861,400 에 포함(`db_cancel_window_sum`).
- NEGATIVE 예외: 그 날 일별 `settle_amount` 0(보류 −5,667,271) → 음수 아님 → 미발동(정상, `_daily_exceptions` 883-898 은 settle_amount<0 만). **양성 대조군**: 전 테이블 유일 음수 일별 행 2025-10-14 settle_amount −763 → API `from=2025-10-01&to=2025-10-31` exceptions 에 `NEGATIVE` 1건 amount −763 date 2025-10-14, daily 버킷 settle_amount −763·commission +37(양수 되돌림) (`w1_api2_result.json` oct2025_day).
- 음성 대조군(정상 행): `2026072630256451` NORMAL_SETTLE_ORIGINAL +550,000 / +524,535 가 API 행·CSV·DB 셋에서 동일 양수.
- 표본 한계: 스테이징 settle_type 은 NORMAL_SETTLE_ORIGINAL(6,258건 2,249,798,480) 과 NORMAL_SETTLE_AFTER_CANCEL(45건 −20,186,300) 둘뿐 — QUICK_SETTLE_CANCEL·NORMAL_SETTLE_BEFORE_CANCEL·QUANTITY_CANCEL_RESTORE 0건(§5).

### A-5 부가세 — 관계 PASS, 전표 충분성은 결정 재고
- `naver_vat_daily` 315행: ts=tx+te 315/315, ts=증빙 5종 합 315/315, 면세 0 전 기간, 음수 일자 2행. 일별=건별 일자 합 315/315 불일치 0(`w1_a5_result.json`).
- 정산과의 관계(실측): 월별 부가세 `total_sales_amount` = Σ`naver_settle_case.pay_settle_amount`(기준일 월) **11개월 전부 원 단위 일치**(2025-10 183,847,180 … 2026-08 168,134,680). 부가세 취소(VOUCH_CANCEL 37건 −20,186,300) = 정산 취소(NORMAL_SETTLE_AFTER_CANCEL 45건 −20,186,300). 즉 부가세 매출 = 결제 정산액(기준일 축), 부가세 포함가.
- API `ledger=vat_case&from=2026-08-01&to=2026-08-31`: vat.total.total_sales 168,134,680(=DB), final true, available_to 2026-08-31, rows 28. 9월 창: final false, total 0, rows 0(당월분 미제공 — 배너 `channel.js:1925`).
- 세액·공급가액 컬럼 없음(`models.py:3856-3864`, 금액 8종은 전부 부가세 포함 매출·증빙 구분) → 전표 작성엔 `taxation_sales×10/110` 손계산 필요. 네이버 API 형상 → §6 결정 재고.

### C-2 월 경계 — PASS
- 컬럼 `Date`(TZ 없음, `models.py:3676-3679`), `parse_settle_date`(`settle_sync.py:270-289`) 문자열 앞 10자, 시각 안 붙임.
- raw 키 확인 뒤 대조(`w1_c2_result.json`): 경계 행 07-31·08-31·09-01 원문 `settleExpectDate/settleCompleteDate` = 컬럼(08-01 행 없음). 불일치 일별 expect 0/218·complete 0/218, 건별 payDate/settleExpectDate/settleCompleteDate/settleBasisDate 0/6,303. 원문에 `T` 0건, 길이≠10 0건.
- `_bucket_key`(344-351) 실측: `granularity=month&from=2026-08-31&to=2026-09-01` → 버킷 `2026-08-01` 14,091,615 · `2026-09-01` 2,785,093 = DB 08-31 14,091,615 · 09-01 2,785,093. 일 단위 동일. 주 단위(08-30~09-07) `2026-08-31` 29,207,521 · `2026-09-07` 10,211,240 = DB `date_trunc('week')`.
- 음성 대조군: 원문=컬럼 행 수 218/218·6,303/6,303 병기(위). 참고: 8/31 하루만 든 달 버킷도 키가 `2026-08-01` — 부분 월이 달 첫날로 이름 붙는 것은 W1-A-02 와 같은 뿌리(경계 자체는 정확).

### C-3 — W1-C-02 로 보고.

## 4. NOT-A-DEFECT
1. KPI·차트·워터폴이 축 셀렉트와 무관하게 예정일 — 결정 사항. 8월 basis 4종 호출 모두 KPI 34,013,589 동일(`w1_c1_result.json` api_aug.*.kpi_settled).
2. 시트 헤더 "정산기준금액" = `pay_settle_amount` — 2026-09-03 확정 7열. 합 177,512,360 이 대사 배너와 같음.
3. rev14→rev19 숫자 변화(예정액 524,535→10,211,240, 건수 485→514) — 09-05 05:30 스케줄 동기화(runs 18·19·20 OK). 각 스냅샷 안에서는 전 층 일치.
4. `from=08-31&to=09-01` 월 호출의 `daily_prev []` — 전기 08-29~08-30 은 주말 0행, `_build_daily` 는 rows 0 이면 `[]`(설계).
5. 9월 조회의 전기가 8월 전체와 같음 — 08-01(토) 0행 우연, 규칙 결함의 반증 아님.
6. 08-05~08-25 일별 settle_amount 0 — 지급 보류가 결제 정산액+수수료를 전액 흡수(6성분 항등식 성립). 보류·해제 짝은 W2 축.
7. 건별 취소 행이 예외 큐 NEGATIVE 로 안 뜸 — NEGATIVE 는 일별 settle_amount<0 만(883-898). 건별 취소는 원장에 부호 그대로("음수는 취소·환급입니다" 바닥 문구 `channel.js:1837`).
8. 부가세 9월 total 0·rows 0 — 미제공 구간을 0 으로 그리지 않음(`channel.js:1917-1925`), `vat.final false`. 화면 확인은 W4.
9. `to=2026-09-17` 대조군 결과가 `to=09-18` 과 동일 — 09-18 행 0 이라 당연(`db_case_0918`·`db_daily_0918` n=0). 양끝 검증은 09-06/08-06 으로 대체.

## 5. 확인 못 한 항목
1. COUNT_MISMATCH 양성 대조군 — 읽기 전용이라 불일치를 만들 수 없음. `tests/domains/test_settlement_channel_*.py` 에 `COUNT_MISMATCH` 문자열 0건(grep) → 테스트 계약도 없어 보임(W4/비평자 확인 요망).
2. QUICK_SETTLE_CANCEL·NORMAL_SETTLE_BEFORE_CANCEL·QUANTITY_CANCEL_RESTORE 부호 — 스테이징 표본 0건.
3. CSV 3종은 rev14 에서만 수령. rev19 는 API↔DB 2층만.
4. 완료일≠예정일 일별 행 0/217 — "예정일 8월 vs 완료일 8월" 차이가 스테이징에선 0. 운영 DB 는 W1 권한 밖.
5. 워터폴 밖 컬럼 5종 비영 행 0건 — 잔차가 생기는 경우의 화면 거동은 표본 부재로 미검증.
6. 화면 실측은 W4 스크린샷(rev14) 인용. rev19 화면 미확인.
7. (참고, W2 축) `naver_settle_sync_runs` 18·19·20 이 2분 간격 SCHEDULE OK 3연속(09-04 20:34~20:38 UTC).

## 6. 결정 재고
1. **파생 세액 표시 허용 여부** — 재계산 금지(D-4)는 네이버 금액 원값 보존이 목적인데, 부가세 탭은 공급가액·세액이 없어(모델 3856-3864) 회계팀이 전표마다 `taxation_sales×10/110` 을 손으로 계산해야 한다. 실측: 과세매출=총매출 11개월 전부, 면세 0. 원값 옆에 "파생(계산)" 라벨을 단 공급가액·세액 두 열을 허용하는 안을 재고 요청(비율 abs 처럼 파생 표시로 취급).

## 7. 산출물
- 스크립트: `w1_client.py`, `w1_a1.py`, `w1_a3.py`, `w1_a4.py`, `w1_a5.py`, `w1_c1.py`, `w1_c2.py`, `w1_c3.py`, `w1_fresh_db.py`, `w1_api2.py`
- 결과: `w1_a1_result.json`, `w1_a3_result.json`, `w1_a4_result.json`, `w1_a5_result.json`, `w1_c1_result.json`, `w1_c2_result.json`, `w1_c3_result.json`, `w1_fresh_db_result.json`, `w1_api2_result.json`
- API 원문: `w1_api_default.json`(rev14), `w1_api_to0917.json`, `w1_api_month_{a,b,c}.json`, `w1_api_aug_{expect,complete,pay,basis}.json`, `w1_api_vat_{aug,sep}.json`, `w1_api_boundary_{month,day,week}.json`, `w1_api_q_cancel.json`, `w1_api_{to_0906,from_0806,may_month,oct2025_day,default_fresh}.json`(rev19)
- CSV(rev14): `w1_daily.csv`, `w1_case.csv`, `w1_sheet.csv`
- 인용 스크린샷(W4 소유): `w4_kpi.png`, `w4_100_waterfall.png`
