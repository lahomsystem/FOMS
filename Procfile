# Railway 배포용 Procfile (Quest 14)
# SocketIO를 지원하기 위해 eventlet 워커 사용
web: gunicorn --worker-class gthread --threads 4 --timeout 120 app:app
