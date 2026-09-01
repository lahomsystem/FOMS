# SIDEFX-WORKER-01 운영 런북 — domain side-effect outbox worker

SIDEFX-00 이 만든 `domain_side_effect_outbox` / `side_effect_worker_heartbeats` 스키마를
소비하는 delivery/expiry/retention worker + readiness checker 운영 절차. 스키마·마이그레이션은
SIDEFX-00 소관이며 이 packet 은 consumer mechanics 만 소유한다.

## 구성 요소

| 파일 | 역할 |
|---|---|
| `tools/ops/run_domain_side_effect_outbox.py` | worker: delivery(claim/lease/dispatch/DONE·retry·DEAD) + expiry scan(만료 lease 회수) + retention scan(purge) + heartbeat |
| `tools/ops/check_sidefx_readiness.py` | readiness: heartbeat 신선도·scan lag·PENDING lag·DEAD count fail-closed 판정 |
| `railway-domain-sidefx.toml` | 별도 Railway service config |
| `foms/services/sidefx_worker.py` | mechanics + handler registry(하류가 채움) + readiness 평가 |

## 배포 (오케스트레이터)

1. Railway 대시보드 > 새 service > Settings > Config Path `railway-domain-sidefx.toml`.
2. env: 이 service 에 `DATABASE_URL` 를 web 과 동일 인스턴스로 연결.
   `STORAGE_DELETE` 는 `R2_*`, `ALIMTALK_SEND` 는 web 과 같은 `SOLAPI_*`(발신번호·브랜드
   프로필 포함)가 필요하다. 키가 없으면 알림톡 행은 재시도 후 DEAD 가 된다.

   > **운영 현황 (2026-09-01 기준 — 사용자 결정)**: 운영 web 에
   > `FOMS_ALIMTALK_AUTO_ENABLED` 를 **설정하지 않았다(=off)**. 따라서 운영에서 나가는
   > 알림톡·문자는 **전부 web 요청 스레드가 동기로** 보낸다 — 실측 수동 버튼
   > (`POST /api/kakao/alimtalk/send-manual/<id>`), 공유 링크 알림톡·문자
   > (`foms/api/share.py`, payload 가 `sync_only: True` 라 워커로 옮길 수 없다).
   > `ALIMTALK_SEND` outbox 행은 **한 건도 생기지 않는다**(생산자 게이트가 web 에 있다 —
   > `kakao_alimtalk.maybe_send_measure_alimtalk`). 그래서 운영 SIDEFX 에 `SOLAPI_*` 를
   > 복사하지 않았고, 지금은 없어도 무해하다.
   >
   > 자동 발송을 켤 때의 **선결 순서**(어기면 그 일정의 멱등 슬롯이 소각된다):
   > ① 운영 SIDEFX 에 `SOLAPI_*` 복사 → ② SIDEFX 재배포 후 handler 등록 확인
   > (`register_handler("ALIMTALK_SEND", ...)`) → ③ 그 다음에야 web 에
   > `FOMS_ALIMTALK_AUTO_ENABLED=1`. 웹을 먼저 켜면 handler 없는 행이 약 43분 뒤 DEAD 가
   > 되고, DEAD 도 `(effect_type, dedupe_key)` UNIQUE 를 180일간 점유한다.
3. start command(자동, toml 정본):
   ```
   python tools/ops/run_domain_side_effect_outbox.py --loop --interval 5 --expiry-scan-interval 300 --retention-scan-interval 86400
   ```
4. web/rq-worker/cron service 에는 이 command·import 등록이 **0** 이어야 한다.

> **경계**: 이 packet 은 registry **인터페이스만** 제공한다. 실 도메인 handler
> (NOTIFICATION/STORAGE_DELETE/GEOCODE 등)는 하류 CHANNEL-WRITER-01·URGENT-CALL-01·
> NOTIFICATION packet 이 `foms.services.sidefx_worker.register_handler(effect_type, handler)`
> 로 등록한다. handler 미배포 상태에서 delivery 를 켜면 해당 effect 는 NoHandler 로
> 재시도되다 `--max-attempts`(기본 10) 소진 시 DEAD 가 되므로, handler 배포 전에는
> 관련 `FOMS_*_MODE` 를 ENFORCED/TICKET 으로 올리지 않는다(§8.2 line 1548).

## readiness 확인 (§8.2 registry command template)

```
python tools/ops/check_sidefx_readiness.py --max-heartbeat-age 30 \
    --max-oldest-pending-lag 60 --max-expiry-scan-lag 360 \
    --max-retention-scan-lag 90000 --max-dead 0
```

- exit 0 = ready, exit 1 = not-ready(판정 실패), exit 2 = 조회 불가(역시 fail-closed).
- `--json` 으로 관측치/실패 목록을 기계 판독 형식 출력.
- 세 heartbeat(DELIVERY/EXPIRY_SCAN/RETENTION) 중 하나라도 없거나 stale 이면 not-ready
  (worker 미기동 신호).

## 장애 대응

| 증상 | 원인 후보 | 조치 |
|---|---|---|
| readiness heartbeat 미존재 | worker service 미기동/크래시 | Railway service 로그 확인, 재기동. env `DATABASE_URL` 확인 |
| PENDING lag 초과 | delivery 정체(handler 느림/예외 폭주, 배치 부족) | 로그의 `delivery step failed` 확인, handler 상태 점검. `--batch-size` 상향 검토 |
| scan lag 초과 | expiry/retention loop 정체 또는 advisory lock 경합 | 다른 replica/수동 실행이 lock 을 오래 잡는지 확인 |
| DEAD > 0 | handler 반복 실패 또는 NoHandler(handler 미배포) | `domain_side_effect_outbox` 의 `last_error` 조회로 원인 분류. handler 배포/수정 후 필요 시 해당 행을 PENDING 으로 수동 재큐 |
| lease 만료 누적 | worker 크래시 중 PROCESSING 잔류 | expiry scan 이 회수(만료 lease → PENDING backoff, attempts 소진 시 DEAD). scan 이 도는지 heartbeat 로 확인 |

## 단발 실행 (검증/수동)

`--loop` 없이 실행하면 delivery+expiry+retention 을 한 번씩 돌고 종료한다(cron·smoke 용):

```
python tools/ops/run_domain_side_effect_outbox.py --once
```

## graceful shutdown

worker 는 SIGTERM/SIGINT 에 현재 loop step 을 마치고 종료(exit 0)한다. Railway
redeploy 시 in-flight 처리를 안전하게 마감하며, 처리 중이던 PROCESSING 행은 lease 만료 뒤
다음 worker 의 expiry scan 이 회수한다(at-least-once — idempotency 는 handler 의
`provider_idempotency_key` 로 보장).
