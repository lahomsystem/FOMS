# 워커 관측 후속 3건 — 워크플로 브리프 (2026-09-09)

앞선 헛알림 근본 수정(production `26e9f8638`)에서 함께 드러난 것들. 사용자가 3건 모두 진행 승인.
worktree `C:\tmp\foms-s-wdflap`, 브랜치 `session/wdflap`(base `origin/deploy`).

## A. 휴대폰 알림이 사건을 말하지 않는다 (worker_push)

- `foms/services/notifications/push_sender.py:154-171` `_generic_title` 에 `WORKER_STALLED`
  분기가 없어 제목이 `새 알림`, 본문이 `확인이 필요한 새 알림이 있습니다.` 로 나간다
  (`_build_payload` 174-195). 어젯밤 그 무내용 push 가 20번 쌓였다.
- **복구 알림도 P1 push 로 나간다.** 멎음·복구가 같은 `notification_type`(`WORKER_STALLED`)이라
  `_should_push`(124-128)가 둘을 구분하지 못한다.
- 비긴급 알림엔 `tag` 가 없어(189-195, `static/sw.js:373`) OS 알림이 묶이지 않고 하나씩 쌓인다.
- 감시자 push 경로는 `send_push_for_notification` 직접 호출이라 `_web_push_enabled()`(82행)
  검사를 안 거친다 — rq 경로(`enqueue_push_for_notification`:436)에만 있다. 플래그가 꺼져도 나간다.

**방향(계약 초안)**: 복구 알림에 별도 `notification_type` 을 준다(예 `WORKER_RECOVERED`).
그러면 P1 집합에 멎음만 넣어 복구는 화면에만 남길 수 있고 제목도 갈린다. 신설 유형이
알림 센터·필터·아이콘·감사 라벨 어디에 등재돼야 하는지 **먼저 전수 조사**하고(등재 누락은
무음 결함이다) 빠짐없이 넣어라. 등재처가 정말 없으면 없다는 것을 근거(grep 출력)로 보여라.
push 본문에 고객명·주문번호·사유를 넣지 않는 기존 규율은 그대로 지킨다(인프라 사건이라
kind 이름과 몇 분째는 민감정보가 아니다).

## B. Sentry 배선 빈 구멍 (loop_sentry)

`init_sentry_once` 호출처가 SIDEFX outbox 하나뿐이다(실측):

```
scripts/maintenance/run_naver_order_sync.py        init_sentry_once=0 capture_exception=1
scripts/maintenance/run_naver_settle_sync.py       init_sentry_once=0 capture_exception=1
scripts/maintenance/run_notification_escalation.py init_sentry_once=0 capture_exception=1
tools/ops/run_rq_worker.py                         init_sentry_once=0 capture_exception=0
tools/ops/run_domain_side_effect_outbox.py         init_sentry_once=1 capture_exception=2
```

`capture_exception`(`foms/services/loop_heartbeat.py:72-91`)은 **스스로 초기화하지 않는다** —
DSN 을 넣어도 이 3개 루프는 아무것도 안 보낸다. 각 루프는 별도 프로세스라(`start.sh` 의 `&`)
프로세스마다 자기 init 이 필요하다.

함정: `foms/platform` 을 최상단에서 import 하면 app_factory 를 통째로 끌어온다 — `init_sentry_once`
는 DSN 이 있을 때만 지연 import 하도록 이미 짜여 있다. 그 규율을 깨지 마라.
`scripts/maintenance/run_geocode_sweep.py:100-127` 은 같은 일을 **자기 안에 복제**해 두었다
(`_init_sentry_once`) — 공용 함수로 모을 수 있는지 판단해라(할 수 없으면 근거를 남겨라).

## C. 진짜로 멎어도 최대 90분 침묵 (sync_cadence)

`NAVER_ORDER_SYNC` 는 운영 간격 1800초라 예산이 5400초다. 예산을 좁히는 것은 답이 아니다
(그러면 이번 사고가 되돌아온다). 올바른 방향은 **일하는 주기와 살아 있다고 말하는 주기를
분리**하는 것이다 — 루프가 60초마다 하트비트를 남기고 `interval_seconds` 로 60 을 신고하면
예산이 자동으로 180초가 되고, 스윕은 지금처럼 1800초마다 한 번만 돈다.

- 지금 구조: `scripts/maintenance/run_naver_order_sync.py:103-121` 이 스윕 1회 → `emit_heartbeat`
  → `time.sleep(interval)`.
- **네이버 HTTP 호출 횟수가 늘어나면 안 된다.** 스윕 주기는 그대로 1800초다. 잠을 쪼개서
  자는 동안에도 하트비트만 남기는 형태가 된다.
- 신고 간격이 60이 되면 예산 180 — 스윕 자체가 60초 넘게 걸리는 tick 에서 헛알림이 나지
  않는지 반드시 따져라(스윕 도중에도 하트비트가 나가야 한다면 그렇게 설계해라).

## 파일 소유권 (겹치면 안 된다)

| 워커 | 편집 가능 파일 |
|---|---|
| worker_push | `foms/services/notifications/push_sender.py` · `foms/services/worker_watchdog.py` · `tests/domains/test_push_sender.py` · `tests/domains/test_worker_watchdog.py` (+ 등재 조사에서 나온 파일은 **총괄에게 보고만**) |
| loop_sentry | `scripts/maintenance/run_naver_settle_sync.py` · `scripts/maintenance/run_notification_escalation.py` · `tools/ops/run_rq_worker.py` · `tests/domains/test_loop_heartbeat_wiring.py` |
| sync_cadence | `scripts/maintenance/run_naver_order_sync.py` (Sentry init 도 이 워커가 같이 넣는다) · `tests/domains/test_worker_loop_heartbeat.py` |

`tests/domains/test_loop_heartbeat_wiring.py` 는 loop_sentry **만** 건드린다. sync_cadence 가
그 파일의 계약을 깨면 고치지 말고 보고해라.

## 공통 규칙

- 근본 원인 수정만. 증상 덮기·우회·`try/except: pass`·하드코딩 우회·`# TODO` 미봉책 금지.
- 한글 docstring·타입 힌트 필수. 함수 50줄 이하.
- **계약 테스트는 변이 검증까지.** 방어를 하나씩 없애 red 가 되는지 확인하고 출력 원문을
  보고서에 넣어라. 단언끼리 겹쳐 한쪽을 지워도 통과하면 그 테스트는 잘못 쓴 것이다.
- 전체 pytest 금지(단일 파일만), `python` 앞에 `PYTHONIOENCODING=utf-8`, git 명령 금지,
  CRLF 보존, 루트 신규 파일 금지, 모든 명령을 `cd C:\tmp\foms-s-wdflap &&` 로 시작.
- 기존 JS 를 고치면 `?v` 핀을 올린다(SW staticCacheFirst). `static/sw.js` 를 고칠 일이
  생기면 총괄에게 보고부터 해라(공용 파일).
