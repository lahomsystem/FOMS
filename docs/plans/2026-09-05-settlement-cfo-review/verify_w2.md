# VW2 — 워커 w2(완전성 B·운영 F) 반박 검증 (2026-09-05)

워크트리 `C:/tmp/foms-s-settle-cfo`(HEAD 7100e2aa1)에서만 코드 읽기·pytest. 읽기 전용: 스테이징 DB 2회(`vw2_sql.py staging`·`vw2_retro_sql.py`), **운영 DB 1회**(`vw2_sql.py production`, 질의 11, `postgresql_readonly=True`), 스테이징 API GET 1회(`vw2_api_probe.py`, 로그인 302 → `GET /api/settlement/channel` 2회, 버튼·POST 없음). 재현 pytest `vw2_repro_test.py` **7 passed**(`vw2_repro_pytest.txt`). 비밀·URL 원문 없음. 워크트리 무편집(git 명령 0).

## 1. FAIL·WARN 판정표

| ID | 워커 심각도 | 판정 | 심각도 재고 | 재무 영향 종류 |
|---|---|---|---|---|
| W2-B-01 확정 구간 밖 정정 미반영 리스크 미공시 | WARN | **CONFIRMED** (근거 보강) | 유지 | 추정 |
| W2-B-02 미해제 보류 18행 -129,757,200 | WARN | **CONFIRMED** (독립 재계산 일치) | 유지 | 실측(합계)·해제 여부는 추론 |
| W2-F-04 FAILED 가 반쯤 교체된 창을 커밋 | WARN | **CONFIRMED** (실행 재현) | 유지 | 추정(실패 미발생) |
| W2-F-01 stale 36h | WARN | **CONFIRMED** (실행 재현) | 유지(완화 사실 병기) | 없음 |
| W2-F-02 큐 부재=이미 대기 중 | WARN | **CONFIRMED** (실행 재현) | 유지 | 없음 |
| W2-F-05 05:30 창 5회 실행 | WARN | **CONFIRMED** (시뮬·양쪽 환경 3일치) | 유지 — 실해는 신규 W2-F-07 로 분리 | 없음 |

### W2-B-01 — CONFIRMED
- 코드 재독: `settle_sync.py:442-444 skip_day`, `:544-555 is_finalized`(`day+30 < today`), `:653-660 _sync_settle_daily` 와 `:805-816 _sync_window` 가 확정일을 건너뜀. 일반 실행의 창 자체가 `today-30`부터라 그 앞 날짜는 애초에 조회도 안 된다.
- 실측(양쪽 환경, `vw2_staging.json`·`vw2_production.json` `partition_runs_0729_0807`): 07-29~08-03 파티션 sync_run_id = 백필 run(스테이징 9·운영 12, 09-03), 08-04 = 09-03 MANUAL, 08-05 = 09-04 05:38 KST run, 08-06~ = 09-05 05:38 run. 즉 오늘(09-05) 기준 08-05 이전은 그 뒤 어떤 실행도 건드리지 않았다. `is_finalized(08-05)=True, (08-06)=False`(`vw2_windows_probe.txt`).
- 문서 재확인: `contracts.md:72` 는 동작만. **워커가 안 쓴 근거 추가**: `docs/research/2026-09-02-naver-settlement/01-naver-settle-api-spec.md:8·:295·:343` — 네이버 공식 Discussion #3123 실사례(정산건이 뒤에 다른 정산일로 옮겨감)·#3674("변경 가능성 낮음" 이지만 롤링 재조회 권장, **완결 시점 API 미제공**). 화면의 "확정 구간 ~08-06"(`channel.js:1010`)은 네이버가 준 확정이 아니라 FOMS 가 정한 30일 가정이다 — 리스크 미공시가 더 무겁다.
- 반증 시도: "실데이터에 창 밖 정정이 있었나" — 백필 run(스테이징 9, 운영 12)이 이미 적재된 1~8월을 재조회했을 때 retro 0. 다만 그 간격은 3시간(9 vs 7)·1일(12 vs 1)이라 반증력이 약하다. 판정 유지.
- 재무 영향: 추정(정정 발생은 네이버 측 사실).

### W2-B-02 — CONFIRMED
- 독립 재계산(`vw2_sql.py` — 1:1 짝 + 고아 양수 행 부분합 탐색 k≤3): 음수 21행 -137,882,500 · 양수 4행 +8,125,300 · 1:1 짝 2(6/19↔8/27 69일, 6/30↔7/16 16일) · 분할 짝 1(1/6 -1,945,900 ↔ 7/15 +1,505,900 + 7/23 +440,000) · **남은 고아 양수 0** · 미해제 **18행 -129,757,200(07-30~08-26)** — 스테이징=운영 동일, 워커 숫자와 원 단위 일치. 전기간 순합 -129,757,200 = 미해제 합(짝이 정확히 상쇄됨 → 해제가 별도 양수 행으로 온다는 워커 모델과 정합).
- 코드: `_build_holdback:551-597` 조회 창 합만, `_holdback_of:479` KPI 동일 정의, 누적·짝 없음 — 재확인. API 실측: 예외 큐 `HOLDBACK` 14행(기본 창)·17행(08-01~09-19) — 창을 바꾸면 수가 바뀐다(`vw2_api_exceptions.json`), 잔액은 어디에도 없다.
- 반증 한계: 건별(case) 테이블에 보류 컬럼·settleType 이 없어(`models.py:3714-3771`, 연구 문서 settleType 7종에 HOLDBACK 없음) 상품주문 단위 짝 매칭은 불가. "18행이 아직 보류 중" 은 "해제 행이 아직 없다" 까지가 실측이다.
- 재무 영향: **실측** -129,757,200(DB 합). 미해제 여부는 추론.

### W2-F-04 — CONFIRMED (실행 재현)
- `vw2_repro_test.py::test_failed_run_commits_half_replaced_window`: 2일 창에서 2일째 case 조회가 예외 → run FAILED, 결과 `DAILY {09-01: run2, 09-02: run2} CASE {09-01: run2, 09-02: run1} COMM 동일` — daily 는 창 전체 새 스냅샷(900000), case/commission 은 1일째만 새 스냅샷인 채 **커밋**됐다. 워터마크 `last_status=FAILED`. 예외 큐 종류는 `{'RETRO'}` 뿐(금액을 바꿨기 때문), `SYNC_FAILED` 류 없음.
- 코드: `_drive:786-803` → `_finish:830-849` `commit()`(FAILED 분기 rollback 없음), `_run_exceptions:945-968` RETRO·COUNT_MISMATCH 만.
- 실측: FAILED/ABORTED_QUOTA run 양쪽 0(`vw2_*.json runs.status_counts`). 재무 영향 추정.

### W2-F-01 — CONFIRMED
- `test_stale_flag_is_false_thirty_hours_after_last_ok`: 30.0h·35.9h → stale False, 36.1h → True. 05:38 성공 뒤 다음 05:30 누락 시 D+1 17:38 KST 까지 dot=ok·부제 '상태 OK'(`channel.js:996-1002`).
- 완화 사실(워커 미기재): 헤더 굵은 글씨가 `'최종 동기화 <시각> (30시간 전)'` 을 항상 보여준다(`agoText:377-383`, 48h 미만은 시간 단위). 경과 시간은 보이나 "일 1회 05:30" 이라는 기준이 화면에 없어 30시간이 비정상인지 읽을 수 없다 → WARN 유지.
- 지금 값(`vw2_*.json watermark`): 스테이징 age 5.67h·운영 5.70h, 둘 다 stale False(대조군).

### W2-F-02 — CONFIRMED (실행 재현)
- `test_queue_absent_and_enqueue_error_both_return_false`: `get_rq_queue()=None`·`enqueue` 예외·중복 세 경우 모두 False. `test_api_maps_queue_absent_to_200_already_queued`: 큐 None 인데 `POST /sync` → **200 `{'queued': False}`**(503 아님) → `channel.js:2092` '이미 대기 중인 동기화가 있습니다' 분기. `queue.py:518-521` docstring("지금은 동기화할 수 없다")·API docstring(`settlement_channel.py:305-306` "queued False = 이미 큐에 있다")과 구현이 셋 다 다르다.

### W2-F-05 — CONFIRMED
- `test_loop_window_runs_five_times_with_60s_run_and_60s_tick`: `in_window` 로 시뮬 → `05:30:59, 05:32:59, 05:34:59, 05:36:59, 05:38:59` 5회 = 운영 run 19~23 timestamp(20:30:59 … 20:38:59 UTC)와 초 단위까지 일치. 소스에 `already_ran` 가드 없음 — 같은 패턴의 `run_naver_auto_dispatch.py:140-141` 에는 있다(비교군).
- 실측 3일치(`vw2_*.json runs.schedule_runs_per_kst_day`): 09-03·09-04·09-05 KST 각 5회, 양쪽 환경 동일. `start.sh:53` 주석 "하루당 … 100회 안팎" 대비 실제 465회.
- 실해는 아래 W2-F-07 로 분리(재무 없음·쿼터 추정 대신 **화면 손실 실측**).

## 2. INFO 항목 확인(반박 의무 없음, 표본만)
- W2-B-03 영업일 구멍 9일: 재확인 — 그 9일에 case 0행·commission 0행, 대조군 다음 영업일(01-19: 61행, 08-14: 11행)은 있음(`vw2_*.json b1`). 결함 아님 유지.
- W2-B-04 coverage OK 전진: `_write_watermark:878-885` `if status == "OK"` 재독 + 기존 테스트 `test_failure_is_recorded…:455-468`(coverage_to None) — 유지.
- W2-F-06 캐시 없음: 아래 PASS 프로브 참조.

## 3. PASS 거짓 초록 검사(pass_probes)
| 축 | 프로브 | 결과 |
|---|---|---|
| B-1 구멍 술어 | 2026-01-01~09-04 구멍 재집계 + 영업일 구멍 9일의 case/commission 행 수 + 다음 영업일 대조군 | 88/247 양쪽 동일, 9일 case 0·commission 0, 대조군 61·11행 → 술어 생존, PASS 유지 |
| B-3 창 분할 | `split_windows` 직접 호출: 실 창(08-06~09-19) 30/28일, 정확히 28·29·56일, 하루, 역순, 46일 daily 미분할 대조군 | 합집합=iter_days·겹침 0·연속, 역순 [], 46일은 [28,18] 로 분할(미분할이면 네이버 400) → PASS 유지 (`vw2_windows_probe.txt`) |
| B-4 coverage | 코드 `:878-885` + 재현 테스트에서 FAILED 뒤 `last_status=FAILED` | OK 만 전진 확인, PASS 유지 |
| F-3 대조군 | 최신 run OK 뒤 워터마크 | 스테이징 rev 19·운영 rev 21 모두 `last_status OK, last_error null` |
| F-4 캐시 경로 | (1) 세션 identity map 잔존 경로: API 는 `get_db()`(`foms/api/cs/settlement_channel.py:185,231,419`) → `teardown_appcontext(close_db)`(`foms/platform/http.py:387`, `db.py:93-102` `db.close()`) 로 요청마다 정리 (2) SW: `/api/settlement/channel` 은 `sw.js:82-107` 세 분기(`/static/`·offline queue·이미지 정규식) 어디에도 안 걸림 (3) 라이브: 워커 프로브 rev 14(09-04) → 내 프로브 rev 19(09-05) 로 전진 | 캐시 경로 없음 PASS 유지 |
| F-1 대조군 | `_build_sync` 36.1h → stale True | 임계값 술어 생존 |

## 4. 신규 발견
### W2-F-07 · WARN · 완전성 — 05:30 창 반복 실행이 소급 변경(RETRO) 예외를 화면에서 지운다 — 스테이징·운영 **오늘 실측**
- 실측: 스테이징 run 16(09-05 05:30:03 KST, 창의 첫 tick) `retro_changes` 3건 — `naver_settle_daily` 09-07 524,535→10,211,240 · `naver_settle_case` 09-07 1행→30행(550,000→10,899,040) · `naver_settle_commission` 09-07 2행→65행(`vw2_staging_retro.json`). 이어진 run 17~20 은 retro 0. 운영도 같은 창 첫 run 19 에 retro 3건, run 20~23 은 0(`vw2_production.json runs.runs_with_retro`).
- 화면: `settlement_channel.py:1182` `_run_exceptions(_latest_run(...))` 는 **최신 1행**(run 20/23)만 읽는다 → 스테이징 API 실측 예외 종류 `{UNMATCHED: 50, HOLDBACK: 14}`, **RETRO 0**(`vw2_api_exceptions.json`, 기본 창·08-01~09-19 둘 다). 재현 `test_repeated_runs_in_one_window_hide_retro_from_screen`: 2회차 retro 1 → 3·4회차 뒤 `_latest_run` 예외에 RETRO 없음, 대조군(2회차 행을 직접 넣으면 RETRO 1행).
- 부가: 오늘 3건은 미래 예정일(09-07)에 건이 늘어난 것이라 "소급 변경(확정 후 값 변동)" 라벨(`:958`)과도 안 맞는다 — 과거 정정과 미래 적립을 구분하지 않아 보여도 잡음이 된다.
- 재무 영향: 없음(측정) — 오늘 건은 미래 적립. 단 과거 파티션 정정이 나도 같은 경로로 사라진다(W2-B-01 과 결합 시 회계팀이 정정을 알 방법이 0).
- 권고(근본): `_run_loop` 창당 1회 가드(`already_ran`, W2-F-05)와 별개로 **예외 큐가 최신 1행이 아니라 "마지막 OK 이후 24h 안 run 전부" 의 retro 를 합치거나**, retro 를 run 표가 아니라 별도 누적 테이블/워터마크에 남긴다. 노력 S(가드)+M(누적).
### W2-F-08 · INFO · 표시 — OK 가 한 번도 없고 FAILED 만 있으면 stale=True 라 "36시간 넘게 갱신되지 않았습니다" 가 '방금 실패' 를 덮는다
- 재현: `test_failed_only_state_is_reported_as_stale_not_failed` — `last_ok_at=None, last_run_at=5분 전, last_status=FAILED` → `_build_sync` `never False, stale True, status FAILED`(`settlement_channel.py:430-441` `age is None → stale`). `channel.js:998-1001` 는 stale 문구가 status 보다 우선하므로 헤더가 '최종 동기화 (방금 전) · 36시간 넘게 갱신되지 않았습니다' 가 된다(문구는 코드 인용 — 실화면 아님, 스테이징·운영은 OK 가 있어 미해당).
- 권고: `age is None and last_status != 'OK'` 를 별도 모드(`failed`)로. 노력 S.

## 5. 워커 재무 영향 실측/추정 구분
- 실측: W2-B-02 -129,757,200(DB 합, 독립 재계산 일치). 나머지 WARN 은 금액 없음 또는 추정(W2-B-01·W2-F-04). 워커 표기와 일치.

## 6. 확인 못 한 항목
- 18행 미해제 보류의 네이버 측 실제 상태(API·셀러센터 조회 금지).
- FAILED 부분 커밋의 운영 실측(실패 유발 금지) — SQLite 레인 재현으로 대체.
- stale/never/failed 문구의 실화면(W4 소관).

## 7. 산출물
`verify_w2.md`(이 파일) · `vw2_sql.py` → `vw2_staging.json`·`vw2_production.json` · `vw2_retro_sql.py` → `vw2_staging_retro.json` · `vw2_api_probe.py` → `vw2_api_exceptions.json` · `vw2_repro_test.py` → `vw2_repro_pytest.txt`(7 passed) · `vw2_windows_probe.txt`
