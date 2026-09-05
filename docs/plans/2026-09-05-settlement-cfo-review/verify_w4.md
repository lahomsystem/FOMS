# VW4 — W4(표시·부채) 반박 검증 원장 (2026-09-05)

- 워크트리 `C:/tmp/foms-s-settle-cfo`(pwd 확인, HEAD 7100e2aa1). 읽기 전용: 코드 읽기·스테이징 SELECT/EXPLAIN(`postgresql_readonly=True`)·스테이징 GET·gstack browse 화면 조작(글자 크기 조절기만, 원복함). 동기화·받아오기 버튼 미클릭. 쓰기는 `OUT/verify_w4.md`·`OUT/vw4_*` 만.
- 스테이징 시계 2026-09-05, 기본 창 08-06~09-19(워커 09-04 산출물은 08-05~09-18 창). 숫자 차이는 창 차이이며 정의 판정에는 영향 없음.
- 산출: `vw4_db.py/json`(SQL 12개+EXPLAIN 4개, `vw4_explain_*.txt`), `vw4_api.py/json`(API·CSV 13회), `vw4_measure.js`·`vw4_100_measure.json`·`vw4_150_measure.json`·`vw4_150_ancestors.json`·`vw4_150_kpi.json`, 스크린샷 `vw4_100_waterfall.png`·`vw4_100_top.png`·`vw4_150_waterfall.png`·`vw4_150_top.png`·`vw4_150_ledger.png`, `vw4_probe.py/json`, `vw4_pytest.txt`.

## 1. 판정 표

| ID | 판정 | 재무 영향 | 심각도 | 한 줄 근거 |
|---|---|---|---|---|
| W4-G-01 | CONFIRMED | 실측(763원·기간귀속 0행) | WARN 유지 | `channel.js:1201` 부제 "정산 완료일 기준" vs `_daily_totals` 529~545 는 예정일 창(`_daily_rows` 470~) 안 완료 행 합, 방식 무관. DB: CHARGE_AMT 완료 행 1건 id 367(2025-10-14, -763)·완료일≠예정일 0/218 |
| W4-G-02 | CONFIRMED | 실측 | WARN 유지 | `_build_holdback` 551~596 단순 합. DB 09-04 창 보류 14행 -119,379,098 + 해제 1행 +2,410,000 = -116,969,098(화면 `w4_kpi.png` 일치); 09-05 창 13행 -91,413,279 + 2,410,000 = -89,003,279(화면 `vw4_150_kpi.json` 일치). 그 해제 +2,410,000 의 보류 짝은 06-19(창 밖) → 창 안 순액은 발생액도 잔액도 아님이 데이터로 증명됨 |
| W4-G-03 | CONFIRMED | 실측 | WARN 유지 | 라벨 원문 재확인: export.py 195 "결제 정산 금액"·235·242 "정산 예정 금액"·320 "정산기준금액"·323 "정산예정금액", channel.js 118 "결제 정산"·120 "정산 예정"·1204 "정산 예정액"(=`_daily_totals` 541 미완료 `settle_amount`). CSV 합 재계산(`vw4_probe.json`): case "정산 예정 금액" 155,725,306(457행) / daily "정산 금액" 34,013,589(19행) / sheet 155,725,306 — 워커 숫자와 동일 |
| W4-G-04 | CONFIRMED | 없음(오해 가능) | WARN 유지 | `_build_reconcile` 734~745 `pay_settle` 만 비교·오차 0. 배너 문자열 `channel.js:1509~1520` 에 필드명 없음. 화면 `w4_kpi.png`·`vw4_100_top.png` "일별 합계 … vs 건별 합계 … 차이 ₩0 대사 일치" |
| W4-G-05 | CONFIRMED | 실측(건수) | WARN 유지 | API 재현(`vw4_api.json`): 기본 창 exceptions 64(UNMATCHED 50 상한+HOLDBACK 14) vs `kpi.unmatched_count` 418, strip `exception_count` 64·`unmatched_count` 418; 연초 창 125(50+50+25) vs 4,265(1,386+2,879). DB 모집단 동일(418 / 4,265, `vw4_db.json` g05_*). 응답에 total/truncated 키 0. `channel.js:1541` 배지 = `exceptions.length`, `:2343` 스트립은 `exception_count` 만 그림(`unmatched_count` 는 받고도 안 그림). 완화 요소: 매칭률 타일 부제가 "FOMS 미연결 418건"을 같은 화면에 씀 |
| W4-G-06 | CONFIRMED | 없음 | WARN 유지 | 재현: `kind=case&type=X` → 200 CSV 0행·파일명 `naver_settle_case_20260801_20260831.csv`(조건 없는 파일과 동일), `q=zzzz-no-such` 동일, `type=PROD_ORDER` 457행 동일 파일명. 코드 `_filter_clauses` 539~569 enum 대조 없음, `export_filename` 710~732 인자에 type/q 없음. 음성 대조군: `daily&type=X` 400 JSON, `kind=nope` 400 JSON |
| W4-G-07 | CONFIRMED | 없음 | WARN 유지 | 100%·1440×900 실화면 `vw4_100_waterfall.png`: "지급보류·한"(x 1244~1300)과 "충전금상계"(1297~1351) 3px 겹침(`vw4_100_measure.json` pairs 1). `shortStepLabel` 1416~1419 `slice(0,6)` |
| W4-G-08 | CONFIRMED(증상) · **원인 정정** | 없음 | WARN 유지 | 150% 실측(`vw4_150_measure.json`): scrollWidth 1675 > 1440, 워터폴 교차 6쌍(`vw4_150_waterfall.png` 판독 불가), Y축 "5,000만" 왼쪽 클립. **워커의 원인("표가 overflow-x:auto 컨테이너 안에 있지 않아")은 틀렸다** — 표는 `.s-ch-tablewrap { overflow-x:auto }`(`settlement-channel.css:316`, `channel.js:1648`) 안에 있다. 실제 원인(`vw4_150_ancestors.json`): `details.s-ch-group`(display:block, **min-width:auto**, 실측 1650px)이 `display:grid` `.s-ch-ledger-body`(1414px, 암묵 auto 트랙)의 그리드 아이템이라 min-content 로 부풀어 격자를 뚫는다(래퍼 1648 = details 1650 > 본문 1414). 따라서 워커 권고 "래퍼 overflow-x:auto 한 줄"은 무효(이미 있음). KPI 값 넘침은 데이터 의존: 오늘 -₩89,003,279 는 +1px(`vw4_150_kpi.json`), 워커 -₩116,969,098 은 +13px |
| W4-H-01 | CONFIRMED | 실측(ms) · 재무 없음 | WARN 유지 | EXPLAIN 재실행(`vw4_explain_h01_*.txt`): COALESCE 술어 q3 Seq Scan 2.586ms·q2 1.942ms·commission 4.977ms. **음성 대조군**: 같은 창을 `search_date BETWEEN` 으로 주면 `Index Scan using ix_nsc_unmatched` 0.49ms → COALESCE 가 원인임을 증명. 추가 사실: case 6,303행·commission 13,984행 모두 `settle_expect_date IS NULL` 0·`≠ search_date` 0(`vw4_db.json` h01_*) — 커널 docstring 601~604 "사실상 같은 날"이 데이터로 참. 규칙 위반은 실재, 체감 0 이므로 WARN 적정 |
| W4-H-02 | CONFIRMED | 없음 | WARN 유지 | `scripts/ops/pre_push_smoke.ps1:214~241` 서브셋에 `test_settlement_*` 0건(직접 읽음), `-Full` 만 전체(209~212). `.github/workflows/ci.yml:109` 전체 스위트. 핀 값 직접 확인: 셸 20·21·423·424 `20260903d`, 채널 22·425 `20260903i`, `test_settlement_channel_render.py:72` `_CHANNEL_PIN="20260903i"`·476 `assert pins == {_CHANNEL_PIN}` |

INFO 2건(W4-H-03·H-04)은 FAIL/WARN 이 아니라 반박 대상 밖 — 코드 라인(`shortStepLabel`·핀 리터럴 등)은 위 검증 중 부수적으로 일치 확인.

## 2. 거짓 초록 검사 (워커 PASS 표본 찌르기)

| 축 | 표본 | 결과 |
|---|---|---|
| G CSV 형식 | 워커가 안 본 창(7월) `commission` + `sheet&basis=complete` (`vw4_api.json` gpass_*, `vw4_probe.json`) | PASS 재확인 — BOM `efbbbf`, CRLF 939/430·LF 단독 0, sheet 파일명 슬러그 `_complete` 있음·헤더 7열 일치, commission 금액 셀 1,876/1,876 평문 정수(`bad 938` 은 검사 스크립트가 enum 열 "수수료 유형"을 오선택한 것 — 표본 값 PAY_COMMISSION, 금액 열 불량 0) |
| G 음성 대조군 | `daily&type=X`·`kind=nope`·비로그인 export | 400 JSON·400 JSON·302 `/login`(파일 아님) — 발동해야 할 것이 발동 |
| G 다크 NOT-A-DEFECT | `static/js/foms/theme.js:43~48` | `resolveAppliedTheme` 이 비모바일 뷰포트면 무조건 `'light'` — 워커 판정 유지 |
| G 콘솔·네트워크 | 채널 탭 진입 → 150% 조작 → 100% 원복 | 콘솔 에러 0, 4xx/5xx 0 (`browse console --errors`·`network`) |
| H 스트립 질의 6 | `build_channel_strip` 을 readonly 세션으로 재실행(`vw4_probe.json` hpass_strip_statements) | 6 문장(daily·case·sync_runs·system_settings), 그중 case 3문장이 COALESCE 술어 — H-01 과 정합 |
| H TTFB | strip ×3 | 144·220·244ms(워커 135ms 중앙값과 같은 급) |
| pytest | `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/domains -k settlement -q -p no:cacheprovider` (워크트리) | `922 passed, 5739 deselected, 1 warning in 24.30s`(`vw4_pytest.txt`) — 기준선 동일 |

## 3. 새 발견 (반박 중 나온 것)

### VW4-G-08a (WARN · 표시) G-08 가로 스크롤의 근본 원인은 래퍼 부재가 아니라 그리드 아이템 `min-width:auto`
- 근거: `vw4_150_ancestors.json` — `.s-ch-tablewrap` w1648 ovx:auto minW:0 / 부모 `details.s-ch-group` w1650 **minW:auto** display:block / 조부모 `.s-ch-ledger-body` w1414 display:grid scrollW 1662. `settlement-channel.css:302`(`.s-ch-ledger-body { display:grid; min-width:0 }`)·`:316`(`.s-ch-tablewrap { overflow-x:auto }`)·`:307`(`.s-ch-group` 에 min-width 없음).
- 권고: `.foms-settle .s-ch-group { min-width: 0; }` 한 줄(또는 `.s-ch-ledger-body { grid-template-columns: minmax(0, 1fr) }`). 워커의 "래퍼 overflow-x:auto" 권고는 적용해도 변화 0. 노력 S. 재무 영향 없음.

### VW4-H-01a (INFO · 유지보수) COALESCE 축은 현재 데이터에서 항등식
- 근거: `vw4_db.json` h01_expect_null_vs_search — case 6,303행 중 `settle_expect_date IS NULL` 0·`≠ search_date` 0, commission 13,984행 동일. 커널 `_case_scope` docstring 601~604 의 "사실상 같은 날"이 참.
- 뜻: 식 인덱스(워커 권고)는 유효하지만, 도입 뒤 `ANALYZE` 후 EXPLAIN 으로 실제 채택을 확인해야 한다(표현식이 정확히 `COALESCE(settle_expect_date, search_date)` 와 일치해야 플래너가 탄다). 술어를 `search_date` 로 바꾸는 우회는 의미(미확정 건 보호)가 달라지므로 권고하지 않음.

## 4. 결정 재고 · 교차 참조
- G-02 검증 중 본 해제 양수 4행 중 2행(07-15 +1,505,900·07-23 +440,000)은 같은 금액의 앞선 보류가 없음 — W2 가 이미 "분할 해제"(`findings_w2.md:35`, 1/6 -1,945,900 의 2회 분할)로 규명했으므로 여기서는 재보고하지 않음. 부호 규약 결정("같은 금액의 양수 행")은 부분 해제를 포함하도록 문구만 넓히면 됨(W2 축).

## 5. 확인 못 한 것
- 없음. 10건 전부 직접 재현.
