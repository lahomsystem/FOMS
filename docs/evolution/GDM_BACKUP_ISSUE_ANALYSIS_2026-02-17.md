# GDM 백업 이슈 분석 보고서 (2026-02-17)

**요청**: 백업 시 문제 발생 — GDM이 가용 자원으로 현재 상태 파악 및 문제 분석  
**분석 범위**: 스크린샷(Socket.IO 오류), 백업 플로우, DB·서버 상태

---

## 1. 결론 (비전문가용)

- **백업 기능 자체**는 Socket.IO를 쓰지 않습니다. 데이터베이스와 파일 백업은 **REST API + 폴링**으로 동작합니다.
- 스크린샷에 보이는 **빨간 오류(Socket.IO 로드 실패, 400 Bad Request)**는 **채팅/실시간 알림용 연결**이 실패한 것이며, **백업 성공 여부와는 별개**입니다.
- 다만, **관리자 페이지에서도 전역 Socket.IO가 자동으로 연결을 시도**하기 때문에, 백업 버튼을 누르는 그 페이지에서 위 오류가 콘솔에 뜨면 “백업할 때 문제가 있다”고 느낄 수 있습니다.
- **권장**: (1) 관리자·백업 페이지에서는 Socket.IO 연결을 시도하지 않도록 제한하고, (2) 백업이 실제로 실패했는지는 “백업 상태 새로고침” 결과로 확인하는 것을 안내합니다.

---

## 2. 현재 상태 파악 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| 백업 실행 방식 | REST API | `POST /api/simple_backup` → 백그라운드 스레드 → `GET /api/backup_status` 폴링 |
| Socket.IO 사용처 | 채팅·실시간 알림 | 백업 API는 미사용 |
| DB 연결 | 정상 | Postgres MCP: connections 8, idle 0 |
| 최근 백업 파일 | 존재 | tier1/tier2에 `database_backup_20260217_125940.sql` 등 |
| 전역 Socket.IO 로드 | layout.html | 로그인 시 **모든 페이지**에서 스크립트 로드 및 연결 시도 |

---

## 3. 스크린샷 오류 분석

콘솔에 보인 두 가지:

1. **`socket.io/?E10=4&tra...` → net::ERR_CONNECTION_RESET**  
   - Socket.IO 리소스 요청 중 **연결이 끊김** (서버 종료, 타임아웃, 방화벽/프록시, 또는 일시적 네트워크 문제).
2. **동일 URL → 400 (BAD REQUEST)**  
   - Socket.IO **핸드셰이크** 단계에서 서버가 요청을 거부.  
   - 흔한 원인: CORS, **세션 만료/불일치**, 프록시 설정, 클라이언트/서버 버전 불일치.

**FOMS 코드 기준:**

- `app.py`: Socket.IO는 `cors_allowed_origins` 설정됨. `connect` 시 `session.get('user_id')` 없으면 `return False`로 **연결 거부** → 클라이언트 측에서 400으로 보일 수 있음.
- `layout.html`: 로그인 사용자(`current_user`)일 때만 Socket.IO 스크립트를 넣고, **즉시 `getAppSocket()`** 호출로 전역 연결 시도.  
  → **관리자 페이지(백업 버튼 있는 페이지)에서도 동일하게 연결 시도** → 실패 시 콘솔에 위 오류 표시.

즉, “백업을 실행하는 페이지”와 “Socket.IO가 실패하는 페이지”가 같아서, **백업 문제로 오인**하기 쉽습니다.

---

## 4. 백업 플로우 (재확인)

```
[사용자] 관리자 > "시스템 백업 실행" 클릭
    → confirm 후 fetch('POST', '/api/simple_backup')
[서버]  백업이 이미 실행 중이면 → 200 + backup_in_progress: true
        아니면 → _backup_state["running"] = True, 스레드에서 SimpleBackupSystem().execute_backup() 실행
        → 즉시 200 + backup_started: true
[클라이언트] 4초 간격으로 /api/backup_status 폴링 (최대 30회)
    → backup_in_progress false + last_backup_result 또는 last_backup_error로 완료/실패 표시
```

- **타임아웃/연결 끊김 방지**: 백업은 **백그라운드 스레드**에서 실행되며, HTTP 요청은 곧바로 끝나므로 `ERR_CONNECTION_RESET`이 백업 **로직**을 중단시키지는 않습니다.
- 단, **같은 탭에서 전역 Socket.IO**가 연결을 시도하고, 그때 서버가 바쁘거나 세션이 만료되면 Socket.IO만 실패하고, 그 에러가 “백업할 때 나는 오류”로 보일 수 있습니다.

---

## 5. 권장 조치

### 5.1 (권장) 관리자/백업 페이지에서 Socket.IO 연결 생략

- **목적**: 백업·관리자 페이지에서는 채팅이 필요 없으므로, 여기서는 Socket.IO 스크립트 로드 및 `getAppSocket()` 호출을 하지 않습니다.
- **효과**: 해당 페이지에서 Socket.IO 관련 `ERR_CONNECTION_RESET`, `400 Bad Request`가 콘솔에 뜨지 않아 “백업 시 문제”로 오인할 가능성이 줄어듭니다.
- **방법 예시**:  
  - `layout.html`에서 Socket.IO 블록을 “채팅/알림이 필요한 라우트”에서만 렌더하도록 조건 추가(예: `request.endpoint == 'chat'` 또는 전용 변수 `socketio_load_on_page`),  
  - 또는 관리자/백업 전용 레이아웃을 두고 그쪽에는 Socket.IO 스크립트를 포함하지 않음.

### 5.2 서버 측 Socket.IO 400 원인 점검 (선택)

- **엔진/핸드셰이크 로깅**:  
  `SocketIO(app, ..., engineio_logger=True, logger=True)` 로 400이 나오는 순간의 로그를 확인.
- **connect 거부 로그**:  
  `"[SocketIO] 인증되지 않은 연결 시도"` 가 자주 찍히면, 해당 요청에서 세션이 비어 있는지(쿠키·SameSite·도메인) 확인.
- **세션 타임아웃**:  
  백업 등으로 오래 머물 때 세션 만료되면 Socket.IO 핸드셰이크가 실패할 수 있음. 필요 시 세션 연장 또는 “재로그인 안내” 정책 검토.

### 5.3 사용자 확인 사항 (안내용)

- 백업 **실제 성공 여부**는 다음으로 확인하는 것이 정확합니다.  
  - “백업 상태” 영역 **새로고침** 후  
  - “마지막 백업 결과” / “마지막 백업 오류” 메시지 확인.  
- 콘솔에만 Socket.IO 오류가 있고, 위 “백업 상태”에는 성공으로 나온다면 **백업은 정상**이고, 오류는 채팅/실시간 연결 실패로 보면 됩니다.

---

## 6. 요약 표

| 구분 | 내용 |
|------|------|
| **백업 자체** | REST + 폴링, Socket.IO 미사용. DB 연결 정상, 최근 백업 파일 존재. |
| **스크린샷 오류** | Socket.IO(채팅/알림) 연결 실패 — ERR_CONNECTION_RESET, 400 Bad Request. |
| **연결고리** | 관리자 페이지도 layout으로 전역 Socket.IO 연결 시도 → 실패 시 콘솔에 오류 → “백업 시 문제”로 오인 가능. |
| **권장** | (1) 관리자/백업 페이지에서 Socket.IO 로드·연결 생략. (2) 백업 성공 여부는 “백업 상태 새로고침”으로 확인하도록 안내. (3) 필요 시 서버에 engineio/logger 켜서 400 원인 상세 확인. |

---

**주문·상태 저장/복원 더블체크**: 별도 문서 `docs/evolution/BACKUP_RESTORE_VERIFICATION.md`에서 주문 건 + status/original_status/cabinet_status/structured_data 포함 여부 및 복원 방식을 검증·기록함.

*문서 생성: GDM 프로토콜에 따른 가용 자원(코드베이스 grep/read, Postgres MCP, sequential-thinking, 웹 검색) 종합 분석.*
