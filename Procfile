# Railway 배포용 Procfile (Quest 14)
# SocketIO를 지원하기 위해 eventlet 워커 사용
web: gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT --timeout 120 app:app
