# 안 닫힌 DB 연결 추적 장치 — 설계 (승인 대기)

작성 2026-11-02. 계기: Sentry `Timeout: 0.1 seconds` (erp_measurement_dashboard, 2026-11-01 23:15:30 UTC).

## 1. 지금까지 확인한 사실

- 운영 web 로그: `sqlalchemy.pool.impl.QueuePool Exception during reset or similar` 가 10-06 ~ 11-01 사이 31건(하루 1건꼴). WORKER·SIDEFX 에는 0건.
- 11-01 건의 스택: `_ConnectionRecord.checkout.<locals>.<lambda>`(weakref 콜백) → `_finalize_fairy` → `rollback()` → psycopg `wait_poll`(간격 `_WAIT_INTERVAL = 0.1`) → gevent `poll` 안에서 `gevent.timeout.Timeout: 0.1 seconds`.
  - 뜻: 어떤 코드가 연결을 꺼낸 뒤 **돌려놓지 않았고**, 나중에 파이썬 쓰레기 수거(GC)가 그 연결을 치우면서 rollback 을 하다가 gevent 문맥이 꼬여 실패했다. SQLAlchemy 는 그 연결을 버리고(invalidate) 끝낸다.
  - `gevent.Timeout` 은 `BaseException` 이라 SQLAlchemy 가 다시 던지고, 그래서 `Exception ignored in` 이 찍힌다.
- 피해: 없음. 같은 요청은 200(브라우저엔 304), 619ms 로 끝났다. 31건 중 30건은 요청 id 가 `[-]` — 요청 밖에서 GC 가 돈 것이다. **오류가 찍힌 화면은 GC 가 우연히 돈 자리일 뿐 범인이 아니다.**
- 동기 드라이버라 SQLAlchemy 2.0.23 은 GC 회수 때 경고("garbage collector is trying to clean up non-checked-in connection")를 남기지 않는다(비동기 방언만). 그래서 실패하지 않은 회수는 로그에 전혀 안 보인다 — 실제 누수는 31건보다 많을 수 있다.
- psycopg3 전환(09-29) 전 30일엔 1건(09-07)뿐이었다. 전환 뒤 rollback 이 gevent `poll` 을 타면서 GC 중 실패가 보이기 시작한 것으로 본다(누수 자체가 새로 생겼는지는 모른다).

## 2. 로컬에서 배제한 것

스크래치 SQLite(QueuePool) + 요청마다 새 스레드(운영의 요청마다 새 그린렛과 같은 구조) + pool `checkout`/`checkin` 이벤트로 "GC 가 돌려놓은 연결"을 잡는 탐지기를 만들었다. 양성 대조군(스레드 안에서 `db_session.execute` 후 안 닫기)은 잡혔다.

- 매개변수 없는 GET 129개, 매개변수 GET 64개(ADMIN 로그인) — **누수 0**.
- 코드에서 직접 연 Session/connect 는 모두 `with` 또는 `finally: close()/remove()` 가 있다(kakao_alimtalk·measure_same_day·thumbnail·jobs·push_sender).
- 남은 후보: POST/PUT/DELETE, Socket.IO 처리기, 그 밖의 백그라운드 그린렛. 로컬 POST 시험은 실제 알림톡·외부 호출 위험이 있어 하지 않았다.

## 3. 제안 — 운영이 범인 위치를 직접 기록하게 한다

새 모듈 `foms/platform/db_leak_trace.py`, `foms/platform/app_factory.py` 에서 `install_request_phase_profile` 옆에 한 번 설치. 대상은 web 의 주 engine 만.

1. **checkout 이벤트**: `connection_record.info["foms_co"]` 에 (a) `sys._getframe` 으로 거슬러 올라가며 `/foms/`·`/app/` 아래 프레임만 최대 6개(파일:줄:함수), (b) 요청 endpoint 와 요청 id(없으면 `-`), (c) 꺼낸 시각을 남긴다. `traceback.format_stack` 은 쓰지 않는다(비용).
2. **reset 이벤트**(돌려놓을 때만 불린다): 호출 프레임을 2~3칸 올라가 `_finalize_fairy` 를 부른 것이 pool `<lambda>`(weakref 콜백)일 때만 GC 회수로 판정하고, `WARNING [DB-LEAK] gc_reclaimed checkout_at=<프레임들> endpoint=<...> req=<...> held_s=<...>` 한 줄을 남긴다. rollback **전에** 불리므로 rollback 이 실패해도 기록은 남는다.
3. 정상 반납 경로에서는 `info` 키만 지운다. 프로세스당 기록 상한 200줄.
4. 동작은 바꾸지 않는다 — 기록만 한다. 끄는 스위치 env `FOMS_DB_LEAK_TRACE=0`.

비용: checkout 한 번에 프레임 몇십 개 걷기(수십 µs) × 요청당 checkout 수. pre_push_smoke 의 성능 가드로 확인한다.

## 4. 시험

- 단위: 스레드 안에서 안 닫은 세션 → GC 후 `[DB-LEAK]` 1줄, 정상 `close()` → 0줄(음성 대조군).
- 정상 경로 회귀: 기존 tests/domains·contracts 그대로.
- `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1`.

## 5. 이후

deploy → production 승격 후 일주일 동안 운영 로그에서 `[DB-LEAK]` 을 모은다. 위치가 나오면 그 자리를 `with`/`finally` 로 고치는 근본 수정을 따로 하고, 장치는 남겨 두거나(재발 감시) 걷어낸다.
