# 2026-09-09 워커 정지 헛알림 26건 — 감시자와 게이트가 같은 표를 다른 잣대로 읽었다

> 유형: 관측 결함(데이터 손실 없음) · 상태: 종결 — 운영 반영 + 실측 확인
> 작성 2026-09-09. 사용자 제보(알림 센터 화면)로 시작.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 관측 결함 — 멀쩡한 워커를 "멎었다"고 알림. 실제 큐 정지·데이터 손실 없음 |
| 원인 축 | 하트비트 신선도 예산이 **판정부마다 다르다**. readiness 게이트는 루프가 신고한 tick 간격 x 3 을 쓰고(`foms/services/sidefx_worker.py:626-641`), 정지 감시자는 등록부 상수만 쓴다(`foms/services/worker_watchdog.py:94`) |
| 영향 | 운영 알림 26건 · 수신자 행 52건(2026-09-08 16:19~22:30 KST). 관리자 `upperkill` 26건 중 23건 미읽음. 같은 기간 네이버 취소·반품 긴급 알림이 이 두 문장에 밀렸다 |
| 현재 상태 | SIDEFX `FOMS_WORKER_WATCHDOG_ENABLED=0` 으로 감시자 자체가 꺼져 알림은 멎었다 — **고쳐서가 아니라 감시를 끈 것** |
| 재발 여부 | 신설 기능의 첫 노출. 같은 결함을 readiness 쪽에서는 T16(2026-09-08)에 이미 실측으로 잡아 고쳤는데, 감시자는 옛 경로에 남았다 |

## 2. 증상 (사용자 제보)

`백그라운드 작업이 멈췄습니다` → 15분 뒤 `다시 돌고 있습니다` → 15분 뒤 다시 멎음.
본문은 매번 `NAVER_ORDER_SYNC(15분째)` 또는 `(16분째)`. 다른 kind 는 한 번도 안 나왔다.

## 3. 근본 원인 — 산수

```
운영 WORKER 서비스   FOMS_NAVER_SYNC_INTERVAL_SECONDS = 1800   (루프 tick 30분)
등록부              WORKER_KIND_SPECS[NAVER_ORDER_SYNC].max_heartbeat_age = 900
                    (주석: "기본 간격이 300초 → 3틱")
```

- 루프는 스윕을 끝낸 뒤 하트비트를 남기고 `interval_seconds=1800` 을 함께 신고한다
  (`scripts/maintenance/run_naver_order_sync.py:86-121`).
- readiness 게이트는 그 신고를 읽어 예산을 `max(900, 1800*3)=5400` 으로 잡는다 → 정상 판정.
- 정지 감시자는 신고를 안 읽고 900 을 쓴다 → **t+900 에 "멎음", t+1800 하트비트에 "복구"**.
  15분 왕복은 이 산수의 결과다.

### 운영 실측 (2026-09-09 09:17 KST, 읽기 전용)

```
kind                    | last_heartbeat_at        | 신고간격 | 나이(초)
NAVER_ORDER_SYNC        | 2026-09-09 00:02:41 UTC  | 1800     | 894    ← 6초 뒤 또 오판할 자리
NAVER_AUTO_DISPATCH     | 2026-09-09 00:16:40 UTC  | 60       | 56
RQ_WORKER               | 2026-09-09 00:17:31 UTC  | 405      | 4
(그 외 6종 전부 신선)

worker_watchdog_state = {"stalled": false, "changed_at": "2026-09-08T13:30:35", "stale_kinds": []}
WORKER_STALLED 알림 26건 (2026-09-08 07:19~13:30 UTC) · notification_user_states 52행
```

`changed_at` 이후 판정 흔적이 없다 = 감시자가 그 시각 이후로 안 돌았다(게이트 0).

## 4. 왜 못 막았나

- readiness 쪽은 **같은 결함을 이미 실측으로 잡았다**(원장 T16: "등록부 고정 900초였으면
  헛알림이 났다"). 그때 고친 것은 `ReadinessThresholds.heartbeat_age_limit` 하나뿐이고,
  하루 뒤 신설된 감시자는 등록부 상수를 직접 읽는 옛 경로로 짰다.
- 감시자 계약 테스트 16건은 **전이·행 없음·게이트**를 못박았지만 **예산 산정**은 등록부
  상수를 그대로 쓴다고 가정했다 — 두 판정부가 같은 답을 내는지 아무도 안 봤다.
- 스테이징 간격이 운영과 달라 스테이징에서는 재현되지 않았다.

## 5. 수정

**예산 정본을 하나로 합쳤다.** `foms/services/sidefx_worker.py` 에
`effective_heartbeat_budget(kind, declared_interval)` 를 신설하고, readiness 게이트
(`ReadinessThresholds.heartbeat_age_limit`)와 정지 감시자(`evaluate_worker_health`)가
**그 함수만** 부른다. 규칙은 readiness 가 쓰던 것 그대로 — `max(등록부값, 신고간격 x 3)`.
등록부 상수는 한 개도 바꾸지 않았다(간격은 env 로 바뀌므로 상수를 키우면 다음에 또 어긋난다).

예산은 `max()` 라 **넓어질 수만 있다** — 이 변경으로 새로 stalled 가 되는 kind 는 없다.

| kind | 신고 간격 | 감시자 예산 이전 → 이후 |
|---|---:|---|
| NAVER_ORDER_SYNC | 1800 | 900 → **5400** (헛알림 당사자) |
| RQ_WORKER | 405 | 900 → **1215** (아래 참고) |
| NAVER_AUTO_DISPATCH · NAVER_SETTLE_SYNC · NOTIFICATION_ESCALATION · GEOCODE_SWEEP | 60 | 180 → 180 (변화 없음) |

**받아들인 부작용**: `RQ_WORKER` 정지 감지가 15분 → 20분 15초로 늦어진다. rq 는 놀 때
`dequeue_timeout` 405초를 신고하고 일반 규칙이 그 x3 을 쓴다. 여기서 kind 별 예외를 만들면
이번 사고의 원인인 "규칙 두 벌"이 되살아나므로, 예외 대신 주석·테스트에 사실대로 적었다
(`tools/ops/run_rq_worker.py:13-16`, `sidefx_worker.py:97-100`).

### 변이 검증 (방어를 지우면 red 가 되는가)

```
$ (effective_heartbeat_budget 에서 `if declared_interval: return max(base, declared*3)` 제거)
FAILED tests/domains/test_worker_watchdog.py::test_declared_interval_widens_the_watchdog_budget
FAILED tests/domains/test_worker_watchdog.py::test_rq_worker_production_declared_interval_sets_the_budget
FAILED tests/domains/test_sidefx_readiness_kinds.py::test_declared_interval_sets_the_budget
FAILED tests/domains/test_ops_worker_heartbeat_endpoint.py::test_declared_interval_widens_the_budget
4 failed, 50 passed          ← 두 판정부의 계약이 같은 변이에 함께 red = 진짜로 한 함수를 부른다

$ (worker_watchdog.py 의 `age >= 예산` 을 `age > 예산` 으로)
FAILED tests/domains/test_worker_watchdog.py::test_rq_worker_production_declared_interval_sets_the_budget
1 failed, 20 passed          ← 경계 단언이 겹치지 않고 정확히 한 건만 잡는다

$ (원복 후) 109 passed · import app -> APP_OK
```

## 6. 남은 것

- **감시자 게이트가 아직 0 이다.** 배포 후 SIDEFX `FOMS_WORKER_WATCHDOG_ENABLED=1` 로
  되돌려야 감시가 살아난다. 되돌린 뒤 `system_settings['worker_watchdog_state'].checked_at`
  이 1~2분 안쪽인지로 확인한다(그 checked_at 기록은 deploy `3eb0f1c86` 에 있고 운영 미승격).
- **진짜로 멎어도 최대 90분 침묵**(NAVER_ORDER_SYNC 간격 1800 x 3). 올바른 방향은 예산 축소가
  아니라 하트비트 주기 분리 — 루프가 "일하는 주기"와 "살아 있다고 말하는 주기"를 나눠 신고하면
  예산이 자동으로 3분대가 된다. 별도 과제.
- **push 본문이 사건을 말하지 않는다.** `push_sender.py` 의 `_generic_title` 에 WORKER_STALLED
  분기가 없어 제목 "새 알림"·본문 "확인이 필요한 새 알림이 있습니다"로 나갔다. 복구 알림도
  P1 push 로 나가고, 비긴급 알림엔 tag 가 없어 OS 알림이 묶이지 않는다.
- **감시자 push 는 `FOMS_WEB_PUSH_ENABLED` 검사를 안 거친다**(rq 경로에만 있다).
- **이미 쌓인 헛알림 26건**: 삭제하지 않는다(사고 증거). 정리한다면 `archived_at` UPDATE 만,
  조건은 `notification_type='WORKER_STALLED'` + 사고 창. 기존 벌크 엔드포인트는 유형 필터가
  없어 정상 알림까지 처리하므로 그대로 쓰면 안 된다.
- **일일 HTTP 판정부**(`foms/api/ops_worker_heartbeat.py:71-105`)는 하트비트 나이만 보고
  `oldest_lag_seconds`·`dead_count` 를 안 읽는다 — CLI 는 not-ready 인데 워크플로는 "전부 신선"
  이라 말할 수 있다. 같은 계열(판정부마다 보는 축이 다름)의 다음 자리다.

## 7. 후속 (2026-09-09 같은 날 처리, deploy `80849d3af`)

같은 조사에서 나온 3건을 이어서 고쳤다(운영 승격은 아직).

1. **push 가 사건을 말하지 않았다** — `_generic_title` 에 분기가 없어 제목 "새 알림"·본문
   "확인이 필요한 새 알림이 있습니다" 로 20건이 쌓였다. `WORKER_RECOVERED` 유형을 신설해
   제목·본문을 가르고, 두 유형이 고정 tag `foms-worker-health` 를 공유해 배너가 쌓이지 않고
   **교체**된다. 복구는 `renotify=False` + `vibrate=[]` 로 조용하다(`renotify=False` 만으로는
   무음이 아니다 — 사람이 멎음 배너를 이미 지웠으면 복구가 새 알림이 되어 진동한다).
   감시자 push 경로가 `FOMS_WEB_PUSH_ENABLED` 를 우회하던 것도 발송 함수 최상단에서 막았다.
2. **정지 감지 90분 → 최대 16분** — 일하는 주기(스윕 1800초)와 살아 있다고 말하는 주기(60초)를
   분리했다. 잠을 60초로 쪼개 조각마다 하트비트를 남기고 조각은 tick 을 신고한다. 넓은 예산이
   필요한 자리는 스윕 **앞**이다 — 뒤에 두면 재배포 직후 밀린 구간을 따라잡는 첫 스윕이
   예산 900 으로 방치돼 이 사고가 되살아난다. 네이버 HTTP 호출은 한 번도 늘지 않는다.
3. **Sentry 배선이 한 벌이 아니었다** — 조사 중 애초 전제가 틀린 것을 확인했다. 루프 3종은
   `from app import app` 로 이미 붙어 있었고 진짜 빈 구멍은 `run_rq_worker` 하나였다. 문제는
   러너마다 방식이 달랐다는 것이고(사설 복제본 2벌, 그중 하나는 env 이름을 문자열로 박아
   정본 일치 계약 밖), 전 러너가 공용 게이트를 진입 함수에서 부르도록 모았다.

부수로 닫은 것: `pre_push_smoke` 큐레이션에 워커 배선 테스트 4종 등재(이번 CI red 3종이 전부
로컬 초록·CI 빨강이었다) · 500줄 래칫에 걸린 테스트 2개 분할 · Windows 시계 분해능(약 15.6ms)
때문에 반쯤 빨개지던 `test_a_second_tick_updates_the_same_heartbeat_row` 를 시계 주입으로 종결.
