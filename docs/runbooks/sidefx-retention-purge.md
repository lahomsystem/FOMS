# SIDEFX-RETENTION-01 운영 런북 — side-effect outbox retention purge

SIDEFX-00 `domain_side_effect_outbox` 의 **terminal 행**(DONE/DEAD)을 retention 기간을
넘겼을 때만 삭제하는 절차. 스키마·마이그레이션은 SIDEFX-00 소관이며 이 packet 은 purge
CLI + 공용 worker daily provider **배선 재사용**만 소유한다(신규 scheduler/worker 없음).

## 두 삭제 경로 (같은 대상, 같은 정밀 조건)

| 경로 | 파일 | 언제 | 대상 |
|---|---|---|---|
| **자동(daily)** | `tools/ops/run_domain_side_effect_outbox.py` 의 RETENTION loop | 공용 worker 가 `--retention-scan-interval`(기본 **86400s**)마다 `run_retention_once` 호출 | DONE completed_at>30d, DEAD dead_at>180d |
| **수동/ops** | `tools/ops/purge_domain_side_effect_outbox.py` | 진단·강제 실행(dry-run 기본) | 동일 |

두 경로 모두 **PENDING/PROCESSING 는 절대 삭제하지 않고**(status 술어가 구조적 제외),
source business row 도 건드리지 않는다(outbox 행만). broad date delete 가 아니라
`id IN (SELECT id ... WHERE status+timestamp)` **ID 멤버십 배치 삭제**이며, 배치마다
commit 하므로 중단 후 재실행이 남은 것부터 이어가는 resume 이다.

## 수동 CLI

```
# dry-run(기본) — 삭제 없이 DONE/DEAD 대상 수만 보고
python tools/ops/purge_domain_side_effect_outbox.py

# 실제 삭제
python tools/ops/purge_domain_side_effect_outbox.py --apply

# retention·배치 조정(기본: DONE 30d / DEAD 180d / batch 1000)
python tools/ops/purge_domain_side_effect_outbox.py --apply \
    --done-retention-days 30 --dead-retention-days 180 --batch-size 1000
```

- 기본은 **dry-run**. `--apply` 없이는 아무것도 지우지 않는다.
- 동시 실행은 session-level advisory lock(`foms:purge_domain_side_effect_outbox`)으로
  직렬화 — 다른 purge(수동 재실행)가 진행 중이면 benign skip(삭제 0). 자동 worker 경로는
  자체 lock(`foms:sidefx_retention_scan`)을 쓰므로 두 경로가 겹쳐도 각자 안전하다(겹치는
  id 배치는 한쪽이 더 적게 삭제할 뿐 — 정합성 무손상).
- exit 0 = 성공(dry-run·apply·lock-skip 포함), 1 = 오류.
- env: `DATABASE_URL`(없으면 `FOMS_TEST_DATABASE_URL`). Flask app 을 import 하지 않아
  Railway heartbeat timeout 을 피한다.

## 자동 경로 확인 (readiness)

공용 worker 가 daily retention 을 돌리는지는 RETENTION heartbeat 로 관측한다:

```
python tools/ops/check_sidefx_readiness.py --max-retention-scan-lag 90000
```

- RETENTION heartbeat 의 `oldest_lag_seconds`(마지막 retention scan 이후 경과)가
  90000s(하루+여유) 미만이어야 ready. 초과·누락이면 worker 미기동/정체 신호.

## 장애 대응

| 증상 | 원인 후보 | 조치 |
|---|---|---|
| terminal 행 무한 누적(DONE/DEAD 표 비대) | worker RETENTION loop 정체 또는 미기동 | readiness 로 RETENTION scan lag 확인, worker 재기동. 급하면 수동 `--apply` 로 즉시 정리 |
| 수동 CLI 가 삭제 0 보고 | (a) 대상 없음 (b) advisory lock 경합 | 로그의 `advisory lock busy` 여부 확인 — busy 면 다른 purge 종료 후 재실행 |
| retention scan lag 초과 | 다른 replica/수동 실행이 lock 을 오래 잡음 | 수동 장기 purge 를 배치로 나눠 실행(`--batch-size` 하향), worker 로그 확인 |

## 경계

- **PENDING/PROCESSING 미삭제**·**source business row 미접근**·**broad date delete 금지**
  (정밀 status+timestamp + ID 배치)·**별도 scheduler/worker 신설 금지**(공용 worker 재사용)·
  **마이그레이션/models 스키마 무변경**.
