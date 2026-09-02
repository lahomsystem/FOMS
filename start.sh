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
  exec rq worker default --url "$REDIS_URL"
else
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - --bind "0.0.0.0:${PORT:-8080}" app:app
fi
