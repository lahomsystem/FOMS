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
  if [ "$FOMS_ESCALATION_LOOP_ENABLED" = "1" ]; then
    python scripts/maintenance/run_notification_escalation.py --loop \
      --interval "${FOMS_ESCALATION_INTERVAL_SECONDS:-60}" --json &
  fi
  exec rq worker default --url "$REDIS_URL"
else
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --bind "0.0.0.0:${PORT:-8080}" app:app
fi
