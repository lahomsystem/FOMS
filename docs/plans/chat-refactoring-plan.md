# 채팅 기능 전반 리팩토링 계획서

**작성:** Grand Develop Master 지휘 하에 전체 코드 리뷰 기반  
**목표:** SyntaxError 근본 제거 및 유지보수 가능한 채팅 아키텍처 확립  
**상태:** Phase 1·2 실행 완료 (이벤트 위임 도입) + 스크립트 외부화로 SyntaxError 근본 차단 (2026-02-28)

---

## 1. 현상 정리

### 1.1 반복 증상
- **증상:** `chat:3530 Uncaught SyntaxError: Unexpected token ')' (at chat:3530:11)`
- **결과:** 채팅방 목록 로딩 실패, 채팅 진입 불가
- **원인 후보 (리뷰 결과):**
  1. **조기 `</script>` 종료:** `chat_scripts_extras.html` 말미에 있던 `</script>`가 상위 `<script>` 블록을 조기 종료시켜, 그 다음 줄이 JS가 아닌 HTML로 해석되며 파서 에러 유발 → **즉시 제거 완료**
  2. **동적 데이터의 인라인 핸들러 삽입:** `onclick="fn(${id}, '${name}')"` 형태로 사용자/API 데이터를 넣을 때, `'`·백틱·`"` 미이스케이프 시 문자열 조기 종료 → `)`가 예기치 않은 토큰으로 보고됨
  3. **여러 partial에 동일 패턴 분산:** rooms, modals, messages, extras 등에서 각각 이스케이프·숫자 강제를 적용했으나, 한 곳만 빠져도 동일 에러 재발

### 1.2 구조적 문제
| 항목 | 내용 |
|------|------|
| **인라인 핸들러 과다** | `onclick`/`onchange`/`onblur`에 동적 값을 직접 삽입하는 패턴이 30곳 이상 |
| **이스케이프 책임 분산** | `escapeHtml`/`escapeJsString`을 호출하는 곳이 템플릿/문자열 결합 곳곳에 흩어져 있어 누락·불일치 가능 |
| **스크립트 조각화** | 11개 partial이 한 `<script>` 안에 단순 결합되어, 라인 번호·스코프·순서 의존이 문서화되지 않음 |
| **테스트 부재** | 채팅 전용 단위/통합 테스트 없음, 리그레션 검증 불가 |

---

## 2. 전체 코드 리뷰 요약

### 2.1 채팅 관련 파일 (19개)
- **진입점:** `templates/chat.html` (237줄), `templates/partials/chat_scripts.html` (스크립트 번들)
- **스크립트 partial (11개):** core, lightbox, utils, notifications, helpers, dom, **rooms**, **messages**, file, **modals**, **extras**  
  (굵은 4개: 동적 HTML 생성·인라인 핸들러 다수)
- **스타일:** `partials/chat_styles.html`
- **백엔드:** `apps/api/chat/routes.py`, `services/storage.py` (업로드 등)

### 2.2 동적 HTML 생성·인라인 핸들러 위치
| 파일 | 역할 | 위험 패턴 |
|------|------|-----------|
| **rooms** | 채팅방 목록·헤더·주문 위젯 | `innerHTML` + onclick/onchange/onblur에 room.id, order.id, room.name 등 |
| **modals** | 방 생성·주문 검색/연결·초대·삭제 | 주문 목록·사용자 목록 `innerHTML` + onclick에 order.id, customer_name, product |
| **messages** | 메시지·첨부 렌더링 | 메시지별 HTML + 다운로드 onclick에 storageKey, filename |
| **extras** | 전역 검색 결과 | 검색 결과 행별 onclick에 result.room_id, result.message_id (템플릿 리터럴 + 조기 `</script>` → **수정 완료**) |
| **notifications** | 알림 팝업 | 알림 DOM에 roomName, senderName, messageContent 등 |
| **file** | 미리보기·업로드 UI | 미리보기 innerHTML에 imageUrl, videoUrl, filename |

### 2.3 스크립트 외부화 (SyntaxError 근본 차단, 2026-02-28)
- **원인:** 인라인 `<script>` 블록 내부에 동적/긴 JS가 있으면, HTML 파서가 문자열/주석 안의 `</script>`를 스크립트 종료로 잘못 해석하거나, 라인/인코딩 이슈로 `Unexpected token ')'` 발생 가능.
- **조치:** 채팅 스크립트를 **외부 JS**로 분리하여 같은 증상 재발 차단.
  1. **라우트:** `GET /chat/scripts.js` 추가 (`@login_required`, `application/javascript`).
  2. **번들 템플릿:** `partials/chat_scripts_bundle.html` (11개 partial include만, `<script>` 래퍼 없음).
  3. **채팅 페이지:** `chat.html`에서 `{% include 'partials/chat_scripts.html' %}` 제거 → `<script src="{{ url_for('chat.chat_scripts_js') }}"></script>` 로 대체.
  4. **dom.html:** 외부 스크립트 지연 로드 시 `DOMContentLoaded`가 이미 발생했을 수 있으므로, `document.readyState === 'loading'`이면 리스너 등록, 아니면 `init()` 즉시 실행하도록 래핑.

### 2.4 적용한 즉시 수정 (이번 세션)
1. **extras:**  
   - `performGlobalSearch` 결과 행을 템플릿 리터럴 대신 **문자열 연결**로 생성  
   - `room_id`/`message_id` **숫자 강제**  
   - **`</script>` 태그 제거** (상위 script 조기 종료 원인 제거)
2. **rooms / modals / messages:**  
   - 이전 세션에서 이미 onclick/onchange/onblur를 **변수 조립 + 문자열 연결**로 정리, ID 숫자 강제, `escapeJsString`(백틱 포함) 적용

---

## 3. 리팩토링 방향 (GDM 원칙 반영)

### 3.1 원칙
- **단순화 우선:** “인라인에 이스케이프 더 넣기”보다 **“인라인 핸들러 제거”**로 문제 제거
- **구조적 의심:** 같은 SyntaxError가 반복되면 **패턴(동적 값 인라인 삽입) 자체를 제거**
- **오컴의 면도날:** Server → HTML → JS(문자열로 삽입) 3단계 대신 **Server → JS(데이터만) → 이벤트 위임** 2단계 지향

### 3.2 목표 아키텍처
1. **이벤트 위임:**  
   - 채팅방 목록·검색 결과·주문 목록·메시지 목록 등 **동적 리스트**는 한 부모에서 `click` 수신  
   - `data-room-id`, `data-order-id`, `data-message-id`, `data-action` 등 **data 속성만** 넣고, 핸들러에서는 `event.target.closest('[data-...]')`로 읽기만 함
2. **동적 값은 data 속성·텍스트로만:**  
   - `onclick="fn(123, 'name')"` 제거  
   - 표시용 텍스트는 `textContent` 또는 `escapeHtml`로만 삽입
3. **스크립트 구조 정리:**  
   - 가능하면 1개 `chat.js` 번들로 통합하거나, partial 수를 줄이고 로드 순서·의존성을 문서화

---

## 4. Phase별 실행 계획

### Phase 1: 안정화 (즉시·단기)
| 단계 | 작업 | 산출물 |
|------|------|--------|
| 1.1 | extras `</script>` 제거 및 검색 결과 문자열 연결·숫자 강제 적용 | **완료** |
| 1.2 | 채팅 페이지 수동 회귀 테스트: 진입 → 목록 로드 → 방 선택 → 메시지 전송 → 검색 | 체크리스트 |
| 1.3 | `docs/plans/chat-syntax-error-review.md`에 “extras 조기 </script> 제거” 및 “전역 검색 결과 생성 방식 변경” 반영 | 문서 갱신 |

### Phase 2: 이벤트 위임 도입 (중기)
| 단계 | 작업 | 산출물 |
|------|------|--------|
| 2.1 | **rooms:** `#rooms-list`에 이벤트 위임, `[data-room-id]` 클릭 → `selectRoom(data-room-id)` | rooms 리팩터 |
| 2.2 | **rooms:** 헤더 버튼(이름 수정·연결·초대·삭제)을 `[data-action][data-room-id]` 등으로 통일, 위임 핸들러에서 분기 | 헤더 버튼 위임 |
| 2.2.1 (추가) | **rooms:** 주문 정보 위젯 내의 상태 변경(`onchange`), 담당자 지정(`onblur`) 등 모든 인라인 이벤트를 제거하고 부모 테이블에서 `change`, `focusout` 이벤트 위임으로 수신하여 처리 | 주문 위젯 리팩터 |
| 2.3 | **modals:** 주문 검색/연결 결과 리스트를 `[data-order-id]` + `[data-action="select-order"]` 등으로만 표시, 위임으로 `selectOrderForRoom`/`connectOrderToRoom` 호출 | modals 리팩터 |
| 2.4 | **messages:** 다운로드 버튼을 `[data-storage-key][data-filename]` + 위임으로 `downloadChatImage` 호출 | messages 리팩터 |
| 2.5 | **extras:** 검색 결과 행을 `[data-room-id][data-message-id]` 등으로만 구성, 위임으로 `selectRoom`/`selectRoomAndHighlight` 호출 | extras 리팩터 |

### Phase 3: 스크립트·문서 정리 (중장기)
| 단계 | 작업 | 산출물 |
|------|------|--------|
| 3.1 | partial 의존성·로드 순서를 `chat_scripts.html` 주석 또는 `docs/context/DECISIONS.md`에 명시 | 문서 |
| 3.2 | (선택) 300줄 이하 단위로 partial 재분할 또는 단일 `chat.bundle.js` 생성 검토 | 구조 개선안 |
| 3.3 | 채팅 관련 Rule: “동적 HTML에 사용자/API 데이터 넣을 때 data 속성 + 이벤트 위임 사용, 인라인 onclick에 문자열/숫자 삽입 금지” | `.cursor/rules/` |

### Phase 4: 검증·회귀 방지 (장기)
| 단계 | 작업 | 산출물 |
|------|------|--------|
| 4.1 | Flask test_client로 `/chat` 200 및 채팅방 목록 API 200 검증 | 테스트 1건 |
| 4.2 | (선택) Playwright 등으로 “채팅 진입 → 목록 클릭 → 메시지 전송” 시나리오 자동화 | E2E 시나리오 |

---

## 5. 성공 기준
- 채팅 페이지 진입 시 콘솔에 **SyntaxError 미발생**
- 채팅방 목록 로드·선택·메시지 전송·전역 검색·주문 연결/연결해제가 **기존과 동일하게 동작**
- 이후 동적 데이터(이름·설명·고객명 등)가 추가되어도 **인라인 핸들러에 문자열을 넣지 않음**으로 재발 방지

---

## 6. 참조
- `docs/plans/chat-syntax-error-review.md` — 이스케이프·즉시 수정 내역
- `.cursor/agents/grand-develop-master.md` — 문제 해결 프로토콜·단순화 우선 원칙
- `templates/partials/chat_scripts*.html` — 대상 partial 목록
