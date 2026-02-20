# Railway 배포용 Procfile (Quest 14)
# Socket.IO 지원: gevent 워커 1개 (다중 워커 시 sticky session 필요)
web: gunicorn -k gevent -w 1 --max-requests 1000 --timeout 120 app:app
