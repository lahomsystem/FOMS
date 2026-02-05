# Railway 배포용 Procfile (Quest 14)
# SocketIO를 지원하기 위해 eventlet 워커 사용
web: gunicorn --worker-class gthread --workers 4 --threads 5 --max-requests 1000 --timeout 120 app:app
