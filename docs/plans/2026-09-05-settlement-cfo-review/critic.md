# critic — 정산탭 CFO 감사 "빠진 것 찾기" (2026-09-05)

- 입력: 프롬프트 `docs/plans/2026-09-04-settlement-tab-cfo-review-prompt.md` 축 A~H 31항목 vs `findings_w1..w4.md`·`verify_w1..w4.md`·`ceo_plan.md`.
- 규율: 워크트리 `C:/tmp/foms-s-settle-cfo`(pwd 확인, HEAD 7100e2aa1)에서만 코드 읽기·pytest. 스테이징 DB 는 `postgresql_readonly=True` SELECT 1회(`critic_c1_case_axis.py`). 운영 DB·API POST·버튼·브라우저 사용 없음. 쓰기는 `critic.md`·`critic_*` 만. 비밀 원문 없음.
- 판정 기호: **done** 수행됨 / **weak** 근거 약함(한계 명시) / **missing** 미수행.

## 1. 항목별 수행 여부 (프롬프트 31항목)

| # | 프롬프트 항목 | 판정 | 어디서 | 비고(한계·보강) |
|---|---|---|---|---|
| A-1 | 30일 창 4층 대사(API·DB일별·DB건별·CSV) | done | W1 §3 A-1(rev14 4층 원 단위 일치, rev19 API=DB), VW1 §2 CSV 독립 재파싱 | 양끝 포함 대조군 09-06/08-06 로 대체(09-18 행 0). CSV 는 rev14 만 |
| A-2 | 워터폴 합=완료액 KPI? 대사 허용 오차 0? | weak | W1-A-01(7단=완료+예정), W1 §3 A-2(Decimal 정확 비교·diff 0·COUNT_MISMATCH 0), VW1 CONFIRMED | 양성 대조군(diff≠0→COUNT_MISMATCH) 은 읽기 전용이라 불가. W1 §5-1 "테스트 계약도 없어 보임" → 비평자 직접 확인: **RETRO·COUNT_MISMATCH·`_run_exceptions` 테스트 0건**(§3-1, 새 발견 CRIT-A-01) |
| A-3 | 전기 비교 기간 길이·28/30/31 처리 | done | W1-A-02(2월 −5.4M·5월 +9.3M), VW1 3월 +29.4M 추가, VW1-N-01/N-03 | 세 발견이 한 뿌리(비교 창 정의) — CEO 병합 권고(§4) |
| A-4 | 취소·환급 행 부호(음성 대조군 포함) | done | W1 §3 A-4(3층 부호 동일·일별 대사 포함·NEGATIVE 양성 2025-10-14), VW1 두 번째 취소 건 | 스테이징 settle_type 2종뿐(QUICK_CANCEL·BEFORE_CANCEL·QUANTITY_RESTORE 표본 0) — 한계 명시됨 |
| A-5 | 부가세 daily/case 관계·전표 충분성 | done | W1 §3 A-5(ts=tx+te 315/315·월별 = Σcase pay_settle 11/11), VW1 3개월 추가+축 다르면 다름 대조군 | 세액·공급가 컬럼 부재 → W1 §6 결정 재고 |
| B-1 | 2026-01-01~오늘 날짜 구멍·화면 구분 | done | W2 B-1(88=주말70+공휴일9+영업일9), W2-B-03(구분 불가 구조), VW2 대조군(다음 영업일 61·11행) | 영업일 구멍 9일의 네이버 측 사실은 확인 불가(본질적 한계, 두 엔드포인트 독립 일치로 간접) |
| B-2 | 30일 창 밖 정정 미반영 공시·보류-해제 짝 누락 | done | W2-B-01(문서·화면 미공시), W2-B-02(미해제 18행 −129,757,200·분할 해제 1건), VW2 독립 재계산 일치+Discussion #3123/#3674 근거 추가 | "같은 금액" 부호 규약이 분할 해제를 안 담는 점 → 결정 재고 누락(§4-2) |
| B-3 | 28일 창 분할 경계(음성 대조군) | done | W2 NOT-A-DEFECT(42/42), VW2 프로브(46일→[28,18]) | startDate 끝 포함은 sync_run_id 실증으로 대체(문서 NOT IN DOCS) |
| B-4 | 배너 사각(잘린 백필 빈 구간, 월별 분포) | done | W2-B-04(스테이징 12개월·운영 9개월 빈 달 0), VW2 `:878-885` OK 만 전진 | RUNNING 잔류는 결정 사항 준수 |
| C-1 | "8월 정산액" 3축 금액·조작 경로·문구 충분성 | weak | W1-C-01(예정 34.0M / 완료 34.0M / 결제 93.6M / 기준 168.1M, 원장 합계 줄 없음), VW1 CONFIRMED | **완료일≠예정일 차이 표본이 스테이징에 0** — 비평자 재확인 건별 0/6,303·일별 0/218(§3-7). 운영 미측(W2·W3·VW2·VW3 운영 배치 4개 어디에도 해당 질의 없음, §3-8). 운영 DB 금지라 비평자도 못 채움 |
| C-2 | 월 경계 KST/UTC·경계 하루 실측 | done | W1 §3 C-2(원문↔컬럼 0/218·0/6,303, 08-31/09-01 버킷), VW1 06-30/07-01·컬럼 타입 8개 date | — |
| C-3 | 시차 지표 유무·최소 제안 | done | W1-C-02(평균 18.19일·중앙 17) | — |
| D-1 | 미매칭 금액·aging·붙일 수 있는 비율 | done | W3-D-01(운영 1,480,447,006·90일+ 981,133,199·전화 일치 68.6%), VW3 독립 재현 일치+취소 32행 −14.5M 상계 명시 | — |
| D-2 | 예외 큐 상한 "N건 중 M건" | done | W3-D-02, VW3-D-04(스트립 exception_count 65 vs 526), W4-G-05(실화면) | 세 발견 병합 대상(§4-1) |
| D-3 | 매칭 건 정산액≠출고가·화면 예외 | weak | W3-D-03(스테이징 2주문: #4242 출고가 0 vs 2,830,000), VW3 전제 보정(operations.js:466 노출 최소화 설계) | 운영 매칭 3주문 출고가 미대조(규율)·부분 취소 표본 0. 표본이 극소라 "몇 건" 질문에 사실상 답 못 함 — 매칭 적체 해소 뒤 재감사 필요 |
| E-1 | 계정별 403 표·MANAGER override | weak | W3 E-1(로그인 200/비로그인 302 2행 + 계약 매트릭스), VW3 라우트 6곳 전수·148 passed | 계정이 ADMIN 하나(브리프가 허용한 대체). 비평자 보강: 접근·스트립 계약 38 passed 재실행, export 거부 배우 403 JSON 테스트·페이지 403 매트릭스 테스트 존재 확인(§3-2·3-3) |
| E-2 | 감사 행 행위자·범위·실효 축·라벨 등재 | done | W3-E-02(sync detail 에 실효 창·run 키 없음), VW3-E-06(export detail 에 type/q 없음), 라벨 174~175 | 비평자 보강: backfill_from 은 범위 밖을 400 으로 거절해 기록값=실효값(§3-5). 단 메시지 "(이미 대기 중)" 이 큐 부재에도 남음 → CRIT-E-01 |
| E-3 | 마스킹 CSV·API·화면 + 새는 경로 대조군 | done | W3 E-3(API·CSV), VW3 verbatim 스캔으로 대조군 교체(daily raw 200행 양성) | 화면 층은 "API 값이라 갈음" 이었음 → 비평자가 W4 화면 텍스트 덤프 3개를 verbatim 형태로 스캔 0건·양성 `****4011` 1건(§3-4). 앱 로그(Railway stdout) 경로는 코드 grep 으로만(§3-6) |
| E-4 | 쓰기 경로 0·replace_partition 웹 호출 0 | done | W3 E-4(호출자 settle_sync 내부 4곳·tasks.py·스크립트), VW3 7파일 commit/add grep 0 | — |
| E-5 | 비번 로테이션 해시 대조 | done | W3-E-05(운영 id57 True·is_active false), VW3 재현 True·음성 False | — |
| F-1 | 신선도 표시 구분·임계값 시간 | done | W2-F-01(36h → D+1 17:38 까지 정상 표시), VW2 재현 35.9h/36.1h·완화 사실(경과 시간 표시), W2-F-08(FAILED-only 를 stale 로) | stale/failed/never 실화면은 표본 부재(스테이징 OK) — 코드 문구 인용으로만. 진행 중(RUNNING) 표시 없음 확인 |
| F-2 | 재배포 중 [지금 동기화] 화면 반응 | done | W2-F-02(큐 부재=200 queued False='이미 대기 중'), VW2 재현 테스트 2건 | 버튼 금지 규율대로 코드+테스트 판정. 비평자: API docstring `:305-306` 이 "이미 같은 job" 이라고 적혀 있음을 소스에서 재확인 |
| F-3 | 403/429/5xx → FAILED·예외 큐·부분 실패 롤백 | done | W2-F-04(daily 창 전체 교체 뒤 case k−1일 상태로 commit), VW2 SQLite 재현 | FAILED run 실측 0(양쪽) — 실패 유발 금지 |
| F-4 | 워커 적재 뒤 웹 캐시 경로 | done | W2-F-06 PASS(+`no-store` 부재 하드닝), VW2 identity map·SW 분기·rev 전진 3중 | — |
| G-1 | 라벨 전수→전표 한 줄 | done | W4 §3 표(막힘 4: 완료액 부제·보류 순액·"정산 예정" 동명이의·대사 대상), VW4 라벨 원문 재확인 | W1-A-04 ≡ W4-G-04(병합 §4-1) |
| G-2 | CSV BOM·부호·날짜·슬러그·회계 최소 열 | done | W4 §4(8종 PASS·최소 열 있음/없음 표), W4-G-06(조건 CSV 동일 파일명·오타 type 200 빈 파일), VW4 7월 commission 재확인 | 부재 열(거래처·공급가·세액·계정) → W4 §8 결정 재고 |
| G-3 | 150% SVG 라벨 겹침 실화면 | done | W4-G-07(100% 1쌍)·G-08(150% 6쌍·가로 스크롤·KPI 넘침), VW4 원인 정정(`min-width:auto` 그리드 아이템, 래퍼는 이미 있음) | CEO 는 VW4-G-08a 의 권고를 채택해야 함(워커 권고는 무효) |
| G-4 | 다크 테마 | done | W4 §5(셸 `theme.js:43~48` 데스크톱 light 고정, NOT-A-DEFECT), VW4 확인 | — |
| H-1 | 스트립 예산 6·질의 수·TTFB·EXPLAIN·1년 | done | W4-H-01(스트립 6, TTFB 203/217/135/125ms, case 4종 Seq Scan), VW4 `search_date` 대조군 Index Scan 0.49ms·COALESCE 항등식 | — |
| H-2 | 50줄 위반 수·리터럴 계약 | done | W4-H-03(JS 6/117·커널 0/47·리터럴 7) | 정성 판정 |
| H-3 | 핀 사슬 테스트·pre_push_smoke 서브셋 | done | W4-H-02(서브셋 0건·CI 전체), VW4 핀 값 직접 확인 | 음성 대조군 실행은 편집 금지라 불가(명시됨) |

집계: done 26 · weak 5(A-2·C-1·D-3·E-1 + 결정 재고 누락) · missing 0(항목 자체) / 메타 gap 2(§4).

## 2. 검증 방법·출력 형식 요구 대비

| 요구 | 상태 | 비고 |
|---|---|---|
| pytest 첫·끝 줄 | done | W4 `922 passed … 31.93s`, VW4 `922 passed … 24.30s`, VW3 148 passed, 비평자 38 passed |
| 스테이징 API 응답 저장·표 | done | `w1_api_*.json`·`vw1_api_*.json`·`vw3_api_full_*.json`·`vw4_api.json` |
| 스테이징 DB 읽기(월별·구멍·보류 짝) | done | `w2_staging.json`·`vw2_staging.json` |
| 운영 DB 읽기 전용 "1회" | done(4회) | W2·W3·VW2·VW3 각 1회 = 브리프 §1·§3 허용 범위. 프롬프트 원문의 "1회" 보다 많으니 보고서에 횟수 명시 권고 |
| 실화면 콘솔 0·네트워크 실패 0 로그 | done | `w4_console_kpi.txt`·`w4_console_views.txt`, VW4 §2. VW1 콘솔 400 2건은 자기 조작(from>to) — 결함 아님 명시됨 |
| 스크린샷 scratchpad | done | `w4_*.png`·`vw4_*.png`·`vw1_*_tip.png` |
| 화면 결함 = 실화면만 | done | W3-D-02 는 소스 판정이었으나 VW3 가 `w4_exceptions_text.txt:277` 로 격상 |
| 화면 조작 소유권(W4 만 browse) | 이탈 | VW1 이 gstack browse 로 툴팁 캡처(읽기 전용·조회만). 결과는 유효, 규율 이탈 기록만 |

## 3. 비평자 자기 확인(self_checked) — 워크트리 `C:/tmp/foms-s-settle-cfo`

1. **COUNT_MISMATCH·RETRO 테스트 계약**(W1 §5-1 요청): `grep -rl RETRO tests/` 0 · `COUNT_MISMATCH` 0 · `_run_exceptions` 0. 음성 대조군(다른 kind 는 있음): HOLDBACK 6파일·NEGATIVE 4·UNMATCHED 9·UNLINKED 4·`retro_changes`(동기화 쪽) 2. 유일한 스크린 계약은 `tests/domains/test_settlement_channel_api.py:228` 키 집합 `{daily_total, case_total, diff}` 뿐 → **CRIT-A-01**.
2. **export 거부 배우 403**: `tests/domains/test_settlement_channel_export_api.py:106-118 test_denied_actors_get_403_json_not_a_file`(`_DENIED_ACTORS` 파라미터, MANAGER+CS 포함, Location 헤더 없음 단정)·`:128 test_denied_actor_leaves_no_audit_row`. 페이지: `tests/domains/test_settlement_dashboard_api.py:65 PAGE_URL="/erp/settlement"`·`:249` VIEWER·비 CS/SALES 403 매트릭스. → E-1 은 계정 1개 한계가 남지만 세 표면(페이지·API·CSV) 모두 거부 계약이 코드로 존재.
3. **접근·스트립 계약 재실행**: `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/domains/test_settlement_channel_access.py tests/domains/test_settlement_channel_strip.py -q -p no:cacheprovider` → `38 passed in 0.58s`.
4. **화면 층 계좌 마스킹**: `w4_channel_text.txt`·`w4_channel_text_immediate.txt`·`w4_exceptions_text.txt` 에 저장 형태 verbatim(`[0-9]{3}\*{7}[0-9]{4}`) 0/0/0, 독립 14자리 토큰 0, 양성 대조군 `****4011` 1건(`w4_channel_text.txt:266` "기업은행 · ****4011"). 14자리 부분 일치 140개는 전부 16~17자리 `product_order_id` 안의 부분 문자열(앞뒤가 숫자). → E-3 화면 층 done.
5. **POST /sync 감사 detail 의 backfill_from 실효성**: `foms/api/cs/settlement_channel.py:246-270 _backfill_arg` 는 오늘−400 미만·오늘 초과를 `ValueError`→400 으로 **거절**(클램프 없음) → `:325-331 log_access(... detail={"queued", "backfill_from", "channel"})` 의 값은 요청값=실효값. 단 `:326` 메시지 `"(이미 대기 중)"` 은 `queued` False 이면 큐 부재·enqueue 예외에도 붙는다(`queue.py:533-549`, W2-F-02 인용) → **CRIT-E-01**.
6. **워커 로그 응답 원문 유출 경로(코드)**: `settle_sync.py` logger 6곳(`:292`·`:312` 파싱 실패 값 `%r` 1값, `:440` 소급 변경 dict(table/date/old/new), `:800`·`:848` 예외), `client.py` 15곳(건수·재시도·토큰 캐시·`:1235 _body_text` 는 **오류 응답** 본문만) — 2xx 응답 본문·행 dict 를 통째로 찍는 곳 0. 한계: Railway 로그 실물은 안 열었다.
7. **스테이징 건별 완료일≠예정일**(`critic_c1_case_axis.py` → `critic_c1_case_axis.json`, readonly 1회): `naver_settle_case` 6,303행 중 완료일≠예정일 0(최대·최소 차 0일), `naver_settle_daily` 218행 중 0, 8월 건별 `settle_expect_amount` 예정일 축 155,725,306 = 완료일 축 155,725,306. → 스테이징에서는 "완료일 8월" 이 "예정일 8월" 과 정의상 구분되나 값이 항상 같다. 운영은 미측(아래 8).
8. **운영 배치 4개(w2·vw2·w3·vw3 `_production.json`)에 완료일≠예정일 질의 부재**: 키 grep 결과 `vw2_production.json` 의 `hold_rows_complete_date_null/set` 뿐. 운영 DB 는 비평자 금지라 채우지 못함 → C-1 weak 로 남김(CEO "확인 못 한 항목").

## 4. CEO 판정에 넘기는 메타 gap

### 4-1. 중복 발견 병합(보고서 결함 목록에서 한 항목으로)
| 뿌리 | 발견 ID | 대표로 남길 것 |
|---|---|---|
| 대사 배너 금액 개념 미표기 | W1-A-04(INFO) ≡ W4-G-04(WARN) | W4-G-04(실화면 근거) — 심각도 하나로 |
| 예외 머리 숫자=잘린 길이 | W3-D-02 · VW3-D-04 · W4-G-05 | VW3-D-04(스트립 65 vs 526 실측) + W4-G-05(실화면) 를 한 항목, W3-D-02 는 "표 잘림 미표시" 하위 |
| 비교 창 정의(전기) | W1-A-02 · VW1-N-01 · VW1-N-03 | W1-A-02 를 대표, N-01(차트 전기 인덱스 짝) 은 같은 항목의 두 번째 표면으로 |
| 05:30 창 5회 실행 | W2-F-05 · W2-F-07 | F-07(RETRO 소실 실측) 을 대표, F-05 는 원인 |
| 150% 가로 스크롤 원인 | W4-G-08 · VW4-G-08a | 권고는 VW4-G-08a(`.s-ch-group{min-width:0}`) 로 교체 — 워커 권고(래퍼 overflow) 는 이미 있어 무효 |
| "정산 예정" 동명이의 | W4-G-03 · W1-C-01(금액 개념 3종) | 라벨 축(G) 과 축 전환 합계 부재(C) 로 나눠 두되 교차 참조 |

### 4-2. 결정 재고 절 누락 후보
- **부호 규약 "해제는 같은 금액의 양수 행이 뒤에 온다"** — 실데이터는 분할 해제(1/6 −1,945,900 → 7/15 +1,505,900 + 7/23 +440,000, `findings_w2.md:35`, `verify_w4.md` §4)가 있다. 결정을 뒤집는 것이 아니라 문구를 "같은 금액 또는 분할 합" 으로 넓혀야 짝 매칭 권고(W2-B-02)가 규약과 어긋나지 않는다. W2 §5 는 "없음" 이라 적었고 VW4 만 §4 에 메모 — CEO 가 "결정 재고" 절에 올려야 한다.
- W1 §6(파생 세액)·W3 §6(출고가 병기)·W4 §8(시트 열 3개·F6) 은 각 워커가 이미 올림.

### 4-3. 심각도 재고 후보(전건 WARN, FAIL 0 인 상태)
- W2-F-07 + W2-B-01 결합: 확정 구간 밖 정정은 백필로만 들어오고, 백필·롤링이 잡은 RETRO 조차 같은 창 5회 실행이 화면에서 지운다 → "소급 변경을 회계팀이 알 방법이 0" 은 완전성 축에서 FAIL 후보. 금액 실측은 0(오늘 건은 미래 적립)이라 WARN 유지도 가능 — CEO 판단.
- W3-D-01(미대사 채권 14.8억·90일+ 9.8억) 은 화면이 틀린 게 아니라 없는 것 — WARN 적정하되 "9월 마감 가능 여부" 한 줄 결론의 **조건** 1순위.

### 4-4. 프로세스 메모
- 운영 DB 읽기 4회(W2·W3·VW2·VW3) — 브리프 허용. 프롬프트 원문 "1회" 와 다르니 보고서 §7 에 횟수·시각 기재 권고.
- VW1 의 gstack browse 사용(CEO 설계 §5-1 은 W4 전용) — 조회·툴팁 캡처만, 결과 유효.
- 날짜 경계: 09-04 산출(rev14, 창 08-05~09-18)과 09-05 산출(rev19, 창 08-06~09-19)이 섞여 있다. 보고서 숫자마다 스냅샷을 병기하지 않으면 "같은 창인데 수가 다르다" 로 읽힌다(예: 미매칭 482/511/418, 예외 64/65/125).

## 5. 새 발견(비평자)

### CRIT-A-01 · WARN · 완전성(검출기 무계약) · `_run_exceptions` 의 RETRO·COUNT_MISMATCH 예외 경로에 테스트 0건
- 근거: `foms/services/settlement_channel.py:945-968 _run_exceptions`(RETRO `:947-957`, COUNT_MISMATCH `:958-963`). `grep -rl "RETRO\|COUNT_MISMATCH\|_run_exceptions" tests/` → 0파일. 음성 대조군: HOLDBACK 6·NEGATIVE 4·UNMATCHED 9·UNLINKED 4파일(같은 예외 큐의 다른 kind 는 계약이 있다). 유일한 관련 단정은 `tests/domains/test_settlement_channel_api.py:228` 키 집합.
- 왜 중요: 이 두 kind 는 W2-F-04(FAILED 부분 커밋 → 일별↔건별 불일치)와 W2-F-07/B-01(소급 변경)의 **유일한 화면 검출기**다. 스테이징·운영 실측은 diff 0·RETRO 0 이라 한 번도 발동한 적이 없고, 발동을 보장하는 테스트도 없다(읽기 전용 감사라 양성 대조군을 만들 수 없었음 — W1 §5-1).
- 재무 영향: 없음(측정 0). 권고: 테스트 2건 — (1) daily≠case 합을 만든 픽스처에서 `exceptions` 에 `COUNT_MISMATCH` 1행·`diff` 부호, (2) `naver_settle_sync_runs.stats.retro_changes` 1건인 최신 run 에서 `RETRO` 1행(+`_EXCEPTION_CAP` 잘림). VW2 `vw2_repro_test.py` 의 픽스처를 그대로 옮기면 된다. 노력 S.

### CRIT-E-01 · INFO · 완전성(감사 추적) · 동기화 감사 행 메시지 "(이미 대기 중)" 이 큐 부재·enqueue 실패에도 남는다
- 근거: `foms/api/cs/settlement_channel.py:325-331` `log_access("네이버 정산 동기화 요청" + ("" if queued else "(이미 대기 중)"), ...)` — `queued` 는 `queue.py:533-549` 가 큐 None·enqueue 예외·중복을 전부 False 로 접은 값(W2-F-02). 감사 행 `detail.queued=False` 만으로는 세 원인을 구분할 수 없다.
- 영향: 없음(추적성). W2-F-02 의 화면 문구와 같은 뿌리이나 표면이 감사 로그다 — 장애 뒤 "누가 언제 동기화를 못 눌렀나" 를 감사로 복원할 수 없다. 권고: W2-F-02 의 3상태 반환과 함께 메시지·detail 에 `reason`(duplicate/unavailable) 기록. 노력 S.

## 6. 산출물
- `critic.md`(이 파일) · `critic_c1_case_axis.py` → `critic_c1_case_axis.json`(스테이징 readonly 1회).
