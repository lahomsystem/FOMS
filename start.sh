#!/bin/bash
set -e  # 어떤 명령이 실패해도 즉시 종료
# Railway unified start: USE_RQ_WORKER=1이면 RQ worker, 아니면 gunicorn
#
# 마이그레이션(alembic upgrade + ensure_schema)은 여기서 실행하지 않는다.
# replica마다 부팅 시 실행하면 세션 advisory lock으로 직렬화되어 cold-start가
# 증폭되므로, 배포당 1회 실행되는 preDeployCommand(predeploy.sh)로 이관했다.
# → replica 부팅은 gunicorn 기동만 남아 즉시화된다.
if [ "$USE_RQ_WORKER" = "1" ]; then
  exec rq worker default --url "$REDIS_URL"
else
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --bind "0.0.0.0:${PORT:-8080}" app:app
fi
