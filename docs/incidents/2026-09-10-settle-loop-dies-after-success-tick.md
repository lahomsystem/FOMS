# 2026-09-10 정산 동기화 루프가 매일 05:31 성공 직후 죽었다 — 하트비트 조립 한 줄이 예외 가드 밖에 있었다

> 유형: 관측 결함 + 루프 정지(정산 데이터 손실 없음 — 정기 실행 자체는 매일 OK 로 끝났다) · 상태: 수정 반영 진행 중
> 작성 2026-09-10. 운영 `worker-heartbeat-daily` 이틀 연속 red(`NAVER_SETTLE_SYNC` STALE)에서 시작.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 루프 정지. `run_naver_settle_sync.py --loop` 프로세스가 매일 05:30 KST 정기 실행 **성공 직후** 죽는다. 정기 실행은 끝났으므로 정산 데이터는 멀쩡하다. 죽은 뒤에는 다음 WORKER 재배포까지 (a) 하트비트 STALE (b) 그날 다시 실행할 일이 생겨도(FAILED 재시도·수동 `--at` 변경) 루프가 없다 |
| 원인 축 | `scripts/maintenance/run_naver_settle_sync.py:270` `_heartbeat_metadata` 의 `int(stats.get("calls") or 0)`. `run_settle_sync` 가 돌려주는 `stats["calls"]` 는 endpoint 별 **dict**(`rows` 는 table 별 dict) → `TypeError`. 이 호출은 `_run_loop` 의 `try` **밖**이라 예외가 루프를 뚫고 나가 프로세스가 종료한다. `start.sh` 의 `… --json &` 루프에는 감독자가 없다(감시 루프는 RQ 소비자만) |
| 영향 | 09-08·09-09 밤 일일 점검 red 2회. 감시자 push `자동 처리가 멈췄습니다 — NAVER_SETTLE_SYNC(3분째)` 매일 05:32 KST(09-10 실측), 복구 push 는 재배포 때. 재배포가 잦아 낮에는 초록으로 보였다 |
| 현재 상태 | 코드 수정 + 회귀 2건. 운영은 09-10 08:41 KST 재배포(PR #339)로 루프가 다시 살아 있으나 **내일 05:31 에 또 죽는 코드**다 — 그 전에 승격 |
| 재발 여부 | 첫 노출은 `FOMS_NAVER_SETTLE_SYNC_ENABLED=1` 이후 매일. 창 밖 tick 만 검사하던 테스트(`test_settle_sync_loop_beats_outside_its_window`)와 정수 가짜 결과를 넣던 키 계약 테스트가 둘 다 이 모양을 못 봤다 |

## 2. 증상

- `worker-heartbeat-daily`(production) 09-08 21:27Z: `NAVER_SETTLE_SYNC` 나이 **3479초**(예산 180) STALE.
  09-09 21:15Z: 나이 **2760초** STALE. 다른 kind 는 전부 OK.
- 두 나이를 측정 시각에서 빼면 마지막 하트비트가 둘 다 **20:29Z = 05:29 KST** — `--at 05:30` 직전 tick.
- 09-09 05:44Z(14:44 KST) 수동 점검은 `전부 신선`(같은 날 낮 재배포 뒤).

## 3. 근본 원인

```
_run_loop (run_naver_settle_sync.py)
  while True:
      try:
          if should_run(...): result = _sync_once(...)       # 61초, OK
      except Exception: ... capture_exception()             # 여기까지가 가드
      emit_heartbeat(engine, kind,
          metadata=_heartbeat_metadata(ran_now, result, tick))   # ← 가드 밖. int(dict) → TypeError
      time.sleep(tick)
```

`run_settle_sync._finish` 의 반환 `stats` 는 `_SyncContext.stats` 그대로 — 초기값
`{"calls": {}, "rows": {}, "retro_changes": [], "partitions": 0}`. `note_call` 이 endpoint 별로,
`note_rows` 가 table 별로 센다. 러너는 그것을 정수라고 믿었다.

### 운영 실측 (2026-09-10 09:00~09:40 KST, 전부 읽기 전용)

`naver_settle_sync_runs`(SCHEDULE 만):

```
id | started_at(UTC)     | secs | status | calls
35 | 2026-09-08 20:30:35 |  62  | OK     | {'settle/case': 45, 'settle/daily': 3, 'settle/commission-details': 45}
38 | 2026-09-09 20:30:26 |  61  | OK     | (같음)
```

WORKER 이전 배포(`0e7f589a`, 09-09 12:02Z 시작) 로그:

```
2026-09-09T12:03:21Z [naver-settle-sync] started (at=05:30 window=10m tick=60s monthly_backfill=on)
2026-09-09T20:31:30Z Traceback (most recent call last):
  File "/app/scripts/maintenance/run_naver_settle_sync.py", line 315, in _run_loop
  File "/app/scripts/maintenance/run_naver_settle_sync.py", line 270, in _heartbeat_metadata
TypeError: int() argument must be a string, a bytes-like object or a real number, not 'dict'
```

정기 실행 시작 20:30:26Z → 끝 20:31:27Z → 그 tick 의 하트비트 조립에서 사망 20:31:30Z. 이후 이 배포에
`[naver-settle-sync]` 로그 0건. 감시자(`notifications`): `WORKER_STALLED` 20:32:42Z
"NAVER_SETTLE_SYNC(3분째)" → `WORKER_RECOVERED` 23:43:17Z(PR #339 재배포).

### 기각한 가설

"정기 실행이 1시간쯤 걸려 그동안 하트비트가 없다" — 코드만 읽고 세웠다. 실행 표가 61초라고 말해
한 줄로 기각됐다. **실행 표 소요 시간을 먼저 봤어야 한다.**

### 첫 탐침의 거짓 초록

가짜 sync 안의 `time.sleep` 이 러너를 멈추려고 패치한 전역 `time.sleep` 이라 즉시 예외로 끝났고, 그
예외(`Exception` 계열)를 러너의 가드가 삼켜 "sync 중 하트비트 1건" 으로 읽혔다. 정지 신호는
`BaseException` 으로, 가짜 sync 의 sleep 은 패치 전 원본으로 잡아야 한다.

## 4. 수정

1. `_count(value)` — dict 면 값의 합, 숫자면 정수, 그 외 0. `calls`·`rows` 둘 다 이걸로 접는다
   (운영 run 38 → calls 93 · rows 52).
2. `_safe_heartbeat_metadata` — 조립이 터져도 경고 로그 + Sentry 1건 남기고 **같은 키**의 최소 metadata
   로 하트비트를 보낸다. 조립 결함이 생존 신호를 끊을 수 없다.
3. 회귀 2건(`tests/domains/test_loop_heartbeat_wiring.py`): 창 안 성공 tick 을 **실제 반환 모양**으로 1 tick
   → 루프 생존 + 하트비트 `ran=True·status=OK·calls=93·rows=52` / 조립 폭발 → 루프 생존 + 하트비트 +
   Sentry 1건. 키 계약 테스트의 정수 가짜도 dict 로 교정.

## 5. 검증

```
# 수정 전(빨강) — 새 테스트 2건이 운영 증상 그대로 루프를 뚫고 나온다
tests/domains/test_loop_heartbeat_wiring.py::test_settle_sync_loop_survives_a_successful_run_tick
  E TypeError: int() argument must be a string, a bytes-like object or a real number, not 'dict'
  scripts\maintenance
un_naver_settle_sync.py:270: TypeError

# 수정 후(초록)
python -m pytest tests/domains/test_loop_heartbeat_wiring.py -q          -> 24 passed
python -m pytest tests/services/integrations/test_naver_settle_sync.py -q -> 42 passed
스크래치 탐침(운영 run 38 모양으로 1 tick)                                  -> GREEN: loop survived,
    metadata={'interval_seconds': 5, 'ran': True, 'status': 'OK', 'calls': 93, 'rows': 52}
tools/harness/failopen_scan.py --check                                    -> exit 0 (scripts/ 는 모집단 밖)
tests/domains/test_failopen_inventory.py + hygiene + docs registry         -> 33 passed
python -c "import app; print('APP_OK')"                                   -> APP_OK
scripts/ops/pre_push_smoke.ps1                                            -> PRE-PUSH SMOKE PASSED
```

운영 확인은 승격 뒤 **다음 05:31 KST** 가 지나야 가능하다 — `worker-heartbeat-daily` 수동 dispatch 로
`NAVER_SETTLE_SYNC` 나이가 180초 안이고 `metadata.ran=true·calls=93` 인지 본다.

## 6. 재발 방지 — 무엇이 막았어야 했나

- 루프 러너의 **생존 신호 경로는 통째로 예외 가드 안**이어야 한다. "실패가 루프를 죽이면 조용히 꺼진다"
  가 `_run_loop` docstring 의 약속인데 하트비트 줄만 밖에 있었다. 다른 러너 4종(escalation·order_sync·
  auto_dispatch·geocode)은 결과 값이 정수라 지금은 안전하지만 같은 구조(가드 밖 조립)다 — 후속.
- 러너 metadata 테스트는 서비스의 **실제 반환 모양**으로 돌린다. 정수 가짜는 계약이 아니라 소원이다.
- `start.sh` 백그라운드 루프에 감독자가 없다는 사실은 그대로다(RQ 소비자만 감시 루프). 죽으면 재배포까지
  누구도 되살리지 않는다 — 별도 판단.
