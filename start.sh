#!/bin/bash
set -e  # 어떤 명령이 실패해도 즉시 종료
# Railway unified start: USE_RQ_WORKER=1이면 RQ worker, 아니면 gunicorn
#
# 마이그레이션(alembic upgrade + ensure_schema)은 여기서 실행하지 않는다.
# replica마다 부팅 시 실행하면 세션 advisory lock으로 직렬화되어 cold-start가
# 증폭되므로, 배포당 1회 실행되는 preDeployCommand(predeploy.sh)로 이관했다.
# → replica 부팅은 gunicorn 기동만 남아 즉시화된다.
if [ "$USE_RQ_WORKER" = "1" ]; then
  # P0 긴급 알림 escalation 스윕 (알림 Phase 3C): FOMS에 in-process 스케줄러가
  # 없으므로 worker 컨테이너에서 long-running 루프로 배선한다 (--loop = 앱 1회
  # 부팅 후 주기 스윕, AUTO-INIT 반복 없음). 백그라운드 서브셸이라 스윕 실패가
  # rq worker 본체에 영향 없고, 다중 replica여도 스윕은 idempotent라 안전.
  # Redis 부팅 레이스 방어 (2026-08-07 운영 사고 근본 수정):
  # Railway 프라이빗 네트워크/Redis 컨테이너가 워커보다 늦게 준비되면
  # `rq worker`가 첫 명령(is_suspended)에서 redis TimeoutError로 즉사한다.
  # 즉사 간격이 ~11초라 재시작 정책 ON_FAILURE(10회)가 2분 만에 소진되고
  # 서비스가 CRASHED로 고착됐다. PING 성공까지 기다린 뒤 기동한다.
  # (예산 초과 시 set -e 로 종료 → Railway 재시작 1회가 수 분을 커버)
  python tools/ops/wait_for_redis.py --url "$REDIS_URL" \
    --timeout "${FOMS_REDIS_WAIT_SECONDS:-300}"

  if [ "$FOMS_ESCALATION_LOOP_ENABLED" = "1" ]; then
    python scripts/maintenance/run_notification_escalation.py --loop \
      --interval "${FOMS_ESCALATION_INTERVAL_SECONDS:-60}" --json &
  fi


  # 네이버 스마트스토어 주문 수집 (NAVER-INGEST-01). escalation 과 같은 배선이다:
  # 백그라운드 서브셸이라 수집 실패가 rq worker 본체를 죽이지 않고, 다중 replica 여도
  # 멱등(UNIQUE (channel, external_id))이라 안전하다.
  # **이 루프는 WORKER 에서만 돈다** — 커머스API센터 호출 IP 한도 3 = Railway static IP 3 이라
  # 여유가 없어 네이버로 나가는 HTTP 는 이 서비스 한 곳으로 몰아야 한다. 기본은 off.
  if [ "$FOMS_NAVER_SYNC_ENABLED" = "1" ]; then
    python scripts/maintenance/run_naver_order_sync.py --loop \
      --interval "${FOMS_NAVER_SYNC_INTERVAL_SECONDS:-300}" --json &
  fi


  # 네이버 발송처리 자동 실행 (NAVER-AUTODISPATCH-01). 사람이 매일 화면에서 누르던
  # 일괄 발송처리를 평일 정해진 시각(기본 16:50 KST)에 대신한다. 수집 루프와 같은 배선이고,
  # 같은 이유로 **WORKER 에서만** 돈다(네이버 HTTP 단일 출구).
  # 되돌릴 수 없는 조작이라 기본은 off 이고, 하루 1회 계약은 서비스가 DB 로 지킨다 —
  # 루프가 창 안에서 여러 번 깨어나도 두 번 나가지 않는다.
  if [ "$FOMS_NAVER_AUTO_DISPATCH_ENABLED" = "1" ]; then
    python scripts/maintenance/run_naver_auto_dispatch.py --loop \
      --at "${FOMS_NAVER_AUTO_DISPATCH_AT:-16:50}" \
      --window "${FOMS_NAVER_AUTO_DISPATCH_WINDOW_MINUTES:-10}" --json &
  fi


  # 네이버 정산 동기화 (SETTLE-CHANNEL-01 §4). 수집·자동 발송 루프와 같은 배선이고,
  # 같은 이유로 **WORKER 에서만** 돈다(네이버 HTTP 단일 출구). 읽기 전용이지만 하루당
  # 2회 x 45일 = 100회 안팎이라 사람이 화면을 쓰는 시간대와 겹치지 않게 새벽에 돈다.
  # 파티션 통째 교체라 창 안에서 여러 번 깨어나도 결과가 같다(멱등). 기본은 off.
  if [ "$FOMS_NAVER_SETTLE_SYNC_ENABLED" = "1" ]; then
    python scripts/maintenance/run_naver_settle_sync.py --loop \
      --at "${FOMS_NAVER_SETTLE_SYNC_AT:-05:30}" \
      --window "${FOMS_NAVER_SETTLE_SYNC_WINDOW_MINUTES:-10}" --json &
  fi


  # 좌표 스윕 (GEO-SWEEP-01): 좌표 없는 주문을 미리 지오코딩 큐에 넣어, 사용자가 지도를
  # 열 때까지 좌표가 비어 있는 문제를 없앤다 (주문 생성/주소 수정의 지오코딩 예약이 SIDEFX
  # outbox 로 가는데 그 워커가 운영에 배포된 적이 없어 소비되지 않는 상태의 안전망).
  # 새 Railway 서비스를 만들지 않고 이 worker 컨테이너를 재사용한다 — rq worker 가 어차피
  # 같은 큐를 소비하므로 배선이 가장 짧다. escalation 과 같은 패턴: 백그라운드 서브셸이라
  # 스윕 실패가 rq worker 본체에 영향 없고, 스윕은 idempotent(enqueue 전에 pending +
  # geocoded_at 시도 표식을 커밋)라 replica 가 여럿이어도 중복으로 큐가 부풀지 않는다.
  if [ "$FOMS_GEOCODE_SWEEP_ENABLED" = "1" ]; then
    python scripts/maintenance/run_geocode_sweep.py --loop \
      --interval "${FOMS_GEOCODE_SWEEP_INTERVAL_SECONDS:-60}" --json &
  fi
  # 큐 소비 본체. `rq worker` CLI 를 그대로 쓰지 않는 이유는 하나다 — 그 프로세스가
  # 자기 생존을 FOMS 감시 표(side_effect_worker_heartbeats)에 안 남겨서, 큐가 멎어도
  # 표만 봐서는 알 수 없었다(2026-02 워커 offline). 러너는 rq 하트비트 자리에서
  # RQ_WORKER 행을 함께 갱신할 뿐, 소비 동작은 rq 그대로다.
  #
  # === 감시 루프 (2026-09-08 운영 사고 근본 수정) ===
  # 러너를 `exec` 로 띄우면 그 프로세스가 PID 1 이라 **러너 종료 = 컨테이너 종료**다.
  # 운행 중 Redis 가 재시작하면 rq 는 "Redis connection timeout, quitting..." 으로
  # 스스로 끝나는데, Railway 재시작 정책(ON_FAILURE)은 그 정상 종료를 실패로 보지 않아
  # 워커가 영구 정지했다 — 2026-09-08 13:36 KST, 승격 배포로 워커와 Redis 가 같이
  # 재기동하다 Redis 가 뒤늦게 내려가 워커가 자멸했고 발주확인 6건이 큐에 11분 넘게
  # 갇혔다(사람이 반응 없는 버튼을 반복해서 눌렀다). 부팅 레이스는 wait_for_redis 가
  # 막지만 **운행 중 재시작은 못 막는다** — 그 구멍을 이 루프가 메운다.
  # 이제 PID 1 은 이 루프가 잡고, 러너가 죽으면 Redis 복귀를 기다렸다 다시 띄운다.
  RQ_PID=""
  _rq_forward_term() {
    if [ -n "$RQ_PID" ]; then
      kill -TERM "$RQ_PID" 2>/dev/null || true
      wait "$RQ_PID" 2>/dev/null || true
    fi
    exit 0
  }
  # Railway 정지·재배포(SIGTERM)는 러너에 그대로 넘겨 진행 중 잡을 정상 종료시킨다.
  trap _rq_forward_term TERM INT

  RQ_BACKOFF=5
  while true; do
    # 재기동 전 Redis PING 을 다시 기다린다(첫 바퀴는 위에서 이미 통과했으므로 즉시).
    # 예산을 넘겨도 루프를 깨지 않는다 — 다음 바퀴에서 다시 기다린다.
    python tools/ops/wait_for_redis.py --url "$REDIS_URL" --timeout "${FOMS_REDIS_WAIT_SECONDS:-300}" || true

    RQ_STARTED_AT=$(date +%s)
    python tools/ops/run_rq_worker.py --url "$REDIS_URL" --queues default &
    RQ_PID=$!
    RQ_RC=0
    wait "$RQ_PID" || RQ_RC=$?
    RQ_PID=""
    RQ_RAN=$(( $(date +%s) - RQ_STARTED_AT ))

    # 오래 살다 죽었으면 일시 장애로 보고 backoff 를 되돌린다. 즉사가 반복되면
    # (설정 오류 등) 60초까지 늘려 로그 폭주와 무의미한 재시도를 막는다.
    if [ "$RQ_RAN" -ge 60 ]; then
      RQ_BACKOFF=5
    else
      RQ_BACKOFF=$(( RQ_BACKOFF * 2 ))
      if [ "$RQ_BACKOFF" -gt 60 ]; then
        RQ_BACKOFF=60
      fi
    fi
    echo "[rq-supervisor] run_rq_worker exited rc=${RQ_RC} after ${RQ_RAN}s - restarting in ${RQ_BACKOFF}s"
    sleep "$RQ_BACKOFF"
  done
else
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - --bind "0.0.0.0:${PORT:-8080}" app:app
fi
