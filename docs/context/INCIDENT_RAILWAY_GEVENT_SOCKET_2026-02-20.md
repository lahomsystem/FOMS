# Incident: Railway Gunicorn gevent + Socket.IO ConcurrentObjectUseError

## 요약
- **증상**: Railway 배포 로그에서 `Autorestarting worker` 후 `Worker graceful timeout`, 이어서 `gevent.exceptions.ConcurrentObjectUseError: This socket is already used by another greenlet` 발생, 워커 종료 후 재기동.
- **영향**: 해당 요청 실패, 일시적 연결 끊김. 워커가 재시작되어 서비스는 복구됨.
- **Severity**: SEV-3 (간헐적 오류, 자동 복구)

## 원인
- **Gunicorn**: `-k gevent` (gevent 워커) 사용 → 프로세스 내 소켓이 gevent 그린렛으로 처리됨.
- **Flask-SocketIO**: `async_mode='threading'` 으로 초기화 → 같은 연결 소켓을 스레드에서도 사용.
- 워커 재시작(graceful) 시점에 **같은 소켓을 gevent와 threading이 동시에 사용**하려 하면서 `ConcurrentObjectUseError` 발생.

## 수정 사항
- **app.py**: Redis 사용 시(프로덕션) Socket.IO를 `async_mode='gevent'` 로 설정해 gunicorn 워커와 동일한 모드 사용.
- **선택 오버라이드**: `SOCKETIO_ASYNC_MODE=threading` 설정 시 기존처럼 threading 유지(로컬/Windows 호환용).

## 검증
- Railway 재배포 후 동일 워커 재시작 구간에서 `ConcurrentObjectUseError` 미발생 확인.
- HTTP 로그: `/erp/api/notifications/badge` 반복 200 → 정상 폴링. 필요 시 폴링 간격 완화 검토 가능.
- Redis `TCP_INVALID_SYN`: 워커 재기동 시 일시적 연결 재설정으로 보이며, 수정 후 관찰.

## 참고
- Procfile/railway.toml: `gunicorn -k gevent -w 1 --max-requests 1000 --timeout 120 app:app` 유지.
- 기존 INCIDENT_SOCKETIO_CONNECTION_2026-02-20.md: 로컬 stale sid / 400 복구 로직과 별개, 이번 건은 서버 측 async 모드 불일치.
