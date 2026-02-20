# Incident RCA: Socket.IO ERR_CONNECTION_RESET 및 400 BAD REQUEST

## Incident RCA
- **Incident**: 브라우저 Network 탭에서 Socket.IO GET 요청 `net::ERR_CONNECTION_RESET`, POST 요청 `400 (BAD REQUEST)` 발생 (manager.js:108, 대상 `http://172.30.1.89:5000/socket.io/`).
- **Severity**: SEV-3 (부분 기능 장애 — 채팅/실시간 알림만 영향, 우회 가능)
- **User Impact**: 동일 LAN 내 다른 기기(172.30.1.89)에서 접속 시 Socket.IO 연결이 끊기거나 400 발생 시 실시간 알림/채팅 업데이트가 일시적으로 동작하지 않을 수 있음.

## Timeline
1. 사용자 브라우저 콘솔/Network에서 Socket.IO GET → ERR_CONNECTION_RESET, POST → 400 확인.
2. 원인 분석: 연결 리셋 후 클라이언트가 이전 세션 ID(sid)로 POST 재시도 → 서버가 해당 sid를 모름 → 400 반환.

## Hypothesis Board
1. **가설: 서버 재시작/리로더로 연결이 끊긴 뒤 stale sid로 POST**  
   - 지지: 400은 보통 engine.io "Session ID unknown"(code 1)과 함께 발생; ERR_CONNECTION_RESET은 서버/네트워크가 연결을 끊을 때 흔함.  
   - 반박: 없음.  
   - **판정: 유지 → 근본 원인으로 채택.**

2. **가설: CORS/쿠키로 인한 400**  
   - 지지: 없음 (동일 오리진 172.30.1.89:5000).  
   - 반박: 요청이 같은 호스트/포트로 가고 있음.  
   - **판정: 기각.**

3. **가설: 클라이언트·서버 프로토콜 버전 불일치**  
   - 지지: 없음 (클라이언트 4.5.4, 서버 flask-socketio 5.x — 호환).  
   - 반박: 초기 핸드셰이크가 성공한 뒤 리셋/400이 나는 패턴과 맞지 않음.  
   - **판정: 기각.**

## Rejected Hypotheses
1. CORS/쿠키 — 동일 오리진이라 해당 없음.
2. 프로토콜 불일치 — 4.5/5.x 호환, 증상은 연결 끊김 후 재시도 구간에서만 발생.

## Root Cause
- **직접 원인**: TCP 연결이 서버/네트워크 측에서 끊김(ERR_CONNECTION_RESET) → 클라이언트가 기존 **stale sid**로 계속 POST → 서버가 해당 세션을 모름 → **400 BAD REQUEST**.
- **발생 조건**: 개발 서버(debug/reloader) 재시작, LAN 불안정, 방화벽/중간 장비로 인한 연결 종료 시.
- **참고**: Socket.IO 공식 문서에서도 "Session ID unknown" 400은 주로 sticky session 미사용 또는 연결 끊김 후 잘못된 sid 재사용과 연관됨.

## Fix
- **Files**: `templates/layout.html`
- **Containment**: 없음 (기능 저하만 있고 데이터 손상 없음).
- **Why this fix**:  
  - `connect_error` 시 기존 싱글톤 소켓을 정리하고 `window.__appSocket = null`로 두어, 다음 `getAppSocket()` 호출 시 **새 핸드셰이크(새 sid)** 로 연결하도록 함.  
  - `disconnect` 시 원인이 `transport error` / `transport close` 등이면 동일하게 싱글톤을 비우고, 일정 시간 후 자동 재연결 시 새 소켓이 생성되도록 함.  
  - 이를 통해 stale sid로 반복 POST하는 구간을 줄이고, 콘솔에 한 번만 안내 메시지를 남기도록 함.
- **Validation**:  
  - 개발 서버에서 페이지 로드 후 서버 재시작(또는 연결 끊김 시뮬레이션) → 콘솔에 재연결 안내 출력 후 새 연결 수립.  
  - 채팅/알림 페이지에서 실시간 수신 다시 동작하는지 확인.

## 로컬 vs 원격(배포) 환경

| 구분 | 로컬 (run.py) | 원격 (Railway Procfile) |
|------|----------------|-------------------------|
| **실행 방식** | `socketio.run(app, debug=True, use_reloader=True)` | `gunicorn --worker-class gthread --workers 1 app:app` |
| **Socket.IO 동작** | ✅ 동작. Werkzeug 개발 서버가 Socket.IO 핸들링. | ⚠️ **현재 설정으로는 Socket.IO 미지원**. gthread WSGI만으로는 `/socket.io/` 프로토콜이 처리되지 않음. (Flask-SocketIO 프로덕션은 보통 `gevent`/`eventlet` 워커 필요) |
| **이번 증상** | ✅ **해당됨**. 리로더로 인한 연결 끊김 → stale sid → 400. LAN 접속(172.30.1.89) 시에도 동일. | ❌ **해당 없음**. 원격에서는 Socket.IO 서버가 올라가지 않아, 클라이언트가 `/socket.io/`에 연결 시도해도 실패/미연결 상태일 뿐, “연결 후 끊김 → 400” 패턴은 재현되지 않음. |
| **적용한 클라이언트 수정** | 로컬에서 연결 끊김/400 시 자동 재연결로 유효. | 원격에서 나중에 Socket.IO를 활성화(예: gevent 워커·별도 엔트리포인트)하면 동일 복구 로직이 그대로 유효함. |

**정리**: 원격에서도 Socket.IO를 쓰기 위해 Procfile을 gevent 워커로 변경함(아래 추가 조치).

**추가 조치(원격에서 Socket.IO 사용)**: Procfile을 `gunicorn -k gevent -w 1` 로 변경, `requirements.txt`에 `gevent` 추가. layout·채팅 페이지는 `config.SOCKETIO_AVAILABLE` 기준으로 클라이언트 로드. 다중 사용자 실시간 알림/채팅이 원격에서도 동작.

## Prevention
- **Rule/Agent/Hook**: 기존 `07-clientsocket` 체크리스트에 "연결 오류 시 싱글톤 초기화·재연결" 패턴 유지.
- **Runbook/Docs**:  
  - 개발 시 `debug=True`/reloader 사용 시 Socket.IO 연결이 가끔 끊기는 것은 정상일 수 있음.  
  - 400이 반복되면 브라우저 새로고침(F5)으로 새 핸드셰이크를 받도록 안내 가능.
- **Tests**: (선택) E2E에서 서버 재시작 후 클라이언트 재연결 검증.
