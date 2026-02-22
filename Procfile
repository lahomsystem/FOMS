# Railway 배포용 Procfile (다중 사용자 확장 계획 2026-02-22)
# Socket.IO + Redis MQ 사용 시 다중 워커/Replica OK (sticky session 불필요)
web: gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 app:app
# 비동기 작업 전용 (REDIS_URL, USE_RQ_WORKER=1 설정 시 별도 서비스로 기동)
worker: rq worker default --url $REDIS_URL
