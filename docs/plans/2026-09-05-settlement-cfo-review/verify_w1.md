# verify_w1 — W1(정확성 A·기간 귀속 C) 반박 검증 (2026-09-05)

- 워크트리 `C:/tmp/foms-s-settle-cfo`(HEAD 7100e2aa1)에서만 코드를 읽었다. DB 는 `postgresql_readonly=True` SELECT 만, API 는 GET 만, 버튼·POST 0회.
- 스냅샷: 검증 시각 2026-09-05 11:0x~11:2x KST, `sync.rev 19`, `last_ok_at 2026-09-04T20:38:03`. 워커 rev19 와 같은 적재 상태이나 **오늘 날짜가 하루 넘어가 기본 창이 08-05~09-18 → 08-06~09-19 로 이동**했다(워커의 `from_0806` 대조군과 같은 수: 수수료 −9,673,426 · 보류 −89,003,279 · 대사 158,017,440). 층 간 대사는 같은 스냅샷 안에서만 견줬다.
- 화면: gstack browse, 세션 쿠키는 requests 로그인(302) 뒤 파일 import → 즉시 삭제. 스크린샷 `vw1_default_month_tip.png`·`vw1_default_month_tip2.png`·`vw1_mar_month_tip.png`. 콘솔 오류 2건(400)은 내가 `to` 를 먼저 채워 from>to 역전이 난 순간의 요청이며 최종 화면의 error 노드는 hidden — 결함 아님.
- 산출: `vw1_a02.py/_result.json`, `vw1_a01_a03.py/_result.json`, `vw1_c01.py/_result.json`, `vw1_probes.py/_result.json`, `vw1_extra.py/_result.json`, `vw1_prev_window_result.json`, API 원문 `vw1_api_*.json`.

## 1. FAIL·WARN 판정

| ID | 판정 | 재무 영향 성격 | 심각도 |
|---|---|---|---|
| W1-A-02 전기 = 같은 일수 직전 구간 | **CONFIRMED** | 실측(원 단위) | WARN 유지 |
| W1-C-01 8월 3축 한 화면 불가·합계 줄 없음 | **CONFIRMED** | 추정(오해 가능, 금액 오류 아님) | WARN 유지 |
| W1-A-01 워터폴 마지막 단 = 완료+예정 | **CONFIRMED** | 실측(차 10,211,240) | WARN 유지 |
| W1-A-03 예정액 세부 계좌0·충전금0 | **CONFIRMED** | 추정(오해 가능) | WARN 유지 |
| W1-A-04 대사 배너 금액 개념 미표기(INFO) | CONFIRMED | — | INFO |
| W1-C-02 지급 소요일 지표 부재(INFO) | CONFIRMED | — | INFO |

### W1-A-02 — CONFIRMED
- 코드 재독: `foms/services/settlement_channel.py:322-335` `_previous_range` = `(from−span, from−1)`, span=일수. 달력 월 분기 없음. `1240` 에서 `build_channel_dashboard` 가 그대로 씀. 비채널 탭 `settlement_aggregation.py:275 _previous_month_range` 는 달 인덱스 기준 — 두 탭의 "전기" 정의가 다르다(워커 주장 그대로).
- API·DB 재실측(`vw1_a02_result.json`):
  - 2월 조회 → `kpi.prev.settled_amount` 210,426,677 = DB 01-04~01-31 210,426,677; 1월 전체 215,844,737 → **−5,418,060**(01-02 행) — 워커 수치 재현.
  - 5월 조회 → prev 196,962,724 = DB 03-31~04-30; 4월 전체 187,628,053 → **+9,334,671**; `daily_prev` 2버킷 `[03-01 9,334,671, 04-01 187,628,053]` — 재현.
  - **추가 표본 3월 조회**(워커 미검) → prev 242,824,664 = DB 01-29~02-28; 2월 전체 213,462,485 → **+29,362,179(+13.8%)**, `daily_prev` `[01-01 29,362,179, 02-01 213,462,485]`. 워커가 든 표본보다 큰 오차.
  - 음성 대조군: 8월 조회 → prev 182,517,772 = 7월 전체(diff 0).
  - 건수도 같은 규칙: 2월 prev.case_count 605 = DB 01-04~01-31 605(1월 전체 635).
- 화면(`vw1_mar_month_tip.png`, 3월·월 단위): 타일 "정산 완료액 ₩146,131,644 ▼ -39.8% 전기 대비"(전기 242,824,664 기준). 라벨은 "전기"뿐.
- 재무 영향: 실측. 전기 대비 % 가 2월 화면 −5.4M, 3월 화면 +29.4M, 5월 화면 +9.3M 만큼 틀린 분모를 쓴다. 장부 금액엔 영향 없음(비교 지표) → WARN 유지.

### W1-C-01 — CONFIRMED
- API 재실측(`vw1_c01_result.json`, 8월·basis 4종): KPI `settled_amount` 4종 모두 34,013,589(축 무관 — 결정 사항). `ledger` 키 집합 = `axis·groups·kind·pagination·rows` — **합계 금액 키 없음**. 그룹 합(손합산) = DB 원 단위 일치: 예정일 155,725,306/457건 · 완료일 155,725,306/457 · 결제일 87,891,578/259(shifted_out 262) · 기준일 157,762,507/468(shifted_out 1). 그룹 금액 컬럼은 `settle_expect_amount`(`settlement_channel.py:229`), 대사 배너는 `pay_settle_amount`(`:734-744`), KPI 는 `settle_amount` — 세 개념이 한 화면에 라벨 없이 공존.
- 프론트 재독: `channel.js:1745-1766` 원장 머리엔 축·되돌림·excluded·shifted_out 만, 합계 줄 없음(`vw1_c01_result.json` `js_has_sum_line_in_ledger_head false`). 바닥 `:1825-1837` 은 건수만. 화면 `w4_kpi.png`·`vw1_default_month_tip.png` 원장 머리 "표 날짜 축: 정산 예정일 기준 · 위 KPI·차트는 늘 정산 예정일 기준" 확인.
- 완료일 8월 = 예정일 8월(스테이징 완료 행 217/217 예정일=완료일, `db_daily_expect_ne_complete n_diff 0`) — 워커와 동일. 운영에서 예정일≠완료일 행이 있으면 차이가 생기나 W1 권한 밖(워커 §5-4 와 같음).
- 재무 영향: 금액 오류 없음, 오해 가능(추정). WARN 유지.

### W1-A-01 — CONFIRMED
- API 오늘 기본 창(`vw1_a01_a03_result.json`): 워터폴 Σ1~6단 59,340,735 = 7단 `settle_amount` 59,340,735 = Σdaily.settle_amount = **정산 완료액 49,129,495 + 정산 예정액 10,211,240** = DB `settled+expected`(21행). 코드 `_daily_totals` `:503-519` 가 `settle_amount` 를 완료/예정으로만 가르고 `_build_waterfall` `:684-697` 은 `totals["settle_amount"]`(둘의 합)을 그린다.
- 음성 대조군(전부 완료된 창, 8월): 7단 34,013,589 = 정산 완료액, 예정 0 → 관계식이 "완료액+예정액"임을 양쪽에서 확인.
- 화면(`vw1_default_month_tip.png`, 오늘 rev19): 타일 "정산 완료액 ₩49,129,495" · "정산 예정액 ₩10,211,240", 워터폴 표 마지막 "정산 금액 ₩59,340,735", 카드 부제 "결제 정산액에서 차감·가산을 거쳐 정산 금액까지"(`channel.js:1378`) — 합 관계 설명 없음. 툴팁 마지막 단 "정산 금액 ₩59,340,735 기간 합계".
- 재무 영향: 실측(차 = 예정 파티션 10,211,240). WARN 유지.

### W1-A-03 — CONFIRMED
- API: `expected_amount 10,211,240`, `expected_account_amount 0`, `expected_charge_amount 0`. DB 창 안 미완료 행 1개(09-07, `settle_method_type NULL`, `bank_type NULL`, `depositor_name '*'`) → `_daily_totals` `:512-517` 가 ACCOUNT/CHARGE_AMT 만 더하므로 둘 다 0(`expected_method_blank 10,211,240`).
- 화면(`vw1_default_month_tip.png`): 타일 "정산 예정액 ₩10,211,240 / 아직 은행 미입금 · 계좌 ₩0 · 충전금 상계 ₩0"(`channel.js:1207-1208`), 입금 채널 카드 "미정(정산 예정) ₩10,211,240 (1건)" — 같은 화면의 두 곳이 다른 규칙.
- 표본 한계(워커 미기재): 전 테이블 미완료 일별 행은 **1행뿐**(`db_expected_method_dist_all` NULL n=1). "네이버가 예정일 전 행의 방식을 늘 비워 보낸다"는 rev14(524,535)·rev19(10,211,240) 같은 09-07 파티션 두 스냅샷 관측이라 일반화는 표본 1 파티션 기준이다. 완료 행은 ACCOUNT 216·CHARGE_AMT 1(2025-10-14 −763).
- 재무 영향: 오해 가능(추정). WARN 유지.

### W1-A-04 / W1-C-02 (INFO) — CONFIRMED
- A-04: `_build_reconcile` `:734-744` 가 `pay_settle` 만 비교. 화면 배너 "일별 합계 ₩158,017,440 vs 건별 합계 ₩158,017,440 → 차이 ₩0 대사 일치"(`vw1_default_month_tip.png`)에 금액 개념 낱말 없음.
- C-02: `grep -i "lag|소요일|days_to|elapsed|lead_time"` 커널 1건(docstring)·`channel.js` 0건.

## 2. PASS 축 거짓 초록 검사 (`vw1_probes_result.json`)

| 축 | 표본 | 결과 |
|---|---|---|
| A-1 3중 대사 | rev14 CSV 3종을 워커 스크립트와 무관하게 재파싱해 rev14 API 와 대조 | 일별 CSV settled 49,129,495 · expected 524,535 · 수수료 −10,889,232 · 보류 −116,969,098 · 결제 정산 177,512,360, 건별 CSV Σ결제 정산 177,512,360 · Σ정산 예정 166,623,128(=API groups 합), 시트 Σ정산기준금액 177,512,360 — 전부 API 와 원 단위 일치. 음성 대조군: 건별 음수 행 2건이라 절대값 합 ≠ 부호 합(참), 창 밖 날짜 행 0, 계좌 마스킹 `****NNNN` 전행 |
| A-2 대사 허용 오차 | 코드 `Decimal` 정확 비교 재독 + 실화면 | 오늘 창 daily 158,017,440 = case 158,017,440, diff 0, 배너 "대사 일치" |
| A-4 취소 부호 | 워커가 안 고른 두 번째 취소 건 `2026080684513091`(08-11) | DB −100,000/−93,370/+3,630 = API 행·raw `paySettleAmount −100000` = CSV "−100000/−93370 정산 후 취소"; 원 정산 짝(08-07 +100,000/+93,370) 양수 그대로. 08-11 Σcase 1,239,000(3건) = daily pay_settle 1,239,000 = API 버킷. 유형 필터 `NORMAL_SETTLE_AFTER_CANCEL` 2건 전부 음수 = DB 2건 −101,000 |
| C-2 월 경계 | 06-30/07-01 월 단위 | 버킷 `2026-06-01` 6,526,198 · `2026-07-01` 1,893,544 = DB 행 그대로, 건수 30=30. 날짜 컬럼 8개 전부 `date` 타입(information_schema), raw `settleExpectDate` 길이 10 이 6,303/6,303, DB 세션 TZ `Etc/UTC` 는 date 컬럼에 무관 |
| A-5 부가세 관계 | 워커 표본 외 2026-06·2025-11·2026-03 | vat_daily = vat_case = Σcase pay_settle(기준일 월): 175,171,910 / 247,058,460 / 163,631,870. 음성 대조군: 6월을 예정일 축으로 묶으면 197,029,340 ≠ 175,171,910(축이 다르면 달라야 하고 실제로 다르다) |

거짓 초록 없음. 워커 PASS 판정 유지.

## 3. 반박 중 새로 발견한 결함

### VW1-N-01 [WARN·기간귀속] 월·주 단위 차트의 "전기" 값이 KPI 의 "전기"와 다른 구간을 가리킨다(부분 월 스텁이 현 버킷에 짝지어짐)
- 근거(화면): `vw1_default_month_tip.png` — 오늘 기본 창 월 단위, 8월 막대 툴팁 "₩65,289,179 전기 2026-06-01". 65,289,179 = DB 06-22~06-30(전기 구간의 9일 스텁)이고 KPI 타일의 전기(06-22~08-05)는 247,806,951(`vw1_prev_window_result.json`). 같은 화면 9월 막대 툴팁 "₩182,517,772 전기 2026-07-01"(7월 전체). `vw1_mar_month_tip.png` — 3월 조회 막대 툴팁 "₩29,362,179 전기 2026-01-01"(01-29~01-31 3일 스텁) vs KPI "▼-39.8% 전기 대비"(242,824,664) vs 달력 2월 213,462,485 — **한 화면에 서로 다른 "전기" 셋**.
- 근거(API·코드): `vw1_api_default_month.json` `daily` 2버킷 vs `daily_prev` 3버킷(`06-01 65,289,179 · 07-01 182,517,772 · 08-01 0`); 3월 `daily` 1 vs `daily_prev` 2. `settlement_channel.py:1248` 가 `_build_daily(prev_rows, prev_from, prev_to, granularity)` 로 전기 구간 날짜를 그대로 버킷화하고, `channel.js:558` `for (i < values.length && i < groupCount)`·`:1366` `prevDaily[i]` 가 **인덱스로** 현 버킷과 짝짓는다.
- 재무 영향(실측): 3월 화면에서 차트 전기 29,362,179 vs KPI 전기 242,824,664(8.3배 차). 장부 금액 아님(비교선).
- 뿌리는 W1-A-02 와 같다(비교 창 정의). 권고: 전기 버킷을 현 버킷과 같은 개수·같은 오프셋으로 만들거나(달 단위면 달력 월 시프트), 최소한 인덱스 짝짓기 대신 버킷 오프셋으로 짝짓기. 노력 S.

### VW1-N-02 [INFO·기간귀속/표시] 월·주 버킷의 `completed` 가 전부-아니면-전무라 완료+예정이 섞인 버킷이 통째로 "(정산 예정)"으로 표시된다
- 근거: 툴팁 "2026-09-01 (정산 예정) ₩25,327,146 정산 금액"(`vw1_default_month_tip2.png`, JS 덤프 `vw1_extra` 실행 로그). DB 9월 = 완료 15,115,906 + 예정 10,211,240(`vw1_extra_result.json` `db_sep_split`). 코드 `settlement_channel.py:523` `"completed": bool(done) and all(done)`, 툴팁 `channel.js:1362`, 스파크 `:1201`(완료 타일 = `completed ? settle_amount : 0` → 9월 버킷 0)·`:1209`(예정 타일 스파크에 25,327,146 전부).
- 재무 영향(실측): 월 단위 화면에서 완료분 15,115,906 이 "정산 예정" 버킷으로 읽힌다. 일 단위에서는 발생하지 않음(행 단위 플래그).
- 권고: `_daily_bucket` 에 완료/예정 합을 따로 실어(행마다 이미 `_daily_totals` 가 가르는 것과 같은 규칙, 재계산 아님) 섞인 버킷은 "일부 완료" 로. 노력 S.

### VW1-N-03 [INFO·기간귀속] 기본 창(오늘−30~오늘+14)의 전기 비교가 미실현 14일을 포함한 창과 전부 실현된 45일을 견준다
- 근거: `vw1_prev_window_result.json` — 기본 창 08-06~09-19 정산 완료액 49,129,495(09-06~09-19 는 행 1·완료 0) vs 전기 06-22~08-05 247,806,951 → 화면 "▼ -80.2% 전기 대비"(`vw1_default_month_tip.png`). 실현 구간만 같은 길이로 견주면(08-06~09-05 vs 07-07~08-05) 49,129,495 vs 156,115,475 → −68.5%. 차이 11.7%p 는 창 정의에서만 나온다.
- 재무 영향(실측): 비교 지표 왜곡, 금액 아님. W1-A-02·N-01 과 같은 뿌리(비교 창 정의). 권고: 완료액 타일의 전기는 실현된 날짜까지만 같은 길이로 잡거나 창을 라벨에 명시("직전 45일 대비"). 노력 S.

## 4. 심각도·재무 영향 성격 판정
- W1-A-02: 실측(원 단위 diff). WARN 적정 — 장부 금액이 아니라 비교 지표.
- W1-C-01: 추정(오해 가능). 인용 금액 4종은 실측. WARN 적정.
- W1-A-01: 실측(차 10,211,240). WARN 적정.
- W1-A-03: 추정(오해 가능). 표본 1 파티션 한계 명시 필요. WARN 적정.
- 과장·축소 없음. 심각도 변경 없음.

## 5. UNVERIFIABLE / 한계
- 없음(전건 재현). 단 W1-C-01 의 "완료일 8월 ≠ 예정일 8월" 은 스테이징에 차이 표본이 없어(217/217 동일) 운영 데이터로만 실증 가능 — W1 권한 밖(워커 §5-4 와 동일).
- 툴팁 캡처는 `.s-ch-ghit` focus 이벤트로 띄웠다(마우스 hover 와 같은 `showTip` 경로, `channel.js:596-599`).
