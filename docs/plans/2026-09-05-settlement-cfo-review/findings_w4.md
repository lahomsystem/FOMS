# W4 표시·부채 — 발견 원장 (축 G·H + pytest)

- 작성: 2026-09-04 16:36 착수 → 중단 → 2026-09-05 재개·완료. 워크트리 `C:/tmp/foms-s-settle-cfo`(pwd 확인). 읽기 전용.
- 스테이징 시계가 감사 도중 **2026-09-04 → 2026-09-05** 로 넘어갔고 워커 루프가 09-04 20:38 에 한 번 더 돌았다(coverage_to 09-18→09-19, 기본 창 08-06~09-19). 09-04 산출물(`w4_kpi.png`·`w4_channel_text.txt`·CSV·`w4_csv_check.json`)과 09-05 산출물(`w4_exceptions_*`·`w4_vat.png`·`w4_labels_db.json`·`w4_150_kpi_overflow.json`·EXPLAIN·TTFB)은 데이터 스냅샷이 다르다. 숫자 판정에는 쓰지 않았고 라벨·형식·성능 판정에만 썼다.
- `OUT` = `C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo`.

## 0. pytest (워크트리, 캐시 금지)

- 명령: `cd C:/tmp/foms-s-settle-cfo && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/domains -k settlement -q -p no:cacheprovider`
- 첫 줄: `........................................................................ [  7%]`
- 마지막 줄: `922 passed, 5739 deselected, 1 warning in 31.93s` (EXIT=0) — 기준선 922 passed 와 동일. 경고 1건은 정산 무관(`test_erp_order_shared_form_scripts.py:1748` SyntaxWarning).
- 원문: `OUT/w4_pytest.txt`.

## 1. 축별 판정

| 축 | 판정 | 근거 한 줄 |
|---|---|---|
| G 표시·내보내기 | **WARN** | 전표 한 줄을 못 쓰는 라벨 4개(정산 완료액 부제·보류·한도·"정산 예정" 동명이의·대사 배너 대상 금액 미표기), 예외 배지=상한 뒤 표시 건수, 조건 건 CSV 파일명 동일, 100% 워터폴 라벨 절단 "지급보류·한", 150% 워터폴 판독 불가+가로 스크롤(F6 후속). CSV 형식(BOM·CRLF·금액·날짜·헤더 순서·축 슬러그)은 전부 PASS. 다크는 셸 미대응(NOT-A-DEFECT). |
| H 성능·구조 부채 | **WARN** | 스트립 6문장=예산 6 PASS, TTFB 30일 203ms·1년 217ms·프래그먼트 125ms PASS. 그러나 `naver_settle_case` 창 술어(COALESCE)가 case 질의 4종 전부 Seq Scan(1.8~5.9ms, 6,303행·8.7MB) — 프로젝트 규칙 "hot path Seq Scan 없음" 위반, 현재 체감 0. 핀 사슬은 테스트가 잡지만 pre_push_smoke 서브셋 사각(CI 만). JS 50줄 초과 6/117, 리터럴 계약 7건. |

음성 대조군(축 판정용):
- G: 발동해야 할 표본이 발동 — `kind=daily&type=X` → 400 JSON(`OUT/w4_csv_check.json` `neg_bad_type`), 비로그인 export → 302 `/login`(파일 아님). 발동하면 안 될 표본이 미발동 — 정상 8종 CSV 전부 BOM `efbbbf`·LF 단독 0·금액 셀 콤마/괄호/통화 0(검사 14,000+셀)·날짜 불량 0.
- H: 인덱스가 있는 `ix_nsd_channel_expect` 를 타는 ① 30일 창은 `Index Scan using ix_nsd_channel_expect`(`OUT/w4_explain_q1_daily_expect_30d.txt`) — EXPLAIN 판독이 살아 있음을 증명. 같은 ①을 1년 창으로 주면 Seq Scan(218행 테이블에서 플래너 선택, 0.385ms) — 인덱스 부재가 아니라 비용 선택.

## 2. 발견 목록 (심각도 순)

### W4-G-01 (WARN · 표시/기간귀속) "정산 완료액" 타일 부제 "통장 입금 완료분 · 정산 완료일 기준"이 계산과 다르다
- 현상: 상단 축 문구는 "정산 예정일 기준"(`templates/cs/partials/settlement_channel_body.html:74`, 화면 `OUT/w4_kpi.png`)인데 타일 부제는 "정산 완료일 기준"(`static/js/settlement/channel.js:1201`). 커널은 **정산 예정일 창**(`OUT/w4_queries.sql` strip #1 `settle_expect_date >= … <=`)의 행 중 `settle_complete_date IS NOT NULL` 인 행의 `settle_amount` 를 더한다(`foms/services/settlement_channel.py:529~545` `_daily_totals`). 완료일이 창 밖이어도 예정일이 창 안이면 들어가고 그 반대는 빠진다. 또 완료분은 `settle_method_type` 을 보지 않아 `CHARGE_AMT`(충전금 상계, 통장에 안 찍힘)도 "통장 입금 완료분"에 들어간다(538~540 — 예정분만 계좌/충전금을 가른다 541~545).
- 실측(`OUT/w4_labels_db.json`): 스테이징 `naver_settle_daily` 218행 중 완료일≠예정일 0행·최대 지연 0일 → 기간귀속 실효 영향 **0원(실측)**. `CHARGE_AMT` 완료 행 1건 `-763원` 이 "통장 입금 완료분"에 포함(실측 **763원**).
- 전표: "정산 완료액" → (차) 보통예금 / (대) 네이버페이 미수금 — 단 CHARGE_AMT 행은 통장이 아니라 (차) 충전금(선급금) 이어야 하므로 한 줄로 못 쓴다.
- 권고: 부제를 계산 그대로 "정산 예정일 창 안 · 완료 처리된 행의 정산 금액(계좌+충전금)"으로 고치거나, `settled` 도 `expected` 처럼 계좌/충전금으로 갈라 부제에 싣는다(커널 `_daily_totals` 한 곳). 노력 S.

### W4-G-02 (WARN · 표시) "보류·한도" KPI 는 잔액도 발생액도 아닌 창 안 순증감이다
- 현상: 타일 값은 창 안 `pay_holdback_amount + settlement_limit_amount` 의 단순 합(`settlement_channel.py:551~596` `_build_holdback`·`_holdback_of`), 보류(음수)와 해제(양수)가 상계된 순액. 부제 "지급 보류 + 정산 한도 초과분"(`channel.js:1230`)은 순액인지 잔액인지 말하지 않는다.
- 실측(`OUT/w4_labels_db.json` `daily_holdback_sign_window`, 창 08-05~09-18): 보류 14행 **-119,379,098**, 해제 1행 **+2,410,000**, 화면 값 **-116,969,098**(`OUT/w4_kpi.png`·`w4_channel_text.txt:263`). 화면 숫자는 당기 보류 발생액(-119.4M)도, 보류 잔액(전기 누적 필요)도 아니다.
- 전표: 지급보류는 (차) 네이버페이 미수금-지급보류 / (대) 네이버페이 미수금 재분류이고 해제는 반대 분개 — 발생액·해제액이 따로 있어야 두 줄을 쓴다. 펼침 상세(15행, 부호 원본)로는 쓸 수 있으나 KPI 한 값으로는 못 쓴다.
- 권고: 타일 부제를 "창 안 순증감(보류 −119.4M · 해제 +2.4M)"처럼 발생·해제를 나눠 적고, `_build_holdback.total` 에 부호별 합을 추가한다(재계산 아님 — 부호별 합만). 노력 S.

### W4-G-03 (WARN · 표시) 같은 낱말 "정산 예정"이 두 필드, 같은 필드 `pay_settle_amount` 가 세 이름
- 현상 A: KPI "정산 예정액"(`channel.js:1204`) = 일별 `settle_amount` 중 미완료분(`_daily_totals` 541). 건별 CSV/원장/시트의 "정산 예정 금액"/"정산예정금액"(`settlement_channel_export.py:242·323`) = `settle_expect_amount`(건별 순정산액, 완료 여부 무관). 회계팀이 시트 "정산예정금액" 합을 KPI "정산 예정액"과 맞추면 반드시 어긋난다.
  - 실측(`OUT/w4_csv_sums.json`, 8월 창·정산 예정일 축): 시트 정산예정금액 합 **155,725,306** / 일별 CSV "정산 금액" 합 **34,013,589** / 09-04 화면 KPI "정산 예정액" **₩524,535**(`w4_channel_text.txt:263`). 정의가 다른 세 숫자다.
- 현상 B: `pay_settle_amount` 가 화면 "결제 정산"(`channel.js:118`), 일별·건별 CSV "결제 정산 금액"(export 195·235), 시트 "정산기준금액"(export 320). "정산 기준"은 CSV 다른 열에서 날짜(정산 기준일·정산 기준 시작일)에 쓰이는 낱말이라 시트만 보면 금액이 아니라 기준일 관련으로 읽힌다.
- 전표: "정산 예정 금액"(건별) → 매출채권 순액 보조부 / "정산 예정액"(KPI) → 미입금 잔액 — 이름이 같아 어느 쪽인지 정해야 전표가 선다.
- 권고: 시트 헤더는 사용자 확정(2026-09-03)이니 유지하고, **KPI 쪽**을 "미입금 정산액(일별 정산 금액 중 미완료분)"으로 바꾸고 부제에 "건별 '정산 예정 금액'과 다름"을 적는다. 노력 S.

### W4-G-04 (WARN · 표시) 대사 배너 "일별 합계 vs 건별 합계 → 대사 일치"가 어떤 금액을 대사했는지 말하지 않는다
- 현상: `_build_reconcile`(`settlement_channel.py:734~745`)은 `pay_settle_amount`(결제 정산 금액)만 비교한다. 배너 문구(`channel.js:1509~1520`)는 "일별 합계 / 건별 합계 / 같은 기간을 일별 API 와 건별 API 로 각각 합산한 값" — 필드 이름이 없다. 화면(`OUT/w4_exceptions_header.png`): "일별 합계 ₩1,576,637,530 vs 건별 합계 ₩1,576,637,530 → 차이 ₩0 대사 일치". 정산 금액(일별 `settle_amount`)과 건별 `settle_expect_amount` 는 대사하지 않는다(보류가 일별에만 있어 원래 다름).
- 전표 관점: 회계팀은 "대사 일치"를 정산금액(입금액) 대사로 읽기 쉽다. 허용 오차 0 은 확인(745행 `daily_total - case_total`, 반올림 없음).
- 권고: 배너에 "결제 정산 금액(paySettleAmount) 기준" 한 마디를 넣는다(`channel.js:1509` 문자열). 노력 S.

### W4-G-05 (WARN · 표시/완전성) 예외 배지 "예외 125"·요약 스트립 "예외 65건"은 모집단이 아니라 상한 뒤 표시 건수
- 현상: 배지 = `(data.exceptions || []).length`(`channel.js:1541`), 스트립 `exception_count = len(exceptions)`(`settlement_channel.py:1316`). `exceptions` 는 갈래별 `_EXCEPTION_CAP = 50`(112행, `_unmatched_rows … .limit(_EXCEPTION_CAP)` 911행)으로 잘린 목록. 화면(`OUT/w4_exceptions_header.png`, 창 2026-01-01~09-18): 배지 "예외 125"·표 125행, 같은 화면 문구 "FOMS 미연결 4,265건 = 워크벤치 대기 1,386건 + 수집 전 주문 2,879건 … 표에는 갈래마다 최근 것부터 상한까지만 실립니다"(`OUT/w4_exceptions_text.txt:277`). 요약 탭 스트립도 "예외 64건/65건"(`w4_channel_text.txt:124`, `w4_exceptions_text.txt:124`).
- 영향: 회계팀이 "예외 125건"을 마감 전 정리 대상 전량으로 읽으면 4,140건이 시야에서 사라진다(금액은 W3 D-1·D-2 축).
- 권고: 배지·스트립은 모집단 수(`unmatched_count` + 일별·run 예외 수)를 쓰고, 표 머리에 "N건 중 M건 표시"를 낸다. W3 D-2 와 같은 근원 — 심각도 최종 판정은 CEO. 노력 S.

### W4-G-06 (WARN · 표시/완전성) 조건을 건 CSV 가 조건 없는 CSV 와 같은 파일명으로 내려오고, 허용 집합 밖 type 은 빈 파일(200)이 된다
- 실측(`OUT/w4_csv_type_neg.json`, 8월 창): `kind=case&type=X` → 200 CSV **0행**, `type=PROD_ORDER` → 457행, `q=zzzz-no-such` → 0행, `kind=sheet&type=X` → 0행, `kind=commission&type=X` → 0행. 다섯 응답의 `Content-Disposition` 이 조건 없는 파일과 **동일**(`naver_settle_case_20260801_20260831.csv` 등). 파일명 슬러그는 축(basis)만 싣는다(C3 수정 범위).
- 근거: `settlement_channel_export.py:539~569` `_filter_clauses` 는 `type` 값을 enum 카탈로그(`_ENUM_MAPS`)와 대조하지 않고 그대로 `==` 술어에 넣는다. 라우트 docstring(`foms/api/cs/settlement_channel.py:400·405`)이 약속한 400 은 "조건을 받지 않는 종류"에만 해당(정상 동작, `neg_bad_type` 400 확인).
- 영향: 회계팀이 유형 필터를 건 채 내려받은 부분 원장이 전체 원장과 같은 이름으로 폴더에 남는다. 오타 type 은 "이 달 정산 없음"처럼 보이는 헤더만 있는 파일이 된다.
- 권고: 파일명에 `_type-<코드>`·`_q` 슬러그를 붙이고(축 슬러그와 같은 자리), `type` 값을 `_ENUM_MAPS[field]` 로 검증해 400. 노력 S.

### W4-G-07 (WARN · 표시) 100% 에서도 워터폴 X축 라벨 "지급 보류·한도"가 "지급보류·한"으로 잘려 이웃과 겹친다
- 실측: `OUT/w4_100_overlap.json` — 100%(1440×900)에서 워터폴 svg 텍스트 19개 중 교차 쌍 1(`["지급보류·한","충전금상계"]`), 일별 차트 0. 화면 `OUT/w4_kpi.png`·`OUT/w4_100_waterfall.png`(X축 "…공제환급 지급보류·한충전금상계 정산금액").
- 근거: `channel.js:1416~1419` `shortStepLabel` — 공백 제거 뒤 6자 초과면 `slice(0, 6)`. "지급보류·한도"(7자) → "지급보류·한". 절단 결과가 낱말이 아니라 툴팁 없이는 뜻을 못 읽는다(툴팁은 원 라벨, 669·66행).
- 권고: 축 라벨을 2줄(`<tspan>`)로 내리거나 약어 표(`short`)를 커널 `_WATERFALL_STEPS` 에 두고 6자 절단을 없앤다. 노력 S.

### W4-G-08 (WARN · 표시 — 원장 F6 후속, 격상 아님) 150% 글자 크기에서 워터폴 라벨 판독 불가 + 축 라벨 클립 + 페이지 가로 스크롤 + KPI 값 넘침
- 실측(1440×900, 조절기 `+` 3회 → `--s-fs: 1.5`):
  - 워터폴 X축 교차 쌍 **6**(`OUT/w4_150_overlap.json`: 결제정산액↔수수료↔혜택정산↔공제환급↔지급보류·한↔충전금상계↔정산금액 전부), 화면 `OUT/w4_150_waterfall.png` — 글자가 한 줄로 붙어 읽을 수 없다. 일별 차트 X축은 0.
  - Y축 라벨 클립(`OUT/w4_150_overflow.json` `svgs`): 일별 차트 "1,000만·2,000만·3,000만" 3개, 워터폴 "5,000만" 1개가 svg 왼쪽 밖(화면 `OUT/w4_150_full.png` 왼쪽 ",000만").
  - 가로 스크롤: `documentElement.scrollWidth` **1666** > clientWidth 1440(09-05, 09-04 는 1574). 원인 요소 `.s-ch-table`(건별 정산 원장 표) 폭 1848px·오른쪽 끝 1874 — 표가 `overflow-x: auto` 컨테이너 안에 있지 않아 본문이 옆으로 밀린다(`OUT/w4_150_overflow.json` `overflowTop`).
  - KPI 값 넘침(`OUT/w4_150_kpi_overflow.json`): "-₩116,969,098" 타일 값 오른쪽 끝이 타일 경계보다 **+13px** 밖(타일 scrollWidth 340 > clientWidth 226, overflow visible). 다른 5타일은 안쪽.
  - 100% 복귀 후 `--s-fs: 1`, localStorage `foms.settlement.fontScale = "1"`, scrollWidth 1440(음성 대조군, `w4_100_overlap.json`).
- 판정: 수용 리스크(F6) 재확인 결과 워터폴은 "읽을 수 없는 수준" → WARN. 가로 스크롤은 CLAUDE.md 프론트 규칙("본문 가로 스크롤 금지")에도 걸린다.
- 권고: `.s-ch-ledger` 표를 `overflow-x:auto` 래퍼로 감싸고, 워터폴 축 라벨은 2줄/회전/약어, Y축 여백을 `--s-fs` 에 비례. 노력 S~M.

### W4-H-01 (WARN · 유지보수) `naver_settle_case`·`naver_settle_commission` 창 술어 COALESCE 가 인덱스를 못 타 Seq Scan
- 실측(`OUT/w4_explain_*.txt` 10개, `OUT/w4_explain_summary.json`, PG 17.11, 스테이징):

| 질의 | 30일 창 | 1년 창 |
|---|---|---|
| ① daily expect | Index Scan `ix_nsd_channel_expect` 0.133ms 22행 | Seq Scan 0.385ms 218행 |
| ② case 매칭 통계 | **Seq Scan** 2.498ms | **Seq Scan** 5.937ms (buffers 1058) |
| ③ case UNMATCHED+link LIMIT 50 | **Seq Scan** 2.601ms | **Seq Scan** 2.886ms |
| ④ case pay_date 축 갭 | **Seq Scan** 1.845ms | **Seq Scan** 3.383ms |
| ⑤ case 완료일별 | **Seq Scan** 2.286ms | **Seq Scan** 4.986ms |

  테이블: `naver_settle_case` 6,303행 8.67MB(총 9.7MB), `naver_settle_commission` 13,984행 18.2MB, `naver_settle_daily` 218행 385KB. 인덱스 17개 중 case 는 `(channel, search_date)`·`(channel, foms_order_id) partial`·`(product_order_id)`·`(channel, search_date) WHERE UNMATCHED` 뿐 — `settle_expect_date`·`settle_complete_date`·`pay_date`·`settle_basis_date` 인덱스 0(기록과 일치).
- 질의 수(`OUT/w4_query_count.json`, `OUT/w4_queries.sql`): 스트립 **6** = 예산 6(docstring 1271) PASS; 대시보드 case/expect 14, case/pay 15(축 갭 카운트 +1), commission 14, vat_case 14, 1년 창 14. daily·case 통계 질의가 현재/전기 2회씩 — 의도된 전기 비교.
- TTFB(`OUT/w4_ttfb.json`, 3회 중앙값): API 30일 **203ms**(151.7KB), 1년 **217ms**(293.8KB), strip **135ms**, 프래그먼트(`X-FOMS-ERP-SHELL` 활성값 + `?view=fragment`) **125ms** 26.9KB `X-FOMS-ERP-FRAGMENT: 1`, 전체 페이지 123~146ms 177.9KB. 헤더만 있고 `view` 없으면 전체 페이지가 온다(`foms/services/common/erp_shell_http.py:10~27` — 브리프 함정 문구 보강). 판정선 30일 <1s·1년 <3s 모두 PASS.
- 판정: 체감 0(ms 단위)이지만 프로젝트 규칙(CLAUDE.md "hot path Seq Scan 없음")에 어긋나고 행 수에 선형이다. 6개월 뒤 운영이 10배여도 수십 ms — FAIL 아님.
- 권고: `(channel, COALESCE(settle_expect_date, search_date))` 식 인덱스 1개(case·commission 각 1)로 술어 그대로 인덱스를 태운다. 노력 S(마이그레이션 1개).

### W4-H-02 (WARN · 유지보수) 핀 사슬은 테스트가 잡지만 로컬 게이트(pre_push_smoke 서브셋)에 없다
- 값 표(`templates/cs/partials/settlement_dashboard_body.html`): 셸 4줄 20·21·423·424 = `20260903d`, 채널 2줄 22·425 = `20260903i`, `tests/domains/test_settlement_channel_render.py:72` `_CHANNEL_PIN = "20260903i"`.
- 잡는 테스트: 채널 render 467~476 `assert pins == {_CHANNEL_PIN}`(저장소 전역 핀 정확히 1개 + 리터럴 일치); 실무 render `test_settlement_operations_render.py:967~987` `len(pins) <= 1` + `pins == {common}`(요약 탭 CSS 핀을 읽어 셸 4줄 동일값 강제); 요약 render 계약 1(`test_settlement_dashboard_render.py:421~425`) 핀 존재.
- 사각: `scripts/ops/pre_push_smoke.ps1:214~241` 서브셋에 `test_settlement_*` 없음, `-Full`(209~212)만 전체. CI `.github/workflows/ci.yml:109` 전체 스위트 → CI 가 잡는다.
- 음성 대조군(실행 안 함 — 편집 금지): 채널 CSS 핀만 `20260903j` 로 올리면 476행 단정이 `{'20260903j'} != {'20260903i'}` 로 red 가 되는 구조.
- 권고: 서브셋에 `tests/domains/test_settlement_channel_render.py::test_channel_asset_pins_are_single_repo_wide` 와 실무 render 핀 테스트를 추가(초 단위). 노력 S.

### W4-H-03 (INFO · 유지보수) channel.js 50줄 초과 함수 6/117, 커널 0/47
- `OUT/w4_fn_len.json`: `foms/services/settlement_channel.py` 47함수 초과 0(docstring 포함 시 2, 최대 35줄), `settlement_channel_export.py` 18/0, `settle_sync.py` 33/0, `foms/api/cs/settlement_channel.py` 14/0. `channel.js` 117함수 중 초과 6 — `waterfallChart` 77(613~689)·`stackColumnChart` 76(476~551)·`renderKpis` 72(1182~1253)·`bindControls` 71(2220~2290)·`mount` 54·`renderDaily` 53. 파일 2,558줄.
- 리터럴 단정 계약: `grep -n "_CHANNEL_PIN\|20260903\|function applyFontScale(\|FONT_KEY" tests/domains/test_settlement_{channel_render,font_scale,dashboard_render}.py | wc -l` = **7**. 대표: `test_settlement_channel_render.py:72 _CHANNEL_PIN = "20260903i"`, `:476 assert pins == {_CHANNEL_PIN}`, `test_settlement_font_scale.py:85 FONT_KEY_LITERAL = "var FONT_KEY = 'foms.settlement.fontScale'"`, `:324 "function applyFontScale("`, `:330 assert js.count("FONT_KEY") >= 3`. 정성 판정: 핀 리터럴은 배포마다 테스트를 같이 고쳐야 하는 의도된 마찰(실무 render 는 동적 비교로 회피), 함수 시그니처·변수 선언문 리터럴 2건은 이름 바꾸기 리팩터를 막는다 — 낮음.

### W4-H-04 (INFO · 부채 지표) 채널 CSS 하드코딩 색
- `static/css/settlement/settlement-channel.css` 662줄: hex 27개·rgba 2개, `var(--s-…)` 소비 182곳. hex 중 18개는 토큰 블록(37~55)·3개는 변형 토큰 선언(520·533·537), 규칙 안 직접 리터럴은 101(`#1f63b8` hover)·420(`#d9a44a`)·573(`#e3d5ac`)·265(`var()` 폴백 2개)·436/625(그림자 rgba). 헤더 주석(20행)의 "색은 토큰 블록 한 곳"과 5곳이 어긋나지만 다크가 셸 차원에서 막혀 있어 실효 0.

## 3. G-1 라벨 전수 → 전표 매핑

| 표면 | 라벨 | 원천 | 회계팀이 옮길 전표 한 줄 | 막힘 |
|---|---|---|---|---|
| KPI | 정산 완료액 | daily `settle_amount`(완료 플래그, 예정일 창) | (차) 보통예금 / (대) 네이버페이 미수금 | **막힘**(CHARGE_AMT 혼입·부제 축 불일치) → G-01 |
| KPI | 정산 예정액 | daily `settle_amount` 미완료분 | 전표 없음 — 미수금 잔액 보조부 | 이름 충돌 → G-03 |
| KPI | 수수료 합계 | daily `commission_settle_amount` | (차) 지급수수료 / (대) 네이버페이 미수금 | 없음(부제 "네이버가 차감한 금액" 명확). 수수료 원장 합과 원천이 다름은 커널 주석(762~765)이 말함 |
| KPI | 실효 수수료율 | 비율 | 전표 없음 | 없음 |
| KPI | 보류·한도 | daily 보류+한도 합(순액) | (차) 미수금-지급보류 / (대) 미수금 [발생], 반대 [해제] | **막힘**(순액) → G-02 |
| KPI | 주문 매칭률 | case 매칭 통계 | 전표 없음(관리 지표) | 없음 |
| 워터폴 | 결제 정산액·수수료·혜택 정산·공제 환급·지급 보류·한도·충전금 상계·정산 금액 | `_WATERFALL_STEPS`(167~175) | 결제 정산액=(차) 미수금 총액 인식 기준, 정산 금액=순입금 예정 | 라벨 절단 → G-07; 혜택·공제 0 이라 "0" 표기 OK |
| 대사 | 일별 합계·건별 합계·대사 일치 | `pay_settle_amount` 만 | 전표 없음(적재 검증) | 대상 금액 미표기 → G-04 |
| 보류 상세 | 정산 예정일·입금 방식·지급 보류·정산 한도·합계·정산 완료 | daily 행 | 행 단위로 위 보류 전표 가능 | 없음(부호 안내 문구 있음, 1267행) |
| 입금 채널 | 계좌 이체(통장 입금)·미정(정산 예정)·충전금 상계 | daily 방식별 | 계좌 이체=보통예금, 충전금=선급금 | 없음("자동 대사되지 않습니다" 문구 있음) |
| CSV daily | 정산 금액 / 결제 정산 금액 / 수수료 정산 합계 / 지급 보류 금액 / 한도 보류 금액 … | 모델 컬럼 소진 | 위와 동일 | 없음 |
| CSV case | 결제 정산 금액 / 네이버페이 수수료 합계 / 무이자 할부 수수료 / 매출 연동 수수료 / 혜택 정산 금액 / 정산 예정 금액 | 모델 컬럼 | 건별 미수금·수수료 보조부 | "정산 예정 금액" 동명이의 → G-03 |
| 시트 7열 | 구매자명·결제일·정산완료일·정산기준금액·Npay 수수료·매출 연동 수수료 합계·정산예정금액 | `pay_settle`·`total_pay_commission`·`selling_interlock`·`settle_expect` | 정산기준금액+Npay 수수료+매출연동수수료 = 정산예정금액 (행 항등식 **457/457 성립**, 전기간 6,303/6,303 성립 — `w4_csv_sums.json`·`w4_labels_db.json`) | "정산기준금액" 낱말 → G-03; 취소 행 사유 열 없음 → 결정 재고 |
| 부가세 | 총매출·과세매출·면세매출·신용카드·현금(소득공제/지출증빙/발급제외)·기타·확정 | vat_daily/case | 각주가 "과세표준은 결제금액 총액, 수수료는 매입세금계산서로 공제"라고 말함(`OUT/w4_vat.png`) | 없음 |

## 4. G-2 CSV 형식 (8월 창 2026-08-01~08-31, `OUT/w4_csv_check.json`, 바이트 `OUT/w4_csv_*.csv`)

| kind | 상태 | BOM | CRLF/LF단독 | 헤더=레지스트리 순서 | 행 | 금액 셀 불량/검사 | 날짜 불량/검사 | 파일명 |
|---|---|---|---|---|---|---|---|---|
| daily | 200 | efbbbf | 20/0 | 예 | 19 | 0/247 | 0/76 | `naver_settle_daily_20260801_20260831.csv`(무슬러그) |
| case(기본) | 200 | efbbbf | 458/0 | 예 | 457 | 0/2742 | 0/2285 | `naver_settle_case_…`(무슬러그) |
| case&basis=complete | 200 | efbbbf | 458/0 | 예 | 457 | 0/2742 | 0/2285 | `naver_settle_case_complete_…` |
| sheet(기본) | 200 | efbbbf | 458/0 | 예 | 457 | 0/1828 | 0/914 | `naver_settle_sheet_…` |
| sheet&basis=pay | 200 | efbbbf | 231/0 | 예 | 230 | 0/920 | 0/460 | `naver_settle_sheet_pay_…` |
| vat_daily | 200 | efbbbf | 29/0 | 예 | 28 | 0/224 | 0/28 | `naver_settle_vat_daily_…`(무슬러그) |
| vat_case | 200 | efbbbf | 370/0 | 예 | 369 | 0/2952 | 0/369 | `naver_settle_vat_case_…` |
| commission | 200 | efbbbf | 1020/0 | 예 | 1019 | 0/3057 | 0/5095 | `naver_settle_commission_…` |

- 음수 표기 `-213878` 형식(콤마·괄호·통화 0) — `_fmt_money`(`settlement_channel_export.py:359~372` docstring: 더존·이카운트 파서). `Cache-Control: no-store`.
- 회계 업로드 최소 열 vs 시트 7열: 거래일=결제일/정산완료일 **있음**, 거래처 **없음**(네이버 상수), 공급가 **없음**, 세액 **없음**(네이버 정산 API 미제공 — vat_case 도 과세매출 총액만), 합계=정산예정금액 **있음**, 계정 **없음**. 부재 열은 결함이 아니라 §8 결정 재고.

## 5. G-3 · G-4 요약

- G-3: §2 W4-G-07(100%)·W4-G-08(150%). 스크린샷 `OUT/w4_kpi.png`(100% 전체), `OUT/w4_100_waterfall.png`, `OUT/w4_150_chart.png`, `OUT/w4_150_waterfall.png`, `OUT/w4_150_full.png`(가운데 상단 메뉴가 한 번 더 보이는 것은 sticky 헤더가 전체 페이지 캡처에 두 번 찍힌 캡처 아티팩트).
- G-4 다크: `static/js/foms/theme.js:43~48` `resolveAppliedTheme` 는 모바일 뷰포트가 아니면 **항상 'light'** 를 돌려준다. 토글은 모바일 메뉴 서랍에만 있다(`templates/partials/shared/erp_mobile_menu_drawer.html:68`, 데스크톱 화면에서 `[data-foms-theme-option]` 0개 — `w4_dark.png` 캡처 시 "no toggle button"). `data-theme="dark"` 를 손으로 박아도 즉시 light 로 되돌아간다(캡처 로그: theme "light", pref "system"). `[data-theme='dark']` 블록(`foms-tokens.css:173`)은 `--foms-*` 만 재선언하고 `.foms-settle` 의 `--s-*`(`settlement-dashboard.css:35~64`, `color-scheme: light`)에는 다크 블록이 0 → 채널 탭은 "요약 대시보드 v1 미결과 동일 범위(셸 미대응)". `settlement-channel.css:17~21` 헤더 주석대로 이 파일은 토큰만 소비. `OUT/w4_dark.png` 는 그래서 라이트 화면이다(computed: settle bg `rgb(238,242,247)`, color-scheme light).

## 6. NOT-A-DEFECT (조사했지만 결함 아님)

| 항목 | 이유 |
|---|---|
| 다크 테마 미대응 | 셸(`theme.js`)이 데스크톱을 light 로 고정 — 채널 탭 고유 결함 아님(§5) |
| ① 1년 창 Seq Scan(`naver_settle_daily`) | 218행 385KB 에서 플래너 비용 선택, 0.385ms; 30일 창은 같은 인덱스를 탄다 |
| 비로그인 export 302 → `/login` | CEO 기대는 JSON 401/403 이었으나 실제는 302 HTML 리다이렉트(파일 아님, 앱 전역 관례) — 자료 유출 없음 |
| `kind=daily&type=X` 400 JSON | 설계대로(`FILTER_FIELDS` 빈 튜플 → ValueError → 400) |
| CSV BOM·CRLF·금액·날짜·헤더 순서·축 슬러그 | 8종 전부 PASS(§4) |
| 시트 7열 항등식 | 정산기준금액+Npay 수수료+매출연동수수료 = 정산예정금액 이 8월 457/457·전기간 6,303/6,303 성립; 혜택·무이자 열이 없어도 값이 전부 0 이라 현재 누락 0원 |
| 100% 일별 차트 | 라벨 교차 0·클립 0·가로 스크롤 0 |
| 부가세 "합계 (227일) · 확정" | `vat.final` = 창 안 모든 행 `is_final`(커널 844~860); 스테이징 315행 전부 final, 배너 "2026-08-31까지 제공 · 당월분은 익월 마감 후"가 창 09-18 과의 차이를 설명 |
| 동기화 상태 줄·부가세 각주 | 최종 동기화 시각·상태·적재/확정 구간·부가세 제공 한계·과세표준 안내 모두 화면에 있음 |
| 대시보드 14~15 문장 | 문서화된 예산은 스트립 6 뿐; 현재/전기 2회 조회는 의도된 비교 |
| `w4_150_full.png` 가운데 메뉴 중복 | 전체 페이지 캡처 아티팩트 |
| 콘솔·네트워크 | KPI 로드(`OUT/w4_console_kpi.txt`)·예외/부가세/150% 조작(`OUT/w4_console_views.txt`) 모두 콘솔 메시지 0, 4xx/5xx 0(302 로그인·304 프리페치뿐) |

## 7. 확인 못 한 항목

| 항목 | 이유 |
|---|---|
| `vat.final=false` 표시 문구 실화면 | 스테이징 `naver_vat_daily` 315행 전부 `is_final=true`(2025-10-01~2026-08-31) — 미확정 표본이 없어 화면에 낼 수 없음. 코드상 문구는 합계 행 접미 " · 확정" 생략뿐(`channel.js:1943`) — "잠정" 표시는 없다 |
| 다크 실화면 | 데스크톱에서 다크가 설계상 불가(§5). 모바일 뷰포트 에뮬레이션은 W4 범위 밖(모바일 셸은 다른 화면) |
| 운영 DB EXPLAIN·행 수 | W4 에게 운영 DB 미허용 — 스테이징 수치(6,303행)만. 운영 규모는 W2·W3 배치 결과 참조 |
| 핀 사슬 음성 대조군 실행 | 워크트리 편집 금지라 단정식 인용만(§2 H-02) |
| 시트 "취소 행 사유 없음"의 회계 처리 | 45행 -19,122,130(전기간)·8월 시트 2행 -101,000 이 부호만으로 구분되는데, 회계팀이 실제로 어떻게 처리하는지는 사용자 확인 필요(§8) |

## 8. 결정 재고 (기존 결정을 뒤집자는 것이 아니라 근거 제시)

1. **시트 7열(2026-09-03 사용자 확정)에 열 3개 추가 검토**: (a) `정산 구분`(settle_type) — 취소 정산 행 45건 -19,122,130원(전기간, `w4_labels_db.json` `case_settle_type_dist`)이 시트에서는 음수 금액으로만 보인다(8월 2행 -101,000, `w4_csv_sums.json`). (b) `거래처` 상수 열("네이버페이") (c) `계정` 열. 세액은 네이버가 주지 않아 추가 불가(재계산 금지 D-4 와도 충돌) — 부가세 탭 각주가 대신 안내.
2. **F6 150% 수용 리스크**: 워터폴 라벨은 판독 불가 수준이고 표가 본문 가로 스크롤을 만든다(§2 G-08). 표 래퍼 `overflow-x:auto` 한 줄은 리스크 수용 없이 닫을 수 있다.

## 9. 산출물 경로 (전부 `OUT/`)

- 원장: `findings_w4.md`
- pytest: `w4_pytest.txt`
- 화면: `w4_kpi.png`, `w4_100_waterfall.png`, `w4_150_chart.png`, `w4_150_waterfall.png`, `w4_150_full.png`, `w4_exceptions_header.png`, `w4_vat.png`, `w4_dark.png`; 텍스트 `w4_channel_text.txt`, `w4_channel_text_immediate.txt`, `w4_exceptions_text.txt`; 콘솔 `w4_console_kpi.txt`, `w4_console_views.txt`
- 겹침·넘침: `w4_overlap.js`, `w4_100_overlap.json`, `w4_150_overlap.json`, `w4_150_overflow.json`, `w4_150_kpi_overflow.json`
- CSV: `w4_csv_check.py`, `w4_csv_check.json`, `w4_csv_{daily,case,case_complete,sheet,sheet_pay,vat_daily,vat_case,commission}.csv`, `w4_csv_type_neg.py`, `w4_csv_type_neg.json`, `w4_csv_sums.json`
- 성능: `w4_query_count.py`, `w4_query_count.json`, `w4_queries.sql`, `w4_explain.py`, `w4_explain_summary.json`, `w4_explain_q{1..5}_*_{30d,1y}.txt`(10개), `w4_ttfb.py`, `w4_ttfb_fragment.py`, `w4_ttfb.json`
- 부채: `w4_fn_len.py`, `w4_fn_len.json`
- 라벨 검증 SQL: `w4_labels_db.py`, `w4_labels_db2.py`, `w4_labels_db.json`
