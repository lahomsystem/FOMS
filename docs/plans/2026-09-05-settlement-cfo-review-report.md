# 네이버 정산 탭 CFO 감사 — 최종 판정 보고서 (2026-09-05)

- 대상: FOMS `/erp/settlement` 4번째 탭 "네이버 정산" (코드 기준 워크트리 `C:/tmp/foms-s-settle-cfo`, HEAD `7100e2aa1`)
- 방법: 워커 4명(축 A~H) → 검증자 4명(전건 반박 시도) → 비평자 1명(누락 검사) → CEO 최종 판정. 읽기 전용 감사(코드 편집·운영 쓰기·동기화 버튼 0회).
- 데이터: 스테이징 API·DB·실화면(gstack browse), 운영 DB 읽기 전용 배치 4회(W2·W3·검증자 W2·W3 각 1회, 숫자만 기록). pytest `tests/domains -k settlement` **922 passed**(기준선 동일, `w4_pytest.txt`·`vw4_pytest.txt`), 접근·스트립·API·export 계약 148 passed(`verify_w3.md`), 재현 테스트 7 passed(`vw2_repro_pytest.txt`).
- 스냅샷 주의: 감사 중 날짜가 09-04 → 09-05 로 넘어가 두 스냅샷이 섞여 있다. **rev14**(09-04, 기본 창 08-05~09-18, 예정액 524,535)·**rev19**(09-05, 기본 창 08-06~09-19, 예정액 10,211,240). 층 간 대사는 같은 스냅샷 안에서만 견줬고, 아래 숫자에는 스냅샷을 병기한다. "미매칭 482/511/418건"·"예외 64/65/125건"처럼 같은 항목의 수가 다른 것은 창·시각 차이이지 불일치가 아니다.
- 근거 파일은 전부 `OUT = C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo` 아래(아래는 파일명만 적는다). 비밀번호·토큰·DB 주소·계좌 원문은 어디에도 없다.

---

## 1. 한 줄 결론

**회계팀이 이 화면으로 9월 마감을 할 수 있는가 — 조건부 예.** 채널 합계 단위(네이버 정산 원장 = DB = 화면 KPI = CSV, 원 단위 일치 실증)로는 장부에 올릴 수 있다. 단 아래 5가지 조건을 지켜야 한다.

| # | 조건 | 왜 |
|---|---|---|
| 1 | **주문 단위 매출↔정산 대사는 9월 마감에서 제외**하고 채널 합계로 계상한다. | 운영 미매칭 정산액 1,480,447,006원(4,227건, 네이버 지급 완료분 1,471,504,974원)이 FOMS 주문과 안 붙어 있다. 매칭된 주문은 운영 3건뿐. 원인은 워크벤치 적체(결정 사항)라 화면이 고칠 수 없다. |
| 2 | **마감 직전 [이 구간 받아오기]를 전월 1일부터 1회 실행하고, 그 직후(다음 05:30 전에) 예외 큐의 RETRO·대사 배너를 확인**한다. 실행은 운영자가 한다(이 감사는 버튼을 누르지 않았다). | 예정일+30일이 지난 날짜는 일반 동기화가 다시 읽지 않고(§3 B-01), 새벽 05:30 창 안 5회 연속 실행이 소급 변경(RETRO) 신호를 화면에서 지운다(§3 F-07). |
| 3 | **화면 숫자를 옮길 때 §8 라벨 해석표를 쓴다.** 특히 "정산 완료액"(예정일 창 안 완료분, 충전금 상계 포함), "보류·한도"(창 안 순증감), 원장 합(정산 예정 금액=수수료 차감 후·보류 전), 전기 대비 %(달력 전월 아님) 4개. | 같은 "8월"에 34,013,589 / 155,725,306 / 165,992,120 / 168,134,680 네 숫자가 나란히 나올 수 있고 화면이 개념 차이를 말하지 않는다(§3 C-02). |
| 4 | **지급 보류 잔액은 화면 밖에서 따로 관리**한다. 현재 미해제 보류 18행 −129,757,200원(07-30~08-26, 스테이징=운영 동일). | 화면은 조회 창 안 보류·해제의 순합만 보여 누적 잔액이 없다(§3 B-02). 일별 CSV의 "지급 보류 금액" 열 부호별 합으로 산출 가능. |
| 5 | **운영 화면에서 마감 직전 1회 자체 대조**: 일별 CSV "정산 금액" 완료분 합 = KPI "정산 완료액". | 정확성 3중 대사는 규율상 스테이징에서만 했다. 코드·데이터 원천(같은 네이버 계정)은 같지만 운영 숫자 자체는 이번에 대조하지 않았다(§7-1). |

FAIL 0 · WARN 25 · INFO 7 · REFUTED 0 · 확인 못 함 17. 틀린 숫자는 하나도 못 찾았다. 결함은 전부 "필요한 숫자가 없다", "라벨이 다른 뜻으로 읽힌다", "통제 사각" 세 부류다.

---

## 2. 축별 판정 표

| 축 | 판정 | 근거 한 줄 | 근거 위치 |
|---|---|---|---|
| A 정확성 | **WARN** | rev14 4층(API kpi·DB 일별·DB 건별·CSV daily/case/sheet) 원 단위 전부 일치 — 완료 49,129,495 · 예정 524,535 · 수수료 −10,889,232 · 보류 −116,969,098 · 대사 177,512,360 · Σ원장 166,623,128 · 485건. rev19 도 API=DB. 양끝 포함(to=09-06/from=08-06 하루치만큼만 변동)·취소 부호 3층 동일·NEGATIVE 양성(2025-10-14 −763)/음성 대조군 통과. WARN 은 숫자가 아니라 숫자를 잇는 문구 3곳(워터폴 마지막 단·예정액 세부·대사 배너 대상). | `w1_a1_result.json` `w1_api2_result.json` `w1_fresh_db_result.json` `vw1_probes_result.json` `vw1_a01_a03_result.json` |
| B 완전성 | **WARN** | 날짜 구멍 88/247일 = 주말 70+공휴일 9+영업일 9(적재 실패 근거 0, 두 엔드포인트 독립 일치)·28일 창 분할 42/42·coverage 안 빈 달 0(스테이징 12개월·운영 9개월) 은 정상. 결함: 미해제 보류 18행 −129,757,200 잔액 미표시, 확정 구간(예정일+30일) 밖 정정 미공시, 05:30 5회 실행이 RETRO 를 지움(스테이징 run16 retro 3건 → API RETRO 0 실측). | `w2_staging.json` `w2_production.json` `vw2_sql.py` `vw2_staging_retro.json` `vw2_api_exceptions.json` `w2_windows.json` |
| C 기간 귀속 | **WARN** | 월 경계는 KST 달력 날짜: 원문↔컬럼 불일치 일별 0/218·건별 0/6,303, 원문에 시각 0건, 날짜 컬럼 8개 전부 `date`, 08-31/09-01·06-30/07-01 버킷 = DB 하루 합 정확. 결함: 전기 = 달력 전월이 아니라 같은 일수 직전 구간(2월 −5,418,060 · 3월 +29,362,179 · 5월 +9,334,671), "8월 정산액" 3축 한 화면 불가·원장 합계 줄 없음. | `w1_c2_result.json` `w1_c1_result.json` `vw1_a02_result.json` `vw1_c01_result.json` `vw1_mar_month_tip.png` |
| D 존재·권리 | **WARN** | 운영 미매칭 1,480,447,006원(취소 32행 −14,497,253 상계 포함 원값 부호합)·90일+ 981,133,199원이 화면에 금액으로 없다(건수만). 예외 머리 숫자가 상한 뒤 길이(스트립 65 vs 모집단 526, 배지 125 vs 4,290). 매칭 건 정산액≠출고가 대조 없음(스테이징 #4242 출고가 0 vs 2,830,000). 음성 대조군: 링크에 주문이 붙었는데 UNMATCHED 인 행 0(운영·스테이징) — 매칭 갱신 누락 아님. | `w3_production.json` `vw3_production.json` `vw3_api_probe.json` `w4_exceptions_text.txt:124·277` `vw3_match_diff_staging.json` |
| E 통제·감사 | **WARN** | 권한(정산 표면 라우트 6곳 전부 `is_accounting_or_admin`, 엔진 gate 가 ADMIN/MANAGER override 보다 먼저, 직접 `== 'ACCOUNTING'` 비교 0건, 비로그인 302, 계약 148 passed)·계좌 마스킹(API·CSV·화면 텍스트 3벌·감사 로그·raw 스캔 0, 양성 대조군 daily raw 200행)·쓰기 경로(웹에서 `replace_partition` 호출 0, POST /sync 는 enqueue+감사 1행) PASS. 결함: 운영 측정 계정 비밀번호가 09-02 노출본과 해시 일치(잠금 상태가 완화), 동기화·내보내기 감사 detail 에 실효 창·run 키·type/q 없음. | `w3_api_log.json` `w3_staging_batch.json` `vw3_staging_probe.json` `vw3_production.json` `critic.md §3-4` |
| F 운영 신뢰성 | **WARN** | 캐시 경로 0(API 헤더 Cache-Control/ETag 없음, SW 가 `/api/settlement` 미가로챔, 버전 카운터 미참조, rev 14→19 전진 확인) PASS. 결함: stale 36h 라 누락 다음 날 근무시간 내내 "상태 OK", 큐 부재·enqueue 실패가 "이미 대기 중"(200), FAILED 실행이 반쯤 교체된 창을 커밋(재현 테스트), 05:30 창 5회 실행(465호출/일). | `w2_strip.json` `vw2_repro_test.py` `vw2_repro_pytest.txt` `vw2_production.json runs` |
| G 표시·내보내기 | **WARN** | CSV 8종 형식(BOM efbbbf·CRLF·금액 평문·ISO 날짜·헤더 순서·축 슬러그) 전부 PASS, 시트 7열 항등식 6,303/6,303. 결함: 전표 한 줄을 못 쓰는 라벨 4개, 예외 배지=잘린 길이, 조건 CSV 동일 파일명·오타 type 빈 파일 200, 100% 워터폴 라벨 절단 겹침, 150% 판독 불가·본문 가로 스크롤. 다크 미대응은 셸 차원(결함 아님). | `w4_csv_check.json` `w4_csv_sums.json` `w4_kpi.png` `vw4_100_waterfall.png` `vw4_150_waterfall.png` `vw4_150_ancestors.json` |
| H 성능·구조 부채 | **WARN** | 스트립 6문장=예산 6, TTFB 30일 203ms·1년 217ms·strip 135ms·프래그먼트 125ms 전부 판정선 안, 커널 50줄 초과 0/47. 결함: `naver_settle_case`·`commission` 창 술어 COALESCE 가 Seq Scan(같은 창을 `search_date` 로 주면 Index Scan 0.49ms — 원인 증명), 핀 사슬 테스트가 pre_push_smoke 서브셋에 없음(CI 만). | `w4_explain_*.txt` `vw4_explain_h01_*.txt` `w4_ttfb.json` `w4_query_count.json` `w4_fn_len.json` |

---

## 3. 결함 목록 (심각도 순)

심각도는 FAIL(틀린 숫자·유출) > WARN-상(마감 조건에 직결) > WARN > INFO. 재무 영향은 **실측**(DB·API 원 단위) / **추정** / **없음(오해 가능)** 으로 구분. 노력 S(반나절)·M(하루 이틀)·L. 출처: W=워커, V=검증자, C=비평자, CEO=병합.

### WARN-상 (마감 조건 직결)

**D-01 미매칭 정산 채권이 화면에 금액으로 없다 — 존재·권리** (W3-D-01, V3 확인)
- 현상: KPI 는 `unmatched_count`·`unmatched_pending_count`·`unmatched_unlinked_count` 건수 3개뿐. "붙지 않은 돈이 얼마이고 얼마나 오래됐나"를 화면에서 알 수 없다.
- 근거: `foms/services/settlement_channel.py:653~681 _kpi_block`(금액 키 없음), `:609~650 _build_case_stats`(status 별 금액을 `stats` 에 안 넣음), `static/js/settlement/channel.js:1993~1997`(건수 문구). 운영 독립 SQL 재현 `vw3_production.json p_status_all`.
- 재무 영향(**실측·운영**): UNMATCHED 4,257행/4,227건 `settle_expect_amount` 합 **1,480,447,006원**(NORMAL_SETTLE_ORIGINAL 4,225행 1,494,944,259 + 취소 32행 −14,497,253 원값 부호합), 그중 정산 완료 1,471,504,974원. aging(예정일, 기준 09-04): <30일 146,066,928 · 30~59일 188,744,096 · 60~89일 164,502,783 · **90일+ 981,133,199원(2,894건)** · 미래 8,942,032. 링크 있는 1,338건 중 전화 일치 918건(68.6%) 343,095,791원은 워크벤치에서 붙일 수 있는 후보. 링크 없는 2,889건은 붙일 정보 자체가 없다.
- 권고(근본): 예외 큐 머리에 "FOMS 미연결 정산액 = 원값 합(완료/미완료) + 30/60/90일 구간" 한 줄. `_build_case_stats` 의 group-by 에 `sum(settle_expect_amount)` 와 aging CASE 를 붙이면 질의 추가 0(재집계·다른 축 아님, 결정 D-4 저촉 없음). 노력 S~M.

**B-02 지급 보류 KPI 는 창 안 순증감이고 누적 잔액이 없다 — 완전성/표시** (W2-B-02 + W4-G-02 병합, V2 독립 재계산 일치·V4 확인)
- 현상: 타일 "보류·한도" = 조회 창 안 `pay_holdback_amount + settlement_limit_amount` 단순 합. 보류(음수)와 해제(양수)가 상계돼 발생액도 잔액도 아니다. 해제는 자기 날짜의 새 행으로 오고 **분할 해제**도 있다.
- 근거: `settlement_channel.py:551~597 _build_holdback`·`:479 _holdback_of`, `channel.js:1225~1232`. 실측 `w4_labels_db.json`·`vw4_db.json g02_*`: 09-04 창 보류 14행 −119,379,098 + 해제 1행 +2,410,000 = 화면 −116,969,098(`w4_kpi.png`); 그 해제의 보류 짝은 06-19(창 밖). 전 기간(`vw2_sql.py`, 스테이징=운영 동일): 보류 21행 −137,882,500 · 해제 4행 +8,125,300 · 1:1 짝 2(6/19↔8/27 69일, 6/30↔7/16 16일) · 분할 짝 1(1/6 −1,945,900 ↔ 7/15 +1,505,900 + 7/23 +440,000, 190·198일) · 고아 양수 0.
- 재무 영향(**실측**): 미해제 **18행 −129,757,200원**(07-30~08-26). "아직 보류 중"은 "해제 행이 없다"까지가 실측(네이버 측 상태는 조회 불가). 회계팀은 이 잔액을 화면에서 얻을 수 없다.
- 권고(근본): 타일 부제에 "창 안 순증감(보류 −119.4M · 해제 +2.4M)" 부호별 합 + 보류 상세 패널에 "적재 구간 전체 누적 잔액" 한 줄 + 같은 금액(분할 합 포함) 짝 표시. 저장값 합산·대조이지 재계산이 아니다. 노력 M.

**B-01 확정 구간(예정일+30일) 밖 정정은 백필 없이는 영원히 안 들어오는데 문서·화면이 그 리스크를 말하지 않는다 — 완전성** (W2-B-01, V2 근거 보강)
- 현상: 일반(SCHEDULE/MANUAL) 실행은 `settle_expect_date + 30 < today` 인 날짜를 건너뛴다. 네이버가 그 날짜 행을 뒤늦게 정정(금액 변경·삭제·해제 소급)하면 다음 백필까지 옛 스냅샷이 남는다.
- 근거: `foms/services/integrations/naver_commerce/settle_sync.py:442~444 skip_day`·`:544~555 is_finalized`·`:805~816`. 문서 `docs/plans/2026-09-02-naver-settlement-contracts.md:72` 는 동작만 기술. 화면 `channel.js:1010` "확정 구간 ~" 한 줄 — 이 확정은 네이버가 준 것이 아니라 FOMS 가 정한 30일 가정이다(`docs/research/2026-09-02-naver-settlement/01-naver-settle-api-spec.md:8·295·343` — 네이버 Discussion #3123 정산일 이동 실사례, #3674 완결 시점 API 미제공·롤링 재조회 권장). 실측: 08-05 이전 파티션은 09-03 백필·MANUAL 이후 어떤 실행도 안 건드림(`vw2_*.json partition_runs_0729_0807`), `is_finalized(08-05)=True/(08-06)=False`.
- 재무 영향(**추정**): 정정 발생 여부는 네이버 측 사실. 노출 모집단 = 확정 구간 안 미해제 보류 4행 −10,378,102원 + 확정 구간 전체 일별 행. 반증(백필이 1~8월을 재조회했을 때 retro 0)은 간격이 3시간·1일이라 반증력이 약하다.
- 권고(근본): ① 계약 문서에 리스크 + "월 마감 전 전월 1일부터 [받아오기]" 운영 절차 명문화 ② 화면 "확정 구간" 줄에 부제("이 날짜 이전 정정은 [이 구간 받아오기]로만 반영") ③ 익월 1일 05:30 전월 1일부터 자동 백필 옵션. 노력 S(①②)/M(③).

**F-07 05:30 창 안 5회 연속 실행이 소급 변경(RETRO) 예외를 화면에서 지운다 — 완전성** (V2 신규 W2-F-07, 원인 W2-F-05 병합)
- 현상: 워커 루프가 창(10분) 안 매 tick(60초)마다 실행하고 "오늘 이미 돌았다" 가드가 없어 같은 동기화가 5회 돈다(운영 run 19~23 = 20:30:59·32:59·34:59·36:59·38:59 UTC, 시뮬과 초 단위 일치). 화면 예외 큐는 **최신 1행**의 run 만 읽는다.
- 근거: `scripts/maintenance/run_naver_settle_sync.py:165~186 _run_loop`(가드 없음; 비교군 `run_naver_auto_dispatch.py:140~141` 에는 있음), `settlement_channel.py:1182 _run_exceptions(_latest_run(...))`. **오늘 실측**: 스테이징 run 16(창 첫 tick) `retro_changes` 3건(09-07 daily 524,535→10,211,240 · case 1→30행 · commission 2→65행, `vw2_staging_retro.json`), run 17~20 retro 0 → API 예외 종류 `{UNMATCHED, HOLDBACK}`, **RETRO 0**(`vw2_api_exceptions.json`). 운영도 run 19 retro 3건 → 20~23 0. 재현 `vw2_repro_test.py::test_repeated_runs_in_one_window_hide_retro_from_screen`. 호출 수 93×5 = 465/일(`start.sh:53` 주석 "100회 안팎" 대비), rev 가 하루 5씩 뛰어 runs 표·감사 잡음, 쿼터 소진 위험(`settle_sync.py:446~454 ABORTED_QUOTA`).
- 재무 영향(**없음, 측정**): 오늘 3건은 미래 예정일(09-07) 적립이라 정정이 아니다. 단 과거 파티션 정정이 나도 같은 경로로 사라진다 — B-01 과 결합하면 회계팀이 소급 변경을 알 방법이 0. 부가: 미래 적립도 "소급 변경(확정 후 값 변동)" 라벨(`:958`)로 나와 잡음이 된다.
- 권고(근본): `_run_loop` 에 창당 1회 가드(`already_ran`) + 예외 큐가 최신 1행이 아니라 "마지막 OK 이후 24h 안 run 전부"의 retro 를 합치거나 retro 를 누적 테이블/워터마크에 남긴다. 미래 적립과 과거 정정을 라벨로 구분. 노력 S(가드)+M(누적).

**D-02 예외 머리 숫자(스트립·배지)가 모집단이 아니라 상한 뒤 표시 건수이고, 표는 "N건 중 M건"을 말하지 않는다 — 표시/완전성** (V3 신규 VW3-D-04 + W4-G-05 + W3-D-02 병합, 실화면 근거)
- 현상: 요약 스트립 "예외 65건"·채널 탭 배지 "예외 125" = `_EXCEPTION_CAP=50` 갈래별 상한 적용 뒤 목록 길이. 표 머리에 상한 숫자도 "N건 중 M건"도 없다. 일별 3종(HOLDBACK·LIMIT·NEGATIVE)은 합쳐 50, RETRO 도 50 — NEGATIVE·LIMIT 총수는 응답 어디에도 없다.
- 근거: `settlement_channel.py:112·883~898·901~912·945~952·1316 "exception_count": len(exceptions)`, `channel.js:1541·2343·1997`. 계약 테스트가 이 정의를 핀으로 박아 둠(`tests/domains/test_settlement_channel_strip.py:204·215·325`). 실측(스테이징 같은 순간, `vw3_api_probe.json`): 기본 창 strip `exception_count` **65** vs `unmatched_count` 511 + 보류 15 = **526**(8배); 창 01-01~09-18 **125** vs 4,265+25 = **4,290**(34배). DB 모집단 동일(`vw3_staging_probe.json`, `vw4_db.json g05_*`). 실화면 `w4_exceptions_header.png`·`w4_exceptions_text.txt:124`("예외64건")·`:277`(문구 뒤 표 125행). 음성 대조군: 창 09-01~09-18 UNMATCHED 42 = KPI 42(상한 미발동).
- 재무 영향(**없음, 오해 가능**): 회계팀이 "예외 125건"을 마감 전 정리 대상 전량으로 읽으면 4,140건이 시야에서 사라진다. 현재 일별 3종 합 25 < 50 이라 금액 잘림은 0(구조 결함). 완화: 매칭률 타일 부제가 "FOMS 미연결 N건"을 같은 화면에 쓴다(요약 탭에는 없다).
- 권고(근본): `exception_count` 를 상한 적용 전 모집단(`case_stats["unmatched"]` + 일별 3종 미절단 건수 + run 예외 수, 추가 질의 0)으로 정의하고, 응답에 kind 별 `total` + 표 머리 "N건 중 50건 표시". 스트립 테스트 3곳 핀을 모집단으로 교체. 노력 S.

### WARN

**C-01 "전기 비교"가 달력 전월이 아니라 같은 일수 직전 구간이고, 차트의 전기는 또 다른 구간을 가리킨다 — 기간 귀속** (W1-A-02 + VW1-N-01 + VW1-N-03 병합)
- 현상: `_previous_range = (from−span, from−1)`(일수 동일, 달력 분기 없음). 같은 화면의 다른 탭(`settlement_aggregation.py:275`)은 달력 월 기준 — 두 탭의 "전기"가 다르다. 월·주 단위 차트는 전기 구간을 그대로 버킷화해 **인덱스로** 현 버킷과 짝지어(`channel.js:558·1366`) 부분 월 스텁이 전기로 나온다.
- 근거: `settlement_channel.py:322~335·1240·1248`. 실측 `vw1_a02_result.json`: 2월 조회 전기 210,426,677(=DB 01-04~01-31) vs 1월 전체 215,844,737 → **−5,418,060**; 3월 조회 전기 242,824,664(01-29~02-28) vs 2월 213,462,485 → **+29,362,179(+13.8%)**; 5월 조회 196,962,724(03-31~04-30) vs 4월 187,628,053 → **+9,334,671**, `daily_prev` 유령 버킷 2개. 음성 대조군: 8월 조회 전기 = 7월 전체(diff 0). 실화면 `vw1_mar_month_tip.png`: 타일 "▼ −39.8% 전기 대비"(전기 242.8M), 막대 툴팁 "전기 2026-01-01 ₩29,362,179"(01-29~31 3일 스텁) — 한 화면에 서로 다른 "전기" 셋. 기본 창 "▼ −80.2%"(`vw1_default_month_tip.png`)는 미실현 14일을 포함한 창과 전부 실현된 45일을 견준 값(실현 구간만 같은 길이면 −68.5%, `vw1_prev_window_result.json`). 계약 테스트에 `_previous_range` 의미 고정 없음.
- 재무 영향(**실측**): 전기 대비 % 의 분모가 월 화면마다 −5.4M/+29.4M/+9.3M 틀린다. 장부 금액 아님(비교 지표).
- 권고(근본): `granularity=month` 면 전기를 달력 월(직전 동일 개월수)로 정렬해 집계 탭과 정의를 맞추고, 차트 전기는 현 버킷과 같은 개수·오프셋으로. 최소한 라벨을 "직전 N일". KPI 재집계가 아니라 비교 창 정의 문제. 노력 S.

**C-02 "8월 정산액" 3축을 한 화면에서 얻을 수 없고, 원장 축을 바꿔 얻는 합은 KPI 와 다른 금액 개념인데 화면이 말하지 않는다 — 기간 귀속/표시** (W1-C-01, V1 확인)
- 현상: 예정일 8월 = 상단 타일 즉시. 완료일·결제일·기준일 8월 = 원장 "표 날짜 축" 전환 → 날짜 그룹 19/25/28개 요약을 **손으로 합산**(합계 줄 없음, `ledger` 키 = axis·groups·kind·pagination·rows). 그룹 금액 = `settle_expect_amount`(수수료 차감 후·보류 전), 대사 배너 = `pay_settle_amount`, KPI = `settle_amount`(보류 반영 후 실입금) — 세 개념이 라벨 없이 공존.
- 근거: `settlement_channel.py:229·734~744`, `channel.js:1745~1766`(원장 머리, 합계 줄 없음)·`:1825~1837`(바닥 건수만), 파셜 `templates/cs/partials/settlement_channel_body.html:74`. 실측 `w1_c1_result.json`·`vw1_c01_result.json`(8월): KPI 정산 완료액 **34,013,589**(basis 4종 동일) / 원장 그룹 합 예정일 155,725,306(457건)·완료일 155,725,306·결제일 87,891,578(259건, 창 밖 262건)·기준일 157,762,507(468건) — 전부 DB 원 단위 일치 / 대사 배너 165,992,120 / 부가세 8월 매출 168,134,680(기준일 축 원장 157,762,507 과의 차 10,372,173 = 수수료). 항등식: Σ건별 expect 155,725,306 = 일별 pay+commission; + 보류 −121,711,717 = 34,013,589. 스테이징은 완료일=예정일 217/217 이라 완료일 8월 = 예정일 8월(운영 차이는 미측, §7-2).
- 재무 영향(**없음, 오해 가능**): 인용 금액은 전부 실측.
- 권고: 원장 머리에 "이 축·이 기간 합계 N건 · Σ정산 예정 금액 X원" 한 줄 + "원장 금액 = 정산 예정 금액(수수료 차감 후·보류 전), KPI 정산 완료액 = 보류 반영 후 실입금" 한 문장. 재집계 아님. 노력 S.

**A-01 워터폴 마지막 단 "정산 금액"은 정산 완료액 타일이 아니라 완료액+예정액이며 화면이 그 관계를 말하지 않는다 — 표시** (W1-A-01, V1 확인)
- 근거: `settlement_channel.py:172~180·503~519·684~697`, `channel.js:1378`(캡션에 합 관계 없음). 실측 rev19 Σ1~6단 59,340,735 = 7단 = 완료 49,129,495 + 예정 10,211,240(`vw1_a01_a03_result.json`); rev14 49,654,030 = 49,129,495 + 524,535. 음성 대조군 8월(전부 완료) 7단 = 완료액. 잔차 항등식 218/218(워터폴 밖 컬럼 비영 행 0). 실화면 `vw1_default_month_tip.png`·`w4_100_waterfall.png`.
- 재무 영향(**실측**): 차 = 예정 파티션 크기(524,535 → 10,211,240).
- 권고: 표 마지막 줄 아래 "정산 금액 = 정산 완료액 + 정산 예정액(미입금)" 한 줄 또는 마지막 단을 두 조각으로. 노력 S.

**A-03 정산 예정액 타일 세부 "계좌 ₩0 · 충전금 상계 ₩0"이 예정액과 맞지 않는다 — 표시** (W1-A-03, V1 확인)
- 근거: `_daily_totals :512~517` 가 ACCOUNT/CHARGE_AMT 만 더하는데 예정일 전 행은 `settle_method_type NULL`. 실측 `expected 10,211,240 / account 0 / charge 0`. 같은 화면 입금 채널 카드는 "미정(정산 예정) ₩10,211,240 (1건)"(`_build_deposit_channels :714~720`) — 두 곳이 다른 규칙. 실화면 `vw1_default_month_tip.png`, 문구 `channel.js:1204~1210`. 표본 한계: 미완료 일별 행이 전 테이블 1행(09-07 파티션)뿐.
- 재무 영향(**없음, 오해 가능**). 권고: 타일 세부에 "미정 X원" 추가 또는 방식 비면 "입금 방식 미정"(카드와 같은 규칙). 노력 S.

**F-04 FAILED 실행이 반쯤 교체된 창을 그대로 커밋하고, FAILED 자체는 예외 큐에 안 실린다 — 완전성** (W2-F-04, V2 실행 재현)
- 근거: `settle_sync.py:786~803 _drive`·`:630~660`(daily 창 전체 먼저 교체)·`:808~812`(case/commission 하루씩)·`:830~849 _finish`(FAILED 분기에서도 `commit()`, rollback 없음), `settlement_channel.py:945~968`(RETRO·COUNT_MISMATCH 만). 재현 `vw2_repro_test.py::test_failed_run_commits_half_replaced_window`: 2일째 예외 → DAILY {09-01:run2, 09-02:run2} / CASE {09-01:run2, 09-02:run1} 커밋, `last_status=FAILED`, 예외 종류 {'RETRO'}만. 기존 테스트 `test_naver_settle_sync.py:455~468` 는 부분 적재 잔존을 검증하지 않는다. 헤더 "상태 FAILED"(`channel.js:1002`)는 stale 문구가 덮는다.
- 재무 영향(**추정**): 실패 창 k일 이후 일별↔건별 불일치(다음 OK 까지, 보통 다음 날). FAILED run 실측 양쪽 0.
- 권고: FAILED/ABORTED_QUOTA 분기에서 `_finish` 전에 `session.rollback()`(창 단위 원자성) + `_run_exceptions` 에 `SYNC_FAILED` 종류. 노력 S.

**CRIT-A-01 소급 변경·대사 불일치 검출기(RETRO·COUNT_MISMATCH)에 테스트가 0건 — 완전성(검출기 무계약)** (C 신규)
- 근거: `settlement_channel.py:945~968`. `grep -rl "RETRO\|COUNT_MISMATCH\|_run_exceptions" tests/` → 0파일. 음성 대조군: 같은 예외 큐의 HOLDBACK 6·NEGATIVE 4·UNMATCHED 9·UNLINKED 4파일은 계약이 있다. 유일한 단정은 `test_settlement_channel_api.py:228` 키 집합.
- 왜 중요: 이 두 kind 는 F-04(부분 커밋)와 B-01/F-07(소급 변경)의 **유일한 화면 검출기**인데, 실측은 diff 0·RETRO 0 이라 발동한 적이 없고(읽기 전용이라 양성 대조군을 만들 수 없었음), 발동을 보장하는 테스트도 없다.
- 재무 영향(**없음**). 권고: 테스트 2건 — daily≠case 픽스처에서 COUNT_MISMATCH 1행·diff 부호, `retro_changes` 1건 최신 run 에서 RETRO 1행(+상한 잘림). `vw2_repro_test.py` 픽스처를 옮기면 된다. 노력 S.

**F-01 stale 임계값 36시간은 일 1회 05:30 스케줄 대비 너무 커서, 누락 다음 날 근무시간 내내 "상태 OK"로 보인다 — 표시** (W2-F-01, V2 재현)
- 근거: `settlement_channel.py:80 STALE_AFTER_HOURS=36`·`:398~441`, `channel.js:996~1002`. 재현 30.0h·35.9h → False, 36.1h → True. D일 05:38 OK → D+1 05:30 누락 → stale 발동 D+1 **17:38 KST**. 완화: 헤더가 "(N시간 전)"을 항상 보여준다(`agoText :377~383`) — 단 "일 1회 05:30" 기준이 화면에 없어 30시간이 비정상인지 못 읽는다. RUNNING(진행 중) 표시는 없다.
- 재무 영향(**없음, 오해 가능**). 권고: 임계값을 스케줄 주기+여유(26~28h)로, 또는 `next_due` 를 내려 "예정 실행을 넘겼다"로 판정. 노력 S.

**F-02 큐 부재·enqueue 실패·중복을 같은 False 로 접어, 화면이 "이미 대기 중인 동기화가 있습니다"라고 말하고 감사 행도 "(이미 대기 중)"으로 남는다 — 표시/추적** (W2-F-02 + CRIT-E-01 병합, V2 재현)
- 근거: `foms/services/jobs/queue.py:533~549`, API `foms/api/cs/settlement_channel.py:283~295·323~331`(ImportError 만 503; False 는 200 `queued=False`), `channel.js:2088~2092·2176`. 재현 `test_queue_absent_and_enqueue_error_both_return_false`·`test_api_maps_queue_absent_to_200_already_queued`. `queue.py:518~521` docstring("지금은 동기화할 수 없다")·API docstring(`:305~306`)·JS 문구 셋이 서로 다르다. 감사 메시지 `"(이미 대기 중)"`(`:326`)도 큐 부재에 붙는다.
- 재무 영향(**없음, 오해 가능**): Redis 장애·재배포 중 눌렀을 때 "누가 이미 돌리고 있다"로 읽고, 장애 뒤 감사로 복원 불가.
- 권고: 반환을 3상태(queued/duplicate/unavailable), unavailable 은 503 + "지금은 동기화할 수 없습니다", 감사 detail 에 `reason`. 노력 S.

**E-05 운영 측정 계정 비밀번호가 2026-09-02 노출 이후 로테이션되지 않았다 — 통제** (W3-E-05, V3 재현) — **백로그 밖 즉시 조치**
- 근거: 운영 `users` id 57 · ADMIN · `is_active=false` · pbkdf2:sha256:600000 · 노출본 해시 대조 **True**, 음성 대조군(변형 문자열) False(`w3_production.json e5_user`·`vw3_production.json`). 비밀번호 계열 감사 행 08-25 이후 0. 값 원문은 어디에도 기록하지 않았다.
- 재무 영향(**없음**): 운영 ADMIN 자격증명 노출 잔존. 잠금이 완화 요인이나 해제 창마다 노출본이 그대로 쓰인다.
- 권고: 운영 비번 로테이션 + secrets 파일 갱신 + 로테이션을 감사 행으로. 노력 S.

**E-02 동기화 요청 감사 행에 실효 구간·run 연결키가 없다 — 추적성** (W3-E-02, V3 확인)
- 근거: API `:316~324` detail = {queued, backfill_from, channel}. `naver_settle_sync_runs.scope` 키 = backfill_from·channel·from·to·trigger, 감사행/job id 없음, 새벽 run `actor_user_id` NULL. 스테이징 3행·운영 4행 detail 키 동일. 보강(C): `_backfill_arg :246~270` 은 범위 밖을 400 으로 거절하므로 기록값=실효값(클램프 없음).
- 재무 영향(**없음**). 권고: detail 에 job id·요청 시 계산된 기본 창, 또는 워커가 run 시작 시 감사 행 id 를 scope 에 역기록. 노력 S.

**E-06 CSV 내보내기 감사 행에 유형·검색 조건(type·q)이 없다 — 추적성** (V3 신규 VW3-E-06)
- 근거: API `:417~418` 은 `filters=_export_filters()` 를 커널에 넘기는데 `:421 _log_export(...)` 는 조건을 받지 않는다(`:355~381` detail = kind·channel·from·to·basis). `_log_export` 자신의 docstring(`:370~372`)이 실효값을 남기는 이유를 말하는데 조건에는 적용 안 됨. 실측: 스테이징 export 감사 33행 중 type/q 키 0/33, 운영 5행 동일. 음성 대조군: 조건을 안 받는 daily 는 400 이라 행 자체가 없다.
- 재무 영향(**없음**): `type=NORMAL_SETTLE_AFTER_CANCEL` 만 받아 간 파일과 전량 파일이 감사상 구별되지 않는다. 권고: `_log_export` 에 filters 전달, 계약 테스트 1행. 노력 S.

**G-01 "정산 완료액" 타일 부제 "통장 입금 완료분 · 정산 완료일 기준"이 계산과 다르다 — 표시/기간 귀속** (W4-G-01, V4 확인)
- 근거: `channel.js:1201` vs `_daily_totals :529~545` — **정산 예정일 창** 안 `settle_complete_date IS NOT NULL` 행의 `settle_amount` 합, 입금 방식 무관(CHARGE_AMT 충전금 상계도 "통장 입금"에 포함, 예정분만 `:541~545` 에서 계좌/충전금 구분). 상단 축 문구는 "정산 예정일 기준"(파셜 `:74`, `w4_kpi.png`).
- 재무 영향(**실측**): 스테이징 완료일≠예정일 0/218 → 기간 귀속 실효 0원; CHARGE_AMT 완료 행 1건 −763원(2025-10-14, `w4_labels_db.json`·`vw4_db.json g01_*`) 혼입. 전표: 보통예금 / 네이버페이 미수금 — CHARGE_AMT 행은 충전금(선급금)이라 한 줄로 못 쓴다.
- 권고: 부제를 계산 그대로 "정산 예정일 창 안 · 완료 처리된 행의 정산 금액(계좌+충전금)" 또는 `settled` 도 계좌/충전금으로 갈라 부제에. 노력 S.

**G-03 같은 낱말 "정산 예정"이 두 필드, 같은 필드 `pay_settle_amount` 가 세 이름 — 표시** (W4-G-03, V4 확인; C-02 와 교차)
- 근거: KPI "정산 예정액"(`channel.js:1204`) = 일별 `settle_amount` 미완료분; 건별 CSV/원장/시트 "정산 예정 금액"/"정산예정금액"(`settlement_channel_export.py:242·323`) = `settle_expect_amount`. `pay_settle_amount` = 화면 "결제 정산"(`:118`)·CSV "결제 정산 금액"(`:195·235`)·시트 "정산기준금액"(`:320`) — "정산 기준"은 다른 열에서 날짜 낱말. 실측 8월(`w4_csv_sums.json`·`vw4_probe.json`): 시트 정산예정금액 합 155,725,306 / 일별 CSV 정산 금액 34,013,589 / 09-04 KPI 정산 예정액 524,535 — 정의가 다른 세 숫자.
- 재무 영향(**실측 숫자, 오해 가능**). 권고: 시트 헤더는 사용자 확정(09-03)이니 유지, **KPI 쪽**을 "미입금 정산액(일별 정산 금액 중 미완료분)"으로, 부제에 "건별 '정산 예정 금액'과 다름". 노력 S.

**G-04 대사 배너 "일별 합계 vs 건별 합계 → 대사 일치"가 어떤 금액을 대사했는지 말하지 않는다 — 표시** (W4-G-04 ≡ W1-A-04 병합, V1·V4 확인)
- 근거: `_build_reconcile :734~745` 는 `pay_settle_amount` 만 비교(Decimal 정확 비교·허용 오차 0 확인). 배너 문자열 `channel.js:1509~1520` 에 필드명 없음. 실화면 `w4_kpi.png`·`vw4_100_top.png`·`w4_exceptions_header.png`("일별 합계 ₩1,576,637,530 vs 건별 합계 ₩1,576,637,530 → 차이 ₩0 대사 일치"). 정산 금액(일별 `settle_amount`)과 건별 `settle_expect_amount` 는 대사하지 않는다(보류가 일별에만 있어 원래 다름).
- 재무 영향(**없음, 오해 가능**): "대사 일치"를 입금액 대사로 읽기 쉽다. 권고: "결제 정산 금액(paySettleAmount) 기준" 한 마디. 노력 S.

**G-06 조건을 건 CSV 가 조건 없는 CSV 와 같은 파일명으로 내려오고, 허용 집합 밖 type 은 빈 파일(200)이 된다 — 표시/완전성** (W4-G-06, V4 재현)
- 근거: `settlement_channel_export.py:539~569 _filter_clauses`(type 을 enum 카탈로그와 대조 없이 `==`), `:710~732 export_filename`(인자에 type/q 없음). 재현(`w4_csv_type_neg.json`·`vw4_api.json`): `kind=case&type=X` → 200 CSV 0행, `q=zzzz-no-such` 0행, `type=PROD_ORDER` 457행 — 셋 다 파일명 `naver_settle_case_20260801_20260831.csv`(조건 없는 파일과 동일). 음성 대조군: `daily&type=X` 400 JSON, `kind=nope` 400 JSON.
- 재무 영향(**없음**): 부분 원장이 전체 원장과 같은 이름으로 폴더에 남고, 오타 type 은 "이 달 정산 없음"처럼 보이는 헤더만 있는 파일. 권고: 파일명에 `_type-<코드>`·`_q` 슬러그, type 을 `_ENUM_MAPS` 로 검증해 400. 노력 S.

**G-07 100% 에서도 워터폴 X축 라벨 "지급 보류·한도"가 "지급보류·한"으로 잘려 이웃과 겹친다 — 표시** (W4-G-07, V4 재현)
- 근거: `channel.js:1416~1419 shortStepLabel`(공백 제거 뒤 6자 초과면 `slice(0,6)`). 실화면 100%·1440×900 `vw4_100_waterfall.png`·`w4_100_waterfall.png`: "지급보류·한"(x 1244~1300)과 "충전금상계"(1297~1351) 3px 겹침(`vw4_100_measure.json` 교차 1쌍). 일별 차트 0.
- 재무 영향(**없음**). 권고: 2줄(`<tspan>`) 또는 약어 표를 `_WATERFALL_STEPS` 에 두고 6자 절단 제거. 노력 S.

**G-08 150% 글자 크기에서 워터폴 판독 불가 + Y축 클립 + 본문 가로 스크롤 + KPI 값 넘침 — 표시 (원장 F6 후속)** (W4-G-08, V4 증상 확인·**원인 정정** VW4-G-08a)
- 실측(`vw4_150_measure.json`·`vw4_150_waterfall.png`·`w4_150_full.png`): 워터폴 X축 교차 6쌍(전부 붙어 읽을 수 없음), Y축 "5,000만"·"1,000만~3,000만" 왼쪽 클립, `scrollWidth` 1675 > 1440(본문 가로 스크롤 — 프론트 규칙 위반), KPI "−₩89,003,279" +1px(워커 −₩116,969,098 은 +13px, 데이터 의존). 100% 복귀 후 0(음성 대조군).
- 원인(정정): 워커의 "표가 overflow-x:auto 컨테이너 안에 있지 않아"는 **틀렸다** — 표는 `.s-ch-tablewrap{overflow-x:auto}`(`static/css/settlement/settlement-channel.css:316`, `channel.js:1648`) 안에 있다. 실제 원인(`vw4_150_ancestors.json`): `details.s-ch-group`(display:block, **min-width:auto**, 1650px)이 `display:grid .s-ch-ledger-body`(1414px)의 그리드 아이템이라 min-content 로 부풀어 격자를 뚫는다. 워커 권고 "래퍼 overflow-x:auto 한 줄"은 적용해도 변화 0.
- 재무 영향(**없음**). 권고: `.foms-settle .s-ch-group { min-width: 0; }` 한 줄(또는 `grid-template-columns: minmax(0, 1fr)`), 워터폴 라벨 2줄/약어, Y축 여백을 `--s-fs` 에 비례. 노력 S.

**D-03 매칭된 건의 정산액≠출고가를 화면이 예외로 내지 않는다 — 정확성/존재** (W3-D-03, V3 전제 보정)
- 근거: 예외 kind 7종(`:883~968`)에 금액 차 없음. 실무 탭 행 API 는 `shipping_price`(`foms/services/settlement_rows.py:332`)와 `naver_settlement.amount`(`:149~207·349`)를 같은 행에 이미 싣지만 프론트가 **일부러** 금액을 안 그린다(`static/js/settlement/operations.js:466~467` "금액은 그리지 않는다 — 노출 최소화 원칙", CSV `:776~777` 상태만). 실측 스테이징 매칭 2주문(`vw3_match_diff_staging.json`): #4242 출고가 **0**(품목 미입력·DRAWING) vs pay 2,830,000/expect 2,698,971(취소 없음), #4461 12,680 = 12,680.
- 재무 영향(**실측·스테이징**): 불일치 절대합 2,830,000원(1건) — 정산 오류가 아니라 주문 입력 공백. 운영 매칭 3주문은 출고가 대조 미실시(§7-10), 부분 취소 표본 0.
- 성격: 소스에 명시된 설계 결정(노출 최소화)과 회계 대사 요구의 충돌 → §6-5 결정 재고. 권고: 매칭 행에 `pay_settle_amount` 와 출고가를 **나란히 원값으로** 두고 다르면 예외 kind(AMOUNT_DIFF). 두 원값 병기이지 재계산이 아니다. 노력 M.

**H-01 `naver_settle_case`·`commission` 창 술어 COALESCE 가 인덱스를 못 타 Seq Scan — 유지보수** (W4-H-01 + VW4-H-01a)
- 근거: EXPLAIN(스테이징 PG 17.11, `w4_explain_*.txt`·`vw4_explain_h01_*.txt`): case 질의 4종 30일·1년 창 전부 Seq Scan 1.8~5.9ms(6,303행 8.7MB), commission 4.98ms. **음성 대조군**: 같은 창을 `search_date BETWEEN` 으로 주면 `Index Scan using ix_nsc_unmatched` 0.49ms → COALESCE 가 원인. 부수 사실: case 6,303행·commission 13,984행 모두 `settle_expect_date IS NULL` 0·`≠ search_date` 0(현재 데이터에서 항등식). 축 컬럼 `pay_date`·`settle_complete_date`·`settle_basis_date` 인덱스 0. 스트립 6문장 중 case 3문장이 이 술어.
- 재무 영향(**없음**): 체감 0(ms 단위, TTFB 판정선 안). 프로젝트 규칙 "hot path Seq Scan 없음" 위반, 행 수에 선형.
- 권고: `(channel, COALESCE(settle_expect_date, search_date))` 식 인덱스(case·commission 각 1, 마이그레이션 1개). 도입 뒤 `ANALYZE` 후 EXPLAIN 으로 채택 확인(표현식 정확 일치 필요). 술어를 `search_date` 로 바꾸는 우회는 의미가 달라지므로 비권고. 노력 S.

**H-02 핀 사슬(셸 4줄·채널 2줄·`_CHANNEL_PIN`)은 테스트가 잡지만 pre_push_smoke 서브셋에 없다 — 유지보수** (W4-H-02, V4 확인)
- 근거: 핀 값 셸 `settlement_dashboard_body.html:20·21·423·424` = `20260903d`, 채널 `:22·425` = `20260903i`, `tests/domains/test_settlement_channel_render.py:72·476 assert pins == {_CHANNEL_PIN}`, 실무 render `test_settlement_operations_render.py:967~987`. `scripts/ops/pre_push_smoke.ps1:214~241` 서브셋에 `test_settlement_*` 0건(`-Full` 만 전체), CI `.github/workflows/ci.yml:109` 전체 스위트 → CI 만 잡는다.
- 재무 영향(**없음**). 권고: 서브셋에 채널 render 핀 테스트·실무 render 핀 테스트 추가(초 단위). 노력 S.

### INFO

- **N-02 월·주 버킷의 `completed` 가 전부-아니면-전무라 완료+예정이 섞인 버킷이 통째로 "(정산 예정)"으로 표시** (V1 신규 VW1-N-02) — `settlement_channel.py:523 all(done)`, `channel.js:1362·1201·1209`. 실측 9월 버킷 "정산 예정 ₩25,327,146" = 완료 15,115,906 + 예정 10,211,240(`vw1_extra_result.json`, `vw1_default_month_tip2.png`) — 완료분 15,115,906 이 예정으로 읽힌다. 일 단위는 미발생. 권고: 버킷에 완료/예정 합을 따로 실어 "일부 완료". 노력 S.
- **C-03 결제→지급 시차 지표 부재** (W1-C-02) — grep 0건. 실측(`w1_c3_result.json`): NORMAL_SETTLE_ORIGINAL 결제일→완료일 n=6,228 평균 18.19일·중앙값 17·최소 1·최대 74, 월별 17.2~19.7. 제안: 타일 1개 "평균 지급 소요일 18일 · 중앙값 17일"(날짜 차이, 재계산 아님). 노력 S.
- **F-08 OK 가 한 번도 없고 FAILED 만 있으면 stale=True 라 "36시간 넘게 갱신되지 않았습니다"가 "방금 실패"를 덮는다** (V2 신규) — `settlement_channel.py:430~441 age is None → stale`, `channel.js:998~1001`. 재현 테스트만(실화면 표본 없음). 권고: `failed` 모드 분리. 노력 S.
- **B-03 영업일 구멍 9일(1/16·3/4·3/20·4/17·5/1·5/29·7/10·7/17·8/13)은 적재 실패 근거 0 이나, 화면이 "정산 없음"과 "적재 실패"를 구분하지 못하는 구조** (W2-B-03) — 9일 모두 OK 백필 run scope 안, 8/13 은 롤링 12회 재조회에도 빈 날, case·commission 0행, 다음 영업일 대조군 61·11행. `_build_daily :484~519` 구분 신호는 `sync.coverage_*`·`last_ok_at` 뿐. 네이버 원장 대조는 불가(§7-5).
- **F-06 JSON API 에 `Cache-Control: no-store` 부재(하드닝)** (W2-F-06) — 현재 캐시 경로 0 이라 PASS. 응답에 구매자명이 실리는데 SW PII 게이트(`static/sw.js:218~222`)는 `no-store` 헤더에 의존 — 미래에 `/api/` 분기가 추가되면 그대로 캐시된다. 1줄 추가. 노력 S.
- **H-03 `channel.js` 50줄 초과 함수 6/117(최대 77), 파이썬 4파일 0/112, 리터럴 단정 계약 7건** (W4-H-03) — 핀 리터럴은 의도된 마찰, 함수 시그니처 리터럴 2건이 이름 바꾸기를 막는 정도. 낮음.
- **H-04 채널 CSS 하드코딩 색 5곳**(`settlement-channel.css:101·420·573·265·436/625`) (W4-H-04) — 헤더 주석("색은 토큰 블록 한 곳")과 어긋나나 다크가 셸에서 막혀 실효 0.

---

## 4. 개선 백로그 (우선순위 = 재무 영향 × 빈도 ÷ 노력)

**백로그 밖 즉시**: E-05 운영 측정 계정 비밀번호 로테이션(S). 재무 아닌 통제 항목이라 순위표에 넣지 않고 오늘 처리.

| 순위 | 항목 | 노력 | 왜 지금 |
|---|---|---|---|
| 1 | **D-02 예외 머리 숫자 모집단화 + "N건 중 50건 표시"** | S | 회계팀이 매일 보는 첫 숫자가 8~34배 작다. 추가 질의 0, 테스트 핀 3곳만 바꾸면 끝. |
| 2 | **B-02 보류 KPI 발생·해제 분리 + 누적 잔액 한 줄** | M | 1.3억 잔액이 화면 어디에도 없어 마감마다 손계산. 분할 해제까지 짝을 보여야 "풀렸는지"를 안다. |
| 3 | **D-01 미매칭 정산액·aging 한 줄** | S~M | 14.8억(90일+ 9.8억)이 건수로만 보여 채권 관리 대상이 시야 밖. group-by 에 sum 한 개 붙이면 된다. |
| 4 | **F-07/F-05 창당 1회 가드 + RETRO 누적(24h 합치기) + 미래 적립/과거 정정 라벨 구분** | S+M | 매일 5회 실행이 정정 신호를 매일 지운다. 마감 전 백필 효과도 다음 05:30 뒤 사라진다. 호출 465→93/일. |
| 5 | **라벨 묶음 한 커밋**: G-01 완료액 부제 · G-03 KPI "미입금 정산액" · G-04 배너 "결제 정산 금액 기준" · A-01 워터폴 합 관계 · A-03 예정액 "미정" · C-02 원장 축 합계 줄+금액 개념 한 문장 | S | 전표 한 줄을 막는 라벨 4개가 전부 문구 수정이라 한 커밋으로 닫힌다. 숫자는 안 건드린다. |
| 6 | C-01 전기 정의(월 단위 달력 월·차트 전기 오프셋·라벨 "직전 N일") | S | 월 화면마다 전기 대비 % 분모가 틀리고 다른 탭과 정의가 다르다. |
| 7 | B-01 문서·"확정 구간" 부제·익월 1일 자동 백필 옵션 | S/M | 조건 2(수동 백필)를 사람 기억에서 코드로 옮긴다. |
| 8 | CRIT-A-01 RETRO·COUNT_MISMATCH 테스트 2건 + F-04 FAILED rollback·SYNC_FAILED kind | S | 유일한 검출기에 계약이 없고, 실패가 반쯤 적재된 창을 남긴다. `vw2_repro_test.py` 픽스처 재사용. |
| 9 | F-01 stale 26~28h(또는 next_due) + F-02 3상태·503·감사 reason + F-08 failed 모드 | S | 워커 사망·재배포 때 화면이 거짓 안심을 준다. |
| 10 | G-06 CSV 파일명 슬러그·type 검증 400 + E-06 export 감사 filters + E-02 sync 감사 job id | S | 내려받은 파일과 감사 행이 서로를 못 찾는다. |
| 11 | G-08a `.s-ch-group{min-width:0}` + G-07 라벨 2줄/약어 + Y축 여백 | S | F6 수용 리스크를 CSS 한 줄로 닫는다(워커 권고 아닌 검증자 원인으로). |
| 12 | H-01 COALESCE 식 인덱스 2개 + H-02 smoke 서브셋 핀 테스트 | S | 규칙 위반 실재·체감 0. 운영 10배에도 수십 ms 라 순위 낮음. |
| 13 | D-03 매칭 행 출고가·pay_settle 병기 + AMOUNT_DIFF (§6-5 결정 뒤) | M | 표본이 극소(스테이징 2·운영 3)라 적체 해소 뒤 효과. |
| 14 | N-02 버킷 부분완료 · C-03 지급 소요일 타일 · F-06 no-store · H-03/H-04 | S | 보조. |

---

## 5. NOT-A-DEFECT (조사했지만 결함 아님 — 다음 리뷰어가 다시 파지 않게)

| 항목 | 이유 | 근거 |
|---|---|---|
| KPI·차트·워터폴이 축 셀렉트와 무관하게 정산 예정일 | 결정 사항. 8월 basis 4종 호출 모두 KPI 34,013,589 동일 | `vw1_c01_result.json` |
| 시트 헤더 "정산기준금액" = `pay_settle_amount` | 2026-09-03 사용자 확정 7열. 합 177,512,360 이 대사 배너와 같음. 시트 항등식(정산기준금액+Npay 수수료+매출연동수수료=정산예정금액) 8월 457/457·전기간 6,303/6,303 | `w4_csv_sums.json` `w4_labels_db.json` |
| rev14→rev19 숫자 변화(예정액 524,535→10,211,240·건수 485→514·미매칭 482→511) | 09-05 05:30 스케줄 동기화(runs 16~20 OK). 각 스냅샷 안에서는 전 층 일치 | `w3_staging_followup.json` |
| 취소 행이 예외 큐 NEGATIVE 로 안 뜸 | NEGATIVE 는 일별 `settle_amount<0` 만(`:883~898`). 건별 취소는 원장에 부호 그대로 + 바닥 문구 "음수는 취소·환급입니다"(`channel.js:1837`). 양성 대조군 2025-10-14 −763 은 뜬다 | `w1_api2_result.json oct2025_day` |
| 08-05~08-25 일별 `settle_amount` 0 | 지급 보류가 결제 정산액+수수료를 전액 흡수(6성분 항등식 218/218) | `w1_fresh_db_result.json` |
| 매칭 건 expect≠pay(#4461 11,840 vs 12,680) | expect = pay − 수수료. 정상 | `vw3_match_diff_staging.json` |
| 부가세 9월 total 0·rows 0·"확정" 접미 | 미제공 구간을 0 으로 그리지 않음, `vat.final` = 창 안 전 행 `is_final`, 배너 "2026-08-31까지 제공 · 당월분은 익월 마감 후" | `w1_api_vat_sep.json` `w4_vat.png` |
| 부가세 관계 | `ts=tx+te` 315/315·증빙 5종 합 315/315·일별=건별 315/315·월별 부가세 매출 = Σcase pay_settle(기준일 월) 11/11 원 단위 일치·축이 다르면 다름(6월 예정일 축 197,029,340 ≠ 175,171,910) | `w1_a5_result.json` `vw1_probes_result.json` |
| RUNNING 잔류 run(운영 10·11, 스테이징 8) | 결정 사항. 그 scope 를 뒤이은 OK run(12·9)이 덮어 빈 구간 0 | `w2_*.json b4_monthly` |
| coverage 합집합·배너 술어 사각(B-4) | `_write_watermark :878~885` 가 OK 일 때만 전진 → 잘린 백필은 coverage_from 을 못 넓혀 배너가 계속 뜬다. coverage 안 빈 달 스테이징 0/12·운영 0/9. coverage_from 이전 daily 행 0(양쪽) | `w2_staging.json` `w2_production.json` |
| 28일/30일 창 분할 경계 | 42/42 통과(합집합=iter_days·교집합 0·역순 []·size 0 자기 보호·윤년·무작위 200), 46일 daily 는 [28,18] 분할. `settle/daily` startDate 끝 포함은 sync_run_id 실증(8/4 run 10·8/5 run 15) — 공식 문서 미기재(NOT IN DOCS) | `w2_windows.json` `w2_boundary.json` `vw2_windows_probe.txt` |
| 영업일 구멍 9일 | 적재 실패 근거 0(§3 INFO B-03) | `vw2_*.json b1` |
| `settlement_limit_amount ≠ 0` | 0행(양쪽), 결정 사항 확인 | `w2_*.json` |
| 스테이징 2026-09 daily 합 ≠ 운영 | 동기화 시점 차이 | `w2_*.json` |
| 워커 적재 뒤 웹 캐시 | API 헤더·SW 분기·identity map(요청마다 `close_db`)·버전 카운터 어디에도 경로 없음, rev 14→19 라이브 전진 | `w2_strip.json` `verify_w2.md §3` |
| 폴링 만료 뒤 재알림 없음(W2-F-03) | 문구 "N분 안에 반영되지 않았습니다 … 새로고침하세요"(`channel.js:2176`)가 정직 | — |
| 실패 뒤 다음 OK 가 자가 치유 | 롤링 창이 같은 구간을 다시 훑어 F-04 불일치는 하루 안에 사라진다(노출 기간 제한 사실) | — |
| `deposit_channels[1].account_no_masked=''` | 충전금 상계 채널(bank_type None·예금주 `*`) — 계좌 없음 | `w3_api_full.json` |
| API 응답의 10자리+ 숫자열 465개 | `product_order_id`/`order_id` 16~17자리, 계좌(14자) 아님 | `w3_staging_batch.json e3_scan` |
| W3 마스킹 "앞 6자리 검색 0건" 대조군 | 저장 형태가 `999*******9999`(네이버가 가운데 7자리를 이미 가림)라 그 검사는 무효였음. verbatim 스캔으로 교체해 PASS 유지(양성 daily raw 200행) | `vw3_staging_probe.json s_account_shape` |
| sync 감사 행 행위자 user 38 | 사용자 전환(IMPERSONATE) 뒤 호출. 행위자 기록 자체는 정상 | `w3_staging_batch.json` |
| 기본 창 미매칭 KPI 482(API 07:42 UTC) vs SQL 511(02:00 UTC 익일) | 야간 동기화가 롤링 창 421행 재적재 — 시차 | `w3_staging_followup.json` |
| 비로그인 export 302 → `/login` | JSON 401/403 이 아니라 HTML 리다이렉트(앱 전역 관례), 파일 아님·유출 없음. 로그인 배우 거부는 403 JSON 계약(`test_settlement_channel_export_api.py:106~118`) | `w3_api_log.json` `critic.md §3-2` |
| `kind=daily&type=X` 400 JSON | 설계대로(`FILTER_FIELDS` 빈 튜플 → ValueError → 400) | `w4_csv_check.json neg_bad_type` |
| CSV 형식 8종 | BOM·CRLF·금액 평문(`_fmt_money :359~372` 더존·이카운트 파서)·ISO 날짜·헤더 순서·축 슬러그 전부 PASS(14,000+셀), 7월 commission·`sheet&basis=complete` 재확인 | `w4_csv_check.json` `vw4_api.json gpass_*` |
| 다크 테마 미대응 | 셸 `static/js/foms/theme.js:43~48` 이 비모바일 뷰포트를 무조건 light — 채널 탭 고유 결함 아님(요약 대시보드 v1 미결과 동일 범위) | `w4_dark.png` |
| ① `naver_settle_daily` 1년 창 Seq Scan | 218행 385KB 에서 플래너 비용 선택 0.385ms, 30일 창은 `ix_nsd_channel_expect` Index Scan | `w4_explain_q1_*` |
| 대시보드 14~15 문장 | 문서화된 예산은 스트립 6 뿐. 현재/전기 2회 조회는 의도된 비교 | `w4_query_count.json` |
| 100% 일별 차트 | 라벨 교차 0·클립 0·가로 스크롤 0 | `w4_100_overlap.json` |
| 동기화 상태 줄·부가세 각주 | 최종 동기화 시각·상태·적재/확정 구간·부가세 제공 한계·과세표준 안내 전부 화면에 있음 | `w4_channel_text.txt` |
| 콘솔·네트워크 | 채널 탭 진입·예외/부가세/150% 조작 콘솔 메시지 0, 4xx/5xx 0(302 로그인·304 프리페치뿐). V1 콘솔 400 2건은 자기 조작(from>to) | `w4_console_*.txt` `verify_w4.md §2` |
| `w4_150_full.png` 가운데 메뉴 중복 | 전체 페이지 캡처 아티팩트 | — |
| 워커 로그 응답 원문 유출 | `settle_sync.py` logger 6곳·`client.py` 15곳 — 2xx 본문·행 dict 를 통째로 찍는 곳 0(`_body_text :1235` 는 오류 응답만) | `critic.md §3-6` |

REFUTED 0건. 단 W4-G-08 의 **원인 설명**(래퍼 부재)은 검증자가 반박·정정했고(`vw4_150_ancestors.json`), 증상 자체는 유지됐다(§3 G-08).

---

## 6. 결정 재고 요청 ("이미 결정된 사항" 중 뒤집을 근거를 찾은 것)

1. **부호 규약 문구 "해제는 같은 금액의 양수 행이 뒤에 온다" → "같은 금액 또는 분할 합"** (C §4-2, W2·V2·V4 실측). 실데이터에 분할 해제가 있다: 1/6 −1,945,900 → 7/15 +1,505,900 + 7/23 +440,000(190·198일). 결정을 뒤집자는 것이 아니라 B-02 짝 매칭 권고가 규약과 어긋나지 않도록 문구를 넓혀야 한다.
2. **재계산 금지(D-4) 아래 "파생(계산)" 라벨 두 열 허용 여부 — 공급가액·세액** (W1 §6). 부가세 탭은 `naver_vat_daily/case` 에 공급가·세액 컬럼이 없어(`models.py:3856~3864`, 네이버 API 형상) 회계팀이 전표마다 `taxation_sales × 10/110` 을 손으로 계산한다. 실측 과세매출=총매출 11개월 전부·면세 0. 비율(abs)처럼 파생 표시로 취급하는 안을 재고 요청. 시트 7열 세액 열 부재도 같은 뿌리.
3. **시트 7열(09-03 사용자 확정)에 열 3개 추가 검토** (W4 §8-1): `정산 구분`(settle_type — 취소 정산 45행 −19,122,130원이 시트에서는 음수로만 보인다, 8월 2행 −101,000), `거래처` 상수("네이버페이"), `계정`. 회계 프로그램 최소 열(거래일·거래처·공급가·세액·합계·계정) 중 있음: 거래일·합계 / 없음: 거래처·공급가·세액·계정.
4. **F6 "150% 수용 리스크" 재고** (W4 §8-2 + VW4-G-08a): 워터폴은 판독 불가 수준이고 본문 가로 스크롤이 프론트 규칙에 걸린다. `.s-ch-group{min-width:0}` 한 줄로 리스크 수용 없이 닫힌다.
5. **매칭 행 "금액은 그리지 않는다 — 노출 최소화 원칙"(`operations.js:466~467`, 소스 명시 설계) vs 회계 대사 요구** (W3 §6 + V3). 실무 탭 행 API 는 출고가와 정산액을 이미 같은 행에 싣는다. 두 원값 병기 + AMOUNT_DIFF 예외는 D-4 재계산 금지와 충돌하지 않는다. 스테이징 실표본 #4242(출고가 0 vs 2,830,000)가 현재 어디에도 안 보인다.
6. **"매칭률 0% = 워크벤치 적체" 결정은 존중** — 뒤집지 않는다. 다만 운영 실측 "링크 있는 미매칭 1,338건 중 전화 일치 918건(68.6%)·343,095,791원"을 적체 해소 우선순위 근거로 첨부한다(D-01).
7. 그 밖의 결정(KPI 재집계 기각·축 셀렉트 위치·xlsx 금지·RUNNING 잔류·coverage 합집합·403 해소·"예정" 스캔 예외·F9/F10 수정분)은 뒤집을 근거 없음. 이 보고서의 권고는 전부 원값 합산·병기·문구 수준이며 D-4 를 건드리지 않는다.

---

## 7. 확인 못 한 항목과 이유 (침묵 금지)

| # | 항목 | 이유 | 대체 근거 |
|---|---|---|---|
| 1 | **운영 화면·운영 3중 대사(A 축)** | 운영 화면 조작 금지, W1 은 운영 DB 권한 없음. 운영 DB 는 W2·W3·검증자 W2·W3 각 1회(합계 4회, 브리프 허용·프롬프트 원문 "1회"보다 많음)만 열었고 정확성 대사는 안 넣었다. | 스테이징 4층 일치 + 코드 동일 + 같은 네이버 계정. 보류 데이터는 운영=스테이징 원 단위 동일. → 조건 5 |
| 2 | "완료일 8월 ≠ 예정일 8월" 차이 실증 | 스테이징 완료일≠예정일 표본 건별 0/6,303·일별 0/218(`critic_c1_case_axis.json`). 운영 배치 4개 어디에도 그 질의 없음. | 정의 차이는 코드로 확인(C-02), 값 차이는 운영 재감사 필요 |
| 3 | COUNT_MISMATCH·RETRO 양성 대조군(실데이터) | 읽기 전용이라 불일치를 만들 수 없음. 테스트 계약도 0(CRIT-A-01). | SQLite 재현 `vw2_repro_test.py` |
| 4 | 취소 유형 3종(QUICK_SETTLE_CANCEL·NORMAL_SETTLE_BEFORE_CANCEL·QUANTITY_CANCEL_RESTORE) 부호 | 스테이징 표본 0(settle_type 은 ORIGINAL·AFTER_CANCEL 둘뿐). | AFTER_CANCEL 2건 3층 부호 동일 |
| 5 | 영업일 구멍 9일이 네이버 원장에서도 "정산 없음"인지 | 네이버 API 직접 호출·셀러센터 조회 금지. | 두 엔드포인트 독립 일치·OK run 재조회 |
| 6 | 미해제 보류 18행이 네이버 측에서 실제 아직 보류 중인지 | 네이버 측 사실. 건별 테이블에 보류 컬럼·HOLDBACK settleType 없음(`models.py:3714~3771`). | "해제 행 없음"까지 |
| 7 | 확정 구간 안 정정이 실제 발생했는지(금액) | 백필 실행 금지(운영 쓰기·큐 점유). | 다음 백필의 retro_changes 로만 |
| 8 | FAILED 부분 커밋·재배포 중 [지금 동기화] 운영 실측 | 실패 유발·버튼 금지. FAILED run 양쪽 0. | 재현 테스트 7 passed |
| 9 | 회계팀(MANAGER/STAFF+ACCOUNTING)·CS 매니저·VIEWER 계정 실측 403 표 | 스테이징 측정 계정이 ADMIN 하나. | 코드(SSOT·엔진 순서)+계약 148 passed+export/페이지 거부 테스트 존재 확인 |
| 10 | 운영 매칭 3주문 출고가 대조·부분 취소 매칭 차액 표본 | 운영 배치는 SQL 집계만(규율), 취소 포함 매칭 건 0(양쪽). | 스테이징 2주문 |
| 11 | stale/never/failed·`vat.final=false` 문구 실화면 | 스테이징·운영 모두 OK·전 행 final 이라 표본 없음. | 코드 문구 인용 |
| 12 | 운영 `raw_snapshot`·`security_logs` verbatim 계좌 스캔 | 운영 배치 1회 규율(그 배치의 숫자 스캔은 형태상 무효). | 스테이징 verbatim 0건, 저장 형태(14자·1계좌) 동일 |
| 13 | 운영 워커 `FOMS_NAVER_SETTLE_SYNC_ENABLED` 값 | railway 조회 안 함. | 운영 runs 가 매일 05:30 KST SCHEDULE 로 도는 것이 확인돼 사실상 켜짐 |
| 14 | 핀 사슬 음성 대조군 실행(핀 하나만 올려 red 확인) | 워크트리 편집 금지. | 단정식 인용 |
| 15 | 다크 실화면 | 데스크톱에서 설계상 불가. | — |
| 16 | 시트 취소 행(부호로만 구분)의 회계 실무 처리 | 사용자 확인 필요. | §6-3 |
| 17 | Railway 앱 로그 실물의 응답 원문 유출 | 로그를 열지 않음. | 코드 grep 0(`critic.md §3-6`) |

프로세스 메모: 검증자 W1 이 설계상 W4 전용이던 gstack browse 를 툴팁 캡처에 썼다(조회·읽기 전용, 결과 유효 — 규율 이탈 기록만). 워커 W4 의 G-08 원인 서술은 검증자가 정정했고 본 보고서는 정정본을 채택했다.

---

## 8. 부록 — 회계팀용 라벨 해석표 (조건 3)

| 화면 라벨 | 실제 값 | 전표로 옮길 때 |
|---|---|---|
| 정산 완료액 | 정산 **예정일** 창 안 행 중 완료 처리된 행의 `settle_amount`(보류 반영 후 실입금, 계좌+충전금 상계 합) | (차) 보통예금 / (대) 네이버페이 미수금. 충전금 상계 행(CHARGE_AMT)은 선급금 — 입금 채널 카드에서 분리 확인 |
| 정산 예정액 | 같은 창 안 미완료 행의 `settle_amount` | 미입금 잔액 보조부. 건별 "정산 예정 금액"과 **다른 값** |
| 수수료 합계 | `commission_settle_amount`(음수) | (차) 지급수수료 / (대) 미수금 |
| 보류·한도 | 창 안 보류(음수)+해제(양수) **순증감** | 발생·해제를 펼침 상세(부호 원본)에서 따로 집계. 누적 잔액은 화면에 없음(현재 −129,757,200) |
| 워터폴 "정산 금액" | 완료액 + 예정액 | 완료액 타일과 다름 |
| 대사 배너 "일별 합계 vs 건별 합계" | `pay_settle_amount`(결제 정산 금액) 만 | 입금액 대사가 아니라 적재 검증 |
| 원장 그룹 합·건별 CSV/시트 "정산 예정 금액" | `settle_expect_amount`(수수료 차감 후·보류 전) | 매출채권 순액 보조부. Σ = 일별 pay+commission |
| 시트 "정산기준금액" | `pay_settle_amount` | 미수금 총액 인식 기준(부가세 매출과 기준일 축에서 일치) |
| 전기 대비 % | 같은 **일수** 직전 구간(달력 전월 아님), 기본 창은 미실현 14일 포함 | 월 보고에 쓰지 말 것(C-01 수정 전) |
| 예외 N건(스트립·배지) | 상한 50/갈래 적용 뒤 표시 건수 | 모집단은 매칭률 타일 "FOMS 미연결 N건" |
| 부가세 총매출 | 결제 정산액(기준일 축) 부가세 포함가, 공급가·세액 없음 | 세액은 ×10/110 손계산(§6-2) |
