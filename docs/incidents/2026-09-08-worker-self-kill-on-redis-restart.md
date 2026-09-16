# 2026-09-08 워커 자멸 — 운행 중 Redis 재시작에 큐 소비자가 PID 1 째 죽었다

> 유형: 운영 사고  ·  상태: 종결 — 근본 수정 + 계약 테스트로 고정
> 작성 2026-09-16. 사후 등재 문서 — 사고 당시 기록이 원장에 남지 않아 저장소 근거로 재구성했다.

사후 등재인 이유: 수정 코드(`start.sh` 감시 루프)와 계약 테스트는 2026-09-08 에 deploy·production 까지
들어갔지만, 사고 자체를 적은 줄이 `docs/AI_CHANGELOG.md`·`docs/incidents/` 어디에도 없었다.
왜 PID 1 을 감시 루프가 잡아야 하는지가 계약 테스트 docstring 에만 남아 있었다.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 운영 사고 — 큐 전면 정지(작업 유실 없음, 지연). 사용자 화면은 "버튼이 안 먹는다" 로 보였다 |
| 원인 축 | 큐 소비자를 `exec` 로 띄워 **PID 1 이 러너**였다. 운행 중 Redis 가 재시작하면 rq 는 `Redis connection timeout, quitting...` 으로 **정상 종료**하는데, PID 1 종료 = 컨테이너 종료이고 Railway 재시작 정책(ON_FAILURE)은 그 정상 종료를 실패로 보지 않아 워커가 영구 정지했다 |
| 영향 | 2026-09-08 13:36 KST. 발주확인 6건이 큐에 11분 넘게 갇혔다. 사용자가 반응 없는 버튼을 반복해서 눌렀다 |
| 구조 변경 여부 | 예. `start.sh` 의 WORKER 분기에서 `exec` 제거 → 감시 루프가 PID 1 을 잡고 러너를 백그라운드로 띄운다. 계약 테스트 5건으로 원복 차단 |
| 재발 여부 | 이후 같은 자멸을 잰 기록 없음. 다만 워커 컨테이너 관련 사고는 이어졌다(09-09 감시자 헛알림, 09-10 정산 루프 자멸) — 원인 축은 서로 다르다 |

## 2. 증상

**발주확인 6건이 큐에 11분 넘게 갇혔다**(`tests/contracts/runtime/test_worker_supervisor_contract.py:7`).
사용자에게는 큐 정지로 보이지 않았다 — 눌러도 아무 일이 없는 버튼으로 보였고, 그래서 반복해서 눌렀다
(`start.sh:85`).

워커 프로세스는 **에러 없이** 사라졌다. rq 가 남긴 마지막 줄은 실패 로그가 아니라
`Redis connection timeout, quitting...` 이다(`start.sh:80-81`). 정상 종료이므로 Railway 의
재시작 정책(ON_FAILURE)이 걸리지 않았고, 서비스는 "정상 종료된 컨테이너" 로 남았다.

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| 2026-09-08 13:36 KST 직전 | 운영 승격 배포로 WORKER 와 Redis 가 함께 재기동 | `start.sh:83-84` |
| 13:36 KST 무렵 | Redis 가 뒤늦게 내려감 — 이미 기동을 마친 rq 가 연결을 잃음 | `start.sh:84-85` |
| 같은 시각 | rq 가 `Redis connection timeout, quitting...` 으로 자기 종료 → PID 1 종료 → 컨테이너 종료 | `start.sh:80-82` |
| 이후 11분 이상 | 워커 부재. 발주확인 6건 큐에 적체 | `tests/contracts/runtime/test_worker_supervisor_contract.py:7` |
| 2026-09-08 | 감시 루프 도입 + 계약 테스트 5건 | `start.sh:88-125`, 계약 테스트 |

## 4. 근본 원인

**부팅 레이스는 이미 막혀 있었다. 막히지 않은 것은 운행 중 재시작이다.**

2026-08-07 의 13시간 정지(`docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md`) 뒤
`tools/ops/wait_for_redis.py` 가 들어가 **기동 시점**의 Redis 부재를 막았다. 그러나 그 가드는
첫 바퀴에서 한 번만 돈다. 이미 기동을 마친 뒤 Redis 가 내려가는 경우에는 아무것도 하지 않는다
(`start.sh:85-87`).

그 구멍 위에 두 가지가 겹쳐 사고가 됐다.

- **PID 1 이 큐 소비자였다.** `exec` 로 자기를 대체하므로 러너의 종료가 곧 컨테이너의 종료다
  (`start.sh:80-81`).
- **그 종료가 "실패" 가 아니었다.** rq 는 연결 타임아웃을 정상 종료로 처리한다. ON_FAILURE 정책은
  실패에만 반응하므로 재시작이 걸리지 않았다(`start.sh:81-84`).

즉 죽는 것 자체는 막을 수 없고(외부 의존), 죽은 뒤 **다시 일어나는 자리가 없었다**는 것이 원인이다.

## 5. 복구

별도 복구 조작 기록 없음 — 큐의 작업은 유실되지 않으므로 워커가 돌아온 뒤 소진됐다.
사용자에게 어떻게 고지했는지는 `미상(근거 없음)`.

## 6. 구조 변경

**PID 1 을 감시 루프가 잡는다**(`start.sh:88-125`).

- `exec` 제거. 러너는 백그라운드(`&`)로 띄우고 `wait "$RQ_PID"` 로 지켜본다 — 그래야 트랩이 걸린다.
- **재기동 전에 Redis PING 을 다시 기다린다**(`wait_for_redis.py`, 예산 초과여도 루프를 깨지 않는다).
  안 그러면 즉사 루프가 된다.
- **backoff 5~60초.** 60초 이상 살다 죽었으면 일시 장애로 보고 5초로 되돌리고, 즉사가 반복되면
  (설정 오류 등) 두 배씩 늘려 60초에서 멈춘다.
- **SIGTERM 전달.** Railway 정지·재배포 신호는 러너에 그대로 넘겨 진행 중인 잡을 정상 종료시킨다
  (`_rq_forward_term`).
- **`[rq-supervisor]` 로그.** 재기동 사실이 남아야 사후 추적이 된다.

원복 차단은 계약 테스트 5건이 맡는다(`tests/contracts/runtime/test_worker_supervisor_contract.py`):
`test_queue_consumer_is_not_pid_one`, `test_supervisor_loop_restarts_rq_and_rewaits_redis`,
`test_supervisor_forwards_sigterm_for_graceful_stop`, `test_supervisor_backs_off_on_hot_crash_loop`,
`test_no_deploy_entrypoint_bypasses_start_sh`.

마지막 하나가 중요하다 — `Procfile`·`railway-worker.toml` 이 `start.sh` 를 우회해 큐 소비자를
직접 띄우면 감시 루프가 통째로 빠지므로, 진입점 쪽도 함께 못 박았다.

**들어가지 않은 것**: Redis 재시작 자체를 막거나 줄이는 조치는 없다. 워커는 여전히 1대이고
(네이버 커머스API 호출 IP 계약, `docs/incidents/2026-08-31-worker-redeploy-queue-stall-852s.md`),
재배포는 지금도 큐 전면 정지다.

## 7. 재발 여부·남은 것

- 재발 여부 — 같은 자멸(운행 중 Redis 재시작 → 컨테이너 종료)을 다시 잰 기록은 없다.
- 남은 것 ①: 이 컨테이너에는 감시 루프 밖의 **무감독 백그라운드 루프들**이 함께 얹혀 있다.
  같은 성격의 자멸이 2026-09-10 정산 루프에서 다시 일어났다
  (`docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md`) — 그쪽은 감시자가 아예 없었다.
- 남은 것 ②: 워커 정지를 사람에게 알리는 경로. 2026-09-09 에 감시자가 붙었지만 헛알림 26건을 내고
  꺼졌다(`docs/incidents/2026-09-09-worker-watchdog-false-stall-flap.md`).
- 남은 것 ③: 이 사고가 11주 동안 사고 원장 밖에 있었다는 사실 자체. 코드와 계약 테스트는 들어갔는데
  기록이 빠졌다. 본 등재가 그 자리다.

## 8. 근거 앵커

- `start.sh:74-77` — 러너를 쓰는 이유(rq CLI 는 FOMS 감시 표에 생존을 안 남긴다, 2026-02 워커 offline)
- `start.sh:79-87` — `exec` = PID 1 · rq 의 정상 종료 · ON_FAILURE 미반응 · 2026-09-08 13:36 KST · 발주확인 6건 11분 · 부팅 레이스와 운행 중 재시작의 구분
- `start.sh:88-125` — 감시 루프 본문(트랩·백그라운드+wait·재대기·backoff·`[rq-supervisor]` 로그)
- `tests/contracts/runtime/test_worker_supervisor_contract.py:1-11` — 사고 경위와 계약의 목적
- `tests/contracts/runtime/test_worker_supervisor_contract.py:34-85` — 계약 5건
- `tools/ops/run_rq_worker.py:1-21` — 러너의 역할(rq `heartbeat()` 자리에서 `RQ_WORKER` 행 갱신, 예산 1215초)
- `docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md` — 부팅 레이스(선행 사고, `wait_for_redis` 도입)
- `docs/incidents/2026-08-31-worker-redeploy-queue-stall-852s.md` — 단일 워커·재배포 = 큐 전면 정지
- `docs/incidents/2026-09-09-worker-watchdog-false-stall-flap.md` — 정지 감시자 헛알림 26건
- `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md` — 감시 루프 밖 백그라운드 루프의 자멸
