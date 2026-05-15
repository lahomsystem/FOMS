#!/bin/bash
# Railway unified start: USE_RQ_WORKER=1이면 RQ worker, 아니면 gunicorn
if [ "$USE_RQ_WORKER" = "1" ]; then
  exec rq worker default --url "$REDIS_URL"
else
  # Run migrations before starting the web server (must succeed — no silent swallow)
  echo "Running DB migrations..."
  alembic upgrade head
  echo "Migrations complete."
  
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --bind "0.0.0.0:${PORT:-8080}" app:app
fi
