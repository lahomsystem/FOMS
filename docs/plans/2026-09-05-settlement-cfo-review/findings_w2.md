# W2 완전성(B)·운영 신뢰성(F) — findings (2026-09-04 착수, 2026-09-05 재개 완료)

워크트리 `C:/tmp/foms-s-settle-cfo`(base origin/deploy 7100e2aa1). 읽기 전용. 스테이징 DB 배치 2회(본 배치 `w2_staging_batch.py` 09-04 07:44 UTC, 경계 보조 `w2_boundary.py` 09-05), 운영 DB 배치 **1회**(`w2_production_batch.py`, 재실행 없음, 질의 15개·연결 1개·`postgresql_readonly=True`), 스테이징 API `?view=strip` 1회(`w2_strip.py`). 버튼·POST·브라우저 사용 없음. 비밀·URL 원문 없음.

> 스테이징 스냅샷은 09-04 07:44 UTC 기준(run 15 까지). 09-05 보조 질의에서 스테이징이 run 20(09-04 20:38 UTC)까지 전진한 것을 확인했으나 본 배치 숫자는 다시 뽑지 않았다(같은 질의 재호출 금지).

## 1. 축별 판정

| 축 | 판정 | 근거 한 줄 |
|---|---|---|
| B 완전성 | **WARN** | 미해제 보류 18행 **-129,757,200원**(스테이징=운영 동일, 분할 해제 1건 확인) + 확정 구간(예정일+30일) 밖 정정 미반영 리스크가 문서·화면 어디에도 공시되지 않음. 날짜 구멍·창 경계·coverage 빈 달은 결함 없음(NOT-A-DEFECT) |
| F 운영 신뢰성 | **WARN** | stale 36h 임계값이 일 1회(05:30) 스케줄 대비 커서 누락 다음 날 근무시간 전체가 '정상'으로 보임 · 큐 부재/enqueue 실패를 '이미 대기 중'으로 말함 · FAILED 실행의 반쯤 적재된 창이 커밋되고 FAILED 자체는 예외 큐에 안 실림 · 05:30 창 안 5회 연속 실행(93호출×5). 캐시 경로는 PASS |

음성 대조군(각 축 PASS 항목):
- B-1 구멍 술어 생존: 주말 구멍 70일(토35·일35)·공휴일 구멍 9일이 잡혔고, 주말·공휴일에 행이 있는 날 0 (`w2_staging.json b1_gap`, `w2_production.json b1_gap` 동일).
- B-3 창 분할: `end<start → []`, `size 0·음수 → 1일 창`(자기 보호) 통과 (`w2_windows.json` b.end_lt_start_empty·b.size0_self_protect).
- B-4 coverage: coverage_from 이전 daily 행 0(스테이징 2025-10-01·운영 2026-01-01 모두 0), 그 구간엔 배너 술어 `from < coverage_from` 참(`channel.js:2128`).
- F-3 실패 경로 대조군: 최신 OK run(스테이징 15·운영 23) 뒤 워터마크 `last_status='OK'·last_error=null`(`w2_*.json f3_runs`).
- F-4 캐시 대조군: SW 가 캐시하는 경로는 `/static/*.css|js`(`static/sw.js:88-92 staticCacheFirst`)·이미지(`:100-102`) — 술어가 살아 있고 `/api/settlement/channel` 은 어느 분기에도 안 걸린다(`:79-107`).

## 2. 발견 목록 (심각도 순)

### W2-B-01 · WARN · 완전성 — 확정 구간(예정일+30일) 밖 정정은 백필 없이는 영원히 안 들어오는데 문서·화면이 리스크를 말하지 않는다
- 현상: 일반(SCHEDULE/MANUAL) 실행은 `settle_expect_date + 30 < today` 인 날짜를 건너뛴다. 네이버가 그 날짜의 행을 뒤늦게 정정(금액 변경·행 삭제·해제 소급 기입)하면 다음 백필까지 옛 스냅샷이 남는다.
- 근거(코드): `foms/services/integrations/naver_commerce/settle_sync.py:442-444 skip_day` · `:544-555 is_finalized` · `:350-383 replace_partition`(창 안 파티션만 교체) · `:805-816 _sync_window`(skip_day 로 case/commission 도 건너뜀).
- 근거(문서): `docs/plans/2026-09-02-naver-settlement-contracts.md:72` 는 "확정 구간 제외: … 백필이 아닌 한 재조회하지 않는다" 로 **동작만** 기술, 리스크·운영 절차(월 마감 전 백필) 언급 없음. `-v1.1-contracts.md`·`ledger.md`·`2026-09-03-settlement-followup-brief.md` 에 '확정/30일/소급' 리스크 서술 0건(grep).
- 근거(화면): `static/js/settlement/channel.js:1010` `'확정 구간 ~' + sync.final_before` 한 줄뿐 — "이 날짜 이전은 다시 읽지 않는다" 는 뜻이 어디에도 없다.
- 음성 대조군: `tests/services/integrations/test_naver_settle_sync.py:536-550` 일반 실행의 case 최소 조회일 = today-31(`min(normal_days) == "2026-08-03"`), 백필은 6/1 조회 — 술어가 살아 있다. retro_changes 는 최근 15 run 전부 0건(`w2_staging.json b2_retro`) — 창 안 소급 변경이 없었다는 뜻이지 창 밖을 봤다는 뜻이 아니다.
- 실측: 확정 구간(<2026-08-05) 안에 **미해제 보류 4행 -10,378,102원**(7/30 -1,690,300 · 7/31 -3,945,183 · 8/3 -3,248,622 · 8/4 -1,493,997; `w2_staging.json b2_holdback.unpaired_list`, 운영 동일). 이 4일 파티션의 sync_run_id 는 9(백필)·10(9/3 MANUAL)에 멈춰 있고 이후 어떤 실행도 건드리지 않았다(`w2_boundary.json` 8/3 run 9·8/4 run 10).
- 재무 영향: **추정** — 정정 발생 여부는 네이버 측 사실이라 금액 불명. 노출 모집단은 확정 구간 안 미해제 보류 -10,378,102원 + 확정 구간 전체 daily 행.
- 권고(근본): ① 계약 문서에 "확정 구간 리스크 + 월 마감 전 전월 1일부터 [받아오기]" 운영 절차 명문화 ② 화면 '확정 구간' 줄에 부제("이 날짜 이전 정정은 [이 구간 받아오기]로만 반영") ③ 월 1회(익월 1일 05:30) 전월 1일부터 자동 백필 옵션. 노력 S(①②)/M(③).

### W2-B-02 · WARN · 완전성 — 미해제 지급 보류 18행 -129,757,200원, 해제는 분할로도 오는데 화면은 기간 합만 보여 잔액을 알 수 없다
- 실측(스테이징 = 운영 동일, `w2_staging.json b2_holdback`·`w2_production.json b2_holdback`): 보류 음수 21행 -137,882,500 · 해제 양수 4행 +8,125,300 · 같은 금액 1:1 짝 2건 -6,179,400(6/19 -2,410,000 ↔ 8/27 +2,410,000 **69일**, 6/30 -3,769,400 ↔ 7/16 +3,769,400 16일) · 1:1 짝 없음 19행 -131,703,100.
- **분할 해제 발견**: 1:1 짝 없는 양수 2행(7/15 +1,505,900, 7/23 +440,000)의 합 = 1,945,900 = 1/6 보류 -1,945,900 과 정확히 일치 → 190일·198일 뒤 두 번에 나눠 해제. 따라서 실제 미해제 = **18행 -129,757,200**(전부 7/30~8/26, 오늘 기준 9~37일 경과).
- 화면·코드: 커널 `foms/services/settlement_channel.py:551-597 _build_holdback` 은 **조회 창 안** 행의 합만 만들고, `:479 _holdback_of` 가 KPI 타일과 같은 정의 — 누적 잔액·짝 매칭이 없다. `channel.js:1225-1232` 타일 부제는 "일자별 N행 — 눌러서 펼치기". 창 밖(6/19) 보류의 해제(8/27)만 창(8/5~9/18)에 들어오면 +2,410,000 이 '보류 감소' 로 보이나 어느 보류가 풀렸는지는 알 수 없다.
- 30일 창과의 관계: 해제는 **자기 날짜의 새 행**으로 오므로 롤링 창이 잡는다(69일·198일 짝 모두 적재됨) — 해제 행 누락은 없다. 위험은 W2-B-01(옛 파티션 정정)과 "아직 해제 전인지 영영 안 풀린 건지 화면으로 구분 불가" 두 가지다.
- settlement_limit_amount ≠ 0 행: 0(결정 사항 확인, 양쪽 환경).
- 재무 영향: **실측** -129,757,200원(미해제 잔액, 채권 관리 대상). 회계팀은 이 잔액을 화면에서 직접 얻을 수 없다(기간 합을 바꿔 가며 손으로 더해야 한다).
- 권고(근본): 보류 상세 패널에 "적재 구간 전체 누적 잔액" 한 줄 + 같은 금액(분할 합 포함) 짝 표시 + 확정 구간 안 미해제 강조. 재계산이 아니라 저장값 합산·대조다(계약 D-4 저촉 없음). 노력 M.

### W2-F-04 · WARN · 완전성 — FAILED 실행이 반쯤 적재된 창을 그대로 커밋하고, FAILED 자체는 예외 큐에 안 실린다
- 코드: `settle_sync.py:786-803 _drive` 모든 `Exception` → FAILED(403 즉시·429/5xx 는 `client.py:62 RETRYABLE_STATUS`·`:1149-1174` 3회 백오프 뒤 raise·401 은 토큰 재발급 1회 뒤 raise). `:805-816 _sync_window` 창마다 commit(앞선 창은 남는다 — 의도된 설계). 문제는 실패한 창: `:630-660 _sync_settle_daily` 가 창 전체(30일) daily 파티션을 **먼저** 교체하고 `:808-812` case/commission 은 하루씩 → k일째에서 예외가 나면 daily 는 30일치 새 스냅샷·case 는 k-1일까지만 새 스냅샷인 상태로 `:830-849 _finish` 가 `commit()` 한다(FAILED 분기에서도 커밋, rollback 없음).
- 결과: k일 이후 daily↔case 합이 어긋날 수 있다(다음 OK 실행까지, 보통 다음 날 05:30). 예외 큐 `settlement_channel.py:945-968 _run_exceptions` 는 RETRO·COUNT_MISMATCH 만 만들므로 실패는 "합 불일치" 로 간접 표시되고 "동기화 실패" 로는 표시되지 않는다. 헤더 `channel.js:1002 '상태 ' + sync.status` 가 '상태 FAILED' 를 보여주지만 stale 이면 `:1000-1001` stale 문구가 덮는다.
- 테스트: `test_naver_settle_sync.py:455-468 test_failure_is_recorded_and_returned_not_raised` 는 FAILED 기록·`coverage_to` 미전진만 단정 — 부분 적재 파티션 잔존 여부는 검증하지 않는다(사각).
- 실측: FAILED/ABORTED_QUOTA run 스테이징 0·운영 0(`w2_*.json f3_runs.status_counts`), 현재 daily↔case 불일치 일수 0. 대조군: OK 뒤 워터마크 OK/null.
- 재무 영향: **추정** — 실패 창 안 k일 이후 날짜의 일별↔건별 불일치, 금액 불명(실패 미발생).
- 권고(근본): `_drive` FAILED/ABORTED_QUOTA 분기에서 `_finish` 전에 `ctx.session.rollback()`(창 단위 원자성; 앞 창 커밋은 유지) + `_run_exceptions` 에 `SYNC_FAILED` 종류 추가(최신 run 이 FAILED/ABORTED_QUOTA 면 1행). 노력 S.

### W2-F-01 · WARN · 표시 — stale 임계값 36h 는 일 1회 05:30 스케줄 대비 너무 커서, 누락 다음 날 근무시간 내내 '정상'으로 보인다
- 코드: `settlement_channel.py:80 STALE_AFTER_HOURS = 36` · `:398-409 _hours_since` · `:412-441 _build_sync` `stale = (not never) and (age is None or age > 36)`. `channel.js:996-1002` never/stale/ok 세 모드, ok 부제 = `'상태 ' + sync.status`. 워터마크는 `_finish` 에서만 쓰이므로(`settle_sync.py:830-849`·`:865-895`) RUNNING 은 화면에 없다(진행 중 표시 부재).
- 스케줄: `scripts/maintenance/run_naver_settle_sync.py:55 DEFAULT_AT="05:30"`, `:53 DEFAULT_WINDOW_MINUTES=10`, `start.sh:56-59`.
- 계산: D일 05:38 KST OK(실측 `w2_strip.json sync.last_ok_at 2026-09-03T20:38:53Z` = 09-04 05:38 KST) → 워커 사망 → D+1 05:30 실행 누락 → stale 발동 = 05:38 + 36h = **D+1 17:38 KST**. 즉 D+1 05:40~17:38(약 12시간, 근무일 전체)은 하루치가 빠진 채 '최종 동기화 … (N시간 전) · 상태 OK' 로 표시된다. 마지막 성공 기준으로는 36시간.
- 실측: 스테이징 age 11.09h·운영 5.31h(stale false) — 정상 상태 대조군. 테스트 `tests/domains/test_settlement_channel_api.py:433`(never)·`:443`(40h → stale) 계약은 있으나 임계값 자체는 검사 대상이 아니다(실행은 W4).
- 재무 영향: 회계팀 오해 가능(하루치 미반영을 정상으로 읽음). 금액 없음.
- 권고(근본): 임계값을 "스케줄 주기 + 여유"(예 26~28h) 로 낮추거나, `sync.next_due`(직전 05:30 창 종료 시각) 를 내려 "예정 실행을 넘겼다" 로 판정. 노력 S.

### W2-F-02 · WARN · 표시 — 큐 부재·enqueue 실패·중복을 같은 False 로 접어, 화면이 '이미 대기 중인 동기화가 있습니다' 라고 말한다
- 코드: `foms/services/jobs/queue.py:533-535` `if not q: return False`, `:547-549` enqueue 예외 → False, `:536-538` 중복 → False. `get_rq_queue` 는 Redis 연결 실패 시 None(`:36-58`). API `foms/api/cs/settlement_channel.py:283-295 _enqueue` 는 **ImportError 일 때만** None → `:323-325` 503; False 는 200 `queued=False` → `channel.js:2088-2092` `'이미 대기 중인 동기화가 있습니다. 반영을 확인합니다.'` → 60초 폴링 → `:2176` '1분 안에 반영되지 않았습니다…'.
- `queue.py:518-521` docstring 은 "큐가 없으면 False 를 돌려주고 화면이 '지금은 동기화할 수 없다'를 그대로 말한다" 고 적혀 있으나 화면 문구는 그렇지 않다(의도와 구현 괴리).
- 테스트: `test_settlement_channel_api.py:550 test_sync_reports_already_queued_without_lying` 은 중복 False 만 다룬다.
- 재배포 시나리오: 워커가 job 을 `started` 로 잡은 채 죽으면 `_SETTLE_SYNC_ACTIVE_STATUSES`(`queue.py:484-486`, started 포함)·`job_timeout="2h"`(`:541-542`) 때문에 RQ 가 정리하기 전까지 모든 클릭이 '이미 대기 중' 이 된다(추정, 실측 금지).
- 재무 영향: 회계팀 오해 가능(Redis 장애·재배포 중 눌렀을 때 "누가 이미 돌리고 있다" 로 읽음).
- 권고(근본): enqueue 반환을 3상태(queued / duplicate / unavailable)로 나누고 unavailable 은 503 + '지금은 동기화할 수 없습니다'. 노력 S.

### W2-F-05 · WARN · 완전성(가용성) — 05:30 창 안에서 같은 동기화가 5번 연속 실행된다(93호출×5 = 465호출/일)
- 실측: 운영 run 19~23 = 2026-09-04 20:30:59·20:32:59·20:34:59·20:36:59·20:38:59 UTC(05:30~05:38 KST) 전부 SCHEDULE·같은 scope·같은 행수, run 14~18·2~6 도 동일 패턴(`w2_production.json b4_monthly.runs_last40`); 스테이징 run 11~15·2~6 동일(`w2_staging.json`). 워터마크 `per_endpoint.calls` = case 45 + daily 3 + commission 45 = 93/run.
- 코드: `run_naver_settle_sync.py:48-53`(tick 60초·창 10분), `:165-186 _run_loop` 는 창 안 매 tick 마다 실행하고 "오늘 이미 돌았다" 가드가 없다(docstring 은 멱등만 언급).
- 영향: 재무 없음. 네이버 쿼터 소진 위험(`settle_sync.py:446-454 check_quota → ABORTED_QUOTA`, `client.py:61-79` 벌칙성 제한), rev 가 하루 5 씩 뛰어 runs 표·감사 잡음, 한 창에서 소급 변경이 5번 기록될 수 있음.
- 권고(근본): `_run_loop` 에 마지막 실행 날짜를 기억해 창당 1회만 실행. 노력 S.

### W2-B-03 · INFO · 완전성 — 영업일 구멍 9일: 적재 실패 근거 없음, 다만 화면은 '정산 없음' 과 '적재 실패' 를 구분하지 못한다(구조)
- 실측(스테이징=운영 동일): 2026-01-01~09-04 247일 중 행 있는 날 159, 구멍 88 = 주말 70 + 공휴일 9 + **영업일 9**(1/16·3/4·3/20·4/17·5/1·5/29·7/10·7/17·8/13; `w2_*.json b1_gap`). 9일 모두 OK 백필 run(스테이징 7·9, 운영 12) scope 안, 8/13 은 OK 롤링 run 12회 이상이 재조회해도 빈 날. daily↔case 예정일 합 불일치 0일(`f3_runs.daily_vs_case_pay_settle_mismatch_days = []`) → 건별 엔드포인트도 그 날 예정 건이 없다 — 두 엔드포인트가 독립적으로 일치.
- 코드: `settlement_channel.py:484-519 _build_daily` — 창 안 행이 하나라도 있으면 빈 날을 0 으로 채우고(`sums[key] = _ZERO`), 행이 0 이면 `[]`. 구분 신호는 `sync.coverage_*`·`last_ok_at`·`status` 뿐(`:412-441`).
- 판정: 결함 아님(적재 실패 증거 없음). 구조 메모로 남긴다. 네이버 원장 대조는 불가(확인 못 한 항목).

### W2-B-04 · INFO · 완전성 — 배너 술어는 `from < coverage_from` 뿐이지만, coverage 는 OK 실행만 전진시키므로 잘린 백필의 빈 구간이 배너를 피해 가지 않는다
- 실측: coverage 안 달 중 daily 일수 < 영업일 절반 또는 case 0 인 달 = 스테이징 0(2025-10~2026-09 12개월)·운영 0(2026-01~2026-09 9개월)(`w2_*.json b4_monthly.months_in_coverage`). RUNNING 잔류 run(스테이징 8, 운영 10·11)의 scope 는 뒤이은 OK run(9·12)이 같은 scope 로 덮었다.
- 코드: `channel.js:2128` 술어; `settle_sync.py:878-885` coverage 는 `status == "OK"` 일 때만 min/max 전진 → 잘린 백필은 coverage_from 을 못 넓히고 배너가 계속 뜬다. `backfill_from .. today+14` 라 OK 창들은 항상 최근 끝에서 겹쳐 합집합에 구멍이 생기지 않는다.
- 판정: 결함 아님. 남는 구조 사각은 "OK 인데 네이버가 빈 응답을 준 날" 뿐(=W2-B-03).

### W2-F-03 · INFO · 표시 — 폴링 만료 뒤에는 다시 알리지 않는다
- `channel.js:74-77` 10초×6(1분)/백필 60회(10분), `:2150-2183 startRevPoll`, `:2176` '… 분 안에 반영되지 않았습니다. 워커가 밀렸을 수 있으니 잠시 뒤 새로고침하세요.' — 폴링 종료 뒤 워커가 처리해도 화면은 다시 알리지 않는다(재접속 시 헤더 시각으로만 안다). 문구가 정직하므로 결함 아님, 기록만.

### W2-F-06 · INFO · 표시 — 캐시 경로 없음(PASS) + JSON API 에 `Cache-Control: no-store` 부재(하드닝)
- 실측: `w2_strip.json cache_headers` Cache-Control/ETag/Expires/Last-Modified/Age/CF-Cache-Status 전부 null, `Vary: Accept-Encoding, Cookie`. `foms/api/cs/settlement_channel.py`·`foms/services/settlement_channel.py` 에 캐시 데코레이터·ETag·table_version·cache_version 참조 0건(grep). `no-store` 는 `:433` export.csv 만. 프래그먼트 304(`foms/services/common/erp_shell_http.py:43`)는 빈 컨테이너라 숫자와 무관. `static/sw.js:79-107` fetch 핸들러는 `/static/`·`/api/foms/offline/queue`·이미지만 가로챔. 워커 세션 훅 부재는 이 API 가 버전 카운터를 안 읽어 영향 0.
- 하드닝: 응답에 구매자명이 실리는데 SW PII 게이트(`sw.js:218-222 responseForbidsStore`)는 `no-store` 헤더에 의존한다 — 미래에 `/api/` 분기가 추가되면 그대로 캐시된다. `Cache-Control: no-store` 1줄 추가 권고. 노력 S.

## 3. NOT-A-DEFECT (조사했으나 결함 아님)

| 항목 | 이유 |
|---|---|
| RUNNING 잔류 run(운영 10·11, 스테이징 8) | 결정 사항. 실측으로도 그 scope 를 뒤이은 OK run(12·9)이 덮어 빈 구간 0 |
| coverage 합집합(스테이징 2025-10-01·운영 2026-01-01) | coverage_from 이전 daily 행 0(양쪽) → 과소·과대 표시 없음. OK 창은 항상 `today+14` 로 끝나 합집합에 구멍 불가 |
| 28일/30일 창 분할 경계 | `w2_windows.json` 42/42 통과(합집합=iter_days·교집합 0·길이 28/29/56/57·시작=끝·끝<시작 []·size 0/음수 자기 보호·윤년·무작위 200). `settle/daily` startDate 끝 포함은 실측으로 증명: 창 시작일 8/4 행 sync_run_id=10(창 08-04~), 8/5 행 sync_run_id=15(창 08-05~) — 배타였다면 `_sync_settle_daily:648-651` 이 그 날을 비웠을 것(`w2_boundary.json`). 문서 `docs/research/2026-09-02-naver-settlement/01-naver-settle-api-spec.md:149-150` 은 포함 여부 미기재(NOT IN DOCS), `:33` 1개월 제한 → 28일 창 |
| 영업일 구멍 9일 | 적재 실패 근거 없음(W2-B-03). 네이버 원장 대조는 불가 |
| settlement_limit_amount ≠ 0 | 0행(양쪽), 결정 사항 확인 |
| retro_changes 창 밖 검사 | 최근 15 run retro 0건이라 데이터로는 판정 불가, 코드(`skip_day`)+테스트(`:536-550`)로 창 밖을 안 봄을 확인 |
| 워커 적재 뒤 웹 캐시 | API·SW·프래그먼트 어디에도 캐시 경로 없음(W2-F-06) |
| 스테이징 2026-09 daily 합(15,640,441) ≠ 운영(25,327,146) | 동기화 시점 차이(스테이징 스냅샷 09-04 05:38 KST, 운영 09-05 05:38 KST). 정확성은 W1 축 |
| 실패 경로에서 다음 OK 가 자가 치유 | 롤링 창이 같은 구간을 다시 훑어 불일치는 하루 안에 사라진다 — W2-F-04 의 노출 기간을 하루로 제한하는 사실 |

## 4. 확인 못 한 항목

| 항목 | 이유 |
|---|---|
| 영업일 구멍 9일이 네이버 원장에서도 '정산 없음' 인지 | 네이버 API 직접 호출·셀러센터 조회 금지. 두 엔드포인트 일치·OK run 재조회로 간접 확인만 |
| 미해제 보류 18행 -129,757,200원이 실제 아직 보류 중인지 | 네이버 측 사실. 화면·DB 로는 "해제 행 없음" 까지만 |
| 확정 구간 안 정정이 실제로 발생했는지(금액) | 백필 실행 금지(운영 쓰기·큐 점유). 정정 여부는 다음 백필의 retro_changes 로만 알 수 있음 |
| FAILED 부분 커밋의 실측 | 실패 유발(잘못된 토큰 등) 금지. 코드·테스트 근거만 |
| 재배포 중 [지금 동기화] 실측 | 버튼·POST 금지. 코드·테스트 계약으로만 |
| stale/FAILED/never 문구의 실화면 | W4 스크린샷 소관. 코드 문구 인용만 |
| 운영 워커 `FOMS_NAVER_SETTLE_SYNC_ENABLED` 값 | railway 조회 안 함. 다만 운영 runs 가 매일 05:30 KST 에 SCHEDULE 로 도는 것이 확인돼 사실상 켜짐 |

## 5. 결정 재고

없음. (B-4 의 "배너 사각" 은 조사 결과 coverage 가 OK 실행만 전진하는 설계 덕에 실해가 없어 결정 유지.)

## 6. 산출물

- `OUT/findings_w2.md` (이 파일)
- `OUT/w2_staging_batch.py` → `OUT/w2_staging.json` (B-1·B-2·B-4·F-3·F-1, 스테이징 09-04 07:44 UTC)
- `OUT/w2_production_batch.py` → `OUT/w2_production.json` (운영 1회 배치, 질의 15, 09-05)
- `OUT/w2_windows_test.py` → `OUT/w2_windows.json` (B-3, 42/42)
- `OUT/w2_boundary.py` → `OUT/w2_boundary.json` (B-3 startDate 끝 포함 실증, 스테이징 보조 1회)
- `OUT/w2_strip.py` → `OUT/w2_strip.json` (F-1·F-4, strip API 1회 + 응답 헤더)
