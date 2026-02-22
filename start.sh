#!/bin/bash
# Railway unified start: USE_RQ_WORKER=1이면 RQ worker, 아니면 gunicorn
if [ "$USE_RQ_WORKER" = "1" ]; then
  exec rq worker default --url "$REDIS_URL"
else
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 app:app
fi
