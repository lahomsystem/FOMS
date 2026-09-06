# 2026-08-07 워커 부팅 레이스로 13시간 무중단 정지

> 유형: 운영 사고  ·  상태: 종결
> 작성 2026-09-07. 사후 등재 문서 — 사고 당시 기록이 아니라 저장소 근거로 재구성했다.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 운영 사고 — 단일 워커 컨테이너 전면 정지(13시간) |
| 원인 축 | 부팅 레이스. Railway 프라이빗 네트워크(`redis.railway.internal`)가 컨테이너 기동 직후 몇 초간 라우팅되지 않을 수 있고 Redis 서비스 자체가 재시작 중일 수도 있는데, `rq worker` 가 부팅 첫 명령(`is_suspended`)에서 redis `TimeoutError` 로 즉사했다(`tools/ops/wait_for_redis.py:1-14`) |
| 복구 | `미상(근거 없음)` — 무엇으로 되살렸는지 저장소에 기록 없음 |
| 구조 변경 여부 | 있음. `tools/ops/wait_for_redis.py` 신설 + `start.sh:14-21` 이 워커 기동 전 Redis PING 성공까지 대기 |
| 재발 여부 | `미상(근거 없음)` — 이후 같은 CRASHED 고착이 있었다는 기록 없음 |

## 2. 증상

워커 서비스가 부팅 즉시 죽기를 반복하다 **CRASHED 상태로 고착**했고, 그대로
**13시간 무중단 정지**했다(`tools/ops/wait_for_redis.py:1-14`).

죽는 지점은 정확히 하나다 — `rq worker` 의 부팅 첫 명령 `is_suspended` 에서 redis
`TimeoutError`(`tools/ops/wait_for_redis.py:5-7`, `start.sh:15-16`).

이 정지가 사용자 화면에서 어떤 증상으로 보였는지, 누가 발견했는지는 `미상(근거 없음)`.
다만 이 컨테이너가 무엇을 들고 있는지는 별건으로 확인돼 있다 — 무감독 루프 5개
(에스컬레이션·수집·자동 발송·정산·지오코딩 스윕)가 `&` 로 뜨고 셸은 `exec rq worker` 로
대체돼 supervisor 도 하트비트도 0이다(`docs/plans/2026-09-06-foms-system-review-report.md:50`, R3).

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| 2026-08-07 (HH:MM `미상(근거 없음)`) | 워커 컨테이너 기동 시점에 Redis 가 아직 준비되지 않음(프라이빗 네트워크 미라우팅 또는 Redis 재시작 중) | `tools/ops/wait_for_redis.py:4-7` |
| +0초 | `rq worker` 가 첫 명령 `is_suspended` 에서 redis `TimeoutError` 로 즉사 | `tools/ops/wait_for_redis.py:6-7` |
| 약 11초 간격 | Railway 재시작 정책 `ON_FAILURE`(최대 10회)가 같은 즉사를 반복 | `tools/ops/wait_for_redis.py:8-9`, `start.sh:17-18` |
| 약 2분 | 재시도 예산 소진 → 서비스 **CRASHED 고착** | `tools/ops/wait_for_redis.py:8-9` |
| 이후 13시간 | 무중단 정지 | `tools/ops/wait_for_redis.py:9` |
| `미상(근거 없음)` | 정지 발견 및 서비스 복귀 | — |

시각(HH:MM)은 어느 칸도 저장소에 없다. 위 표의 상대 간격(~11초·2분·13시간)만
`wait_for_redis.py` docstring 이 단정한 값이다.

## 4. 근본 원인

**두 겹이다. 둘 다 docstring 이 단정으로 적어 두었다**(`tools/ops/wait_for_redis.py:1-14`).

1. **부팅 레이스.** Railway 프라이빗 네트워크(`redis.railway.internal`)는 컨테이너 기동
   직후 몇 초간 라우팅되지 않을 수 있고, Redis 서비스 자체가 재시작 중일 수도 있다.
   그때 `rq worker` 는 기다리지 않고 첫 명령에서 예외로 죽는다.
2. **재시작 예산이 레이스보다 빨리 마른다.** 즉사 간격이 ~11초라 `ON_FAILURE` 10회가
   2분 만에 소진된다. 즉 "몇 초 뒤면 붙었을 의존" 을 재시작 정책이 기다려 주지 못하고,
   한 번의 일시 오류가 **영구 고착**으로 승격된다. 13시간은 그 승격의 값이다.

되짚어야 할 성질: 실패한 것은 워커 코드가 아니라 **부팅 순서 가정**이다. 워커는 Redis 가
자기보다 먼저 준비돼 있다고 가정했고, 그 가정이 깨졌을 때 물러설 자리가 없었다.

## 5. 복구

`미상(근거 없음)`. 서비스를 어떻게 되살렸는지(수동 재배포·Redis 재시작·플랫폼 조치)를
적은 줄이 저장소에 없다. 데이터 손실 여부도 이 사고에 대해서는 기록이 없다 — `미상(근거 없음)`.

## 6. 구조 변경

**근본 수정이 들어갔다.**

- `tools/ops/wait_for_redis.py` 신설(`:1-14` docstring 이 배경·해결을 그대로 담고 있다).
  워커 기동 전에 Redis PING 성공까지 대기하고, 대기 예산을 넘기면 **비정상 종료(exit 1)로
  Railway 재시작에 맡긴다** — 한 번의 재시작이 수 분을 커버하므로 재시도 예산이 순식간에
  마르지 않는다(`tools/ops/wait_for_redis.py:11-14`).
- `start.sh:14-21` 이 워커 기동 경로에서 그 스크립트를 부른다. 주석이 사고를 직접 기록한다
  ("Redis 부팅 레이스 방어 (2026-08-07 운영 사고 근본 수정)"). 예산은
  `FOMS_REDIS_WAIT_SECONDS`(기본 300초)로 잡혀 있다(`start.sh:20-21`).

이 조치는 증상 덮기가 아니라 원인 제거다 — 죽는 자리를 try/except 로 감싼 것이 아니라
**부팅 순서 가정 자체를 대기로 바꿨다**.

## 7. 재발 여부·남은 것

- 재발 여부 — `미상(근거 없음)`. 2026-08-07 이후 같은 CRASHED 고착을 적은 줄이 없다.
- 남은 것 ①: 이 워커는 여전히 **1대**다. 네이버 커머스API 호출 IP 계약상 단일 서비스라
  복제로 풀 수 없다(`tools/ops/check_worker_redeploy_safe.py:3-4`,
  `docs/plans/2026-09-06-foms-system-review-report.md:50`). 즉 이 컨테이너의 정지는
  지금도 큐 전면 정지다(그 자체가 2026-08-31 사고 —
  `docs/incidents/2026-08-31-worker-redeploy-queue-stall-852s.md`).
- 남은 것 ②: **정지를 사람에게 알리는 경로가 여전히 없다.** `/healthz` 는 설계상 liveness 만이고
  `init_sentry` 호출처는 web 한 곳, 워크플로 7개에 알림 0(`docs/plans/2026-09-06-foms-system-review-report.md:50`).
  이 사고에서 13시간이 흐른 이유를 구조가 아직 갖고 있다.
- 남은 것 ③: 같은 "소비 프로세스가 안 돈다" 실패 모드가 6개월 간격으로 반복됐고 두 번 다
  사용자가 화면에서 발견했다(2026-02 워커 offline · 2026-08-31 SIDEFX 미배포 —
  `docs/plans/2026-09-06-foms-system-review-report.md:133`,
  `docs/incidents/2026-02-22-railway-worker-map-utils.md:8-15`).

## 8. 근거 앵커

- `tools/ops/wait_for_redis.py:1-14` — 배경·해결 전문(13시간 정지·~11초 즉사·ON_FAILURE 10회·2분 소진·CRASHED 고착)
- `start.sh:14-21` — 사고를 명시한 배선 주석 + PING 대기 호출(`FOMS_REDIS_WAIT_SECONDS` 기본 300초)
- `tools/ops/check_worker_redeploy_safe.py:3-4` — 운영 worker 가 1대인 이유(네이버 IP 계약)
- `docs/plans/2026-09-06-foms-system-review-report.md:50` — R3, 워커 단일 장애점·supervisor 0·알림 0, 근거 목록에 `tools/ops/wait_for_redis.py:1-12`(13시간 정지) 포함
- `docs/plans/2026-09-06-foms-system-review-report.md:133-134` — R8, 반복 실패 모드와 "운영 사고 4건이 사고 원장 밖"
- `docs/incidents/2026-02-22-railway-worker-map-utils.md:8-15` — 같은 유형 선행 사고(2026-02)
