#!/bin/bash
set -e  # 어떤 명령이 실패해도 즉시 종료
# Railway unified start: USE_RQ_WORKER=1이면 RQ worker, 아니면 gunicorn
if [ "$USE_RQ_WORKER" = "1" ]; then
  exec rq worker default --url "$REDIS_URL"
else
  echo "Running DB migrations..."
  alembic upgrade head
  echo "Migrations complete."

  # WDPlanner V2 컬럼 보정 (alembic_version 불일치 복구)
  python tools/ensure_schema.py

  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --bind "0.0.0.0:${PORT:-8080}" app:app
fi
