# Railway 배포용 Procfile (다중 사용자 확장 계획 2026-02-22)
# Socket.IO + Redis MQ 사용 시 다중 워커/Replica OK (sticky session 불필요)
web: gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - app:app
# 비동기 작업 전용 (REDIS_URL, USE_RQ_WORKER=1 설정 시 별도 서비스로 기동)
# rq worker 를 직접 띄우지 않는다 — start.sh 의 감시 루프가 Redis 재시작 시 러너를
# 다시 띄우고, 러너가 RQ_WORKER 하트비트를 남긴다(2026-09-08 운영 사고). 여기서 rq 를
# 직접 부르면 그 보호와 하트비트가 둘 다 사라진다.
worker: sh start.sh
