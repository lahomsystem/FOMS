# 채팅 SyntaxError (Unexpected token ')') 전수 리뷰 및 수정

## 원인
- 사용자/API 데이터가 **템플릿 리터럴(백틱)** 또는 **onclick 단일따옴표 문자열** 안에 그대로 들어가면, 데이터에 포함된 `'` 또는 `` ` ``가 문자열을 조기 종료시켜 `Unexpected token ')'` 발생.

## 수정 요약

### 1. `escapeJsString` 강화 (chat_scripts_utils.html)
- **추가 이스케이프**: 백틱 `` ` `` → `\``
- 단일따옴표·백슬래시에 더해, onclick/템플릿 리터럴 안에서도 안전하도록 처리.

### 2. 사용자 데이터가 들어가는 템플릿 리터럴 제거 (chat_scripts_modals.html)
- `selectOrderForRoom` 내부:  
  `textContent = \`주문 #${orderId} - ${customerName} (${product})\``  
  → `textContent = '주문 #' + orderId + ' - ' + customerName + ' (' + product + ')';`  
- `customerName`/`product`에 백틱이 있어도 구문이 깨지지 않도록 문자열 연결로 변경.

### 3. 메시지 메타에 escapeHtml 적용 (chat_scripts_messages.html)
- `userName`을 그대로 템플릿에 넣던 부분 → `escapeHtml(userName)` 사용.
- 이미지/비디오/파일 링크의 `src`/`href`에 `escapeHtml(...)` 적용해 `"`·`` ` ``·`<` 등으로 속성/템플릿이 깨지지 않도록 함.

### 4. 알림 썸네일 URL 이스케이프 (chat_scripts_notifications.html)
- `attachment.thumbnail_url`을 그대로 `src`에 넣던 부분 → `escapeHtml(attachment.thumbnail_url || '')` 사용.

### 5. order/room ID 숫자 강제 (chat_scripts_rooms.html)
- `safeOrderId = Number(order.id) || 0`, `safeRoomId = Number(room.id) || 0` 도입.
- 위젯/헤더의 모든 `onclick`·`data-order-id`·`href`에 `order.id`/`room.id` 대신 이 값 사용.
- `renderRooms`에서도 `rid = Number(room.id) || 0` 사용.
- status 옵션 폴백은 `defaultStatusOption` 변수로 분리 후 `${statusOptions}`만 삽입.

## 검토한 파일 (누락 없이)
- chat_scripts_utils.html — escapeHtml(백틱), escapeJsString(백틱 추가)
- chat_scripts_rooms.html — safeRoomId/safeOrderId/rid, escapeJsString(room.name), statusOptions
- chat_scripts_modals.html — selectOrderForRoom textContent, escapeJsString(order.*), order.id
- chat_scripts_messages.html — userName, filename, URL(src/href) escapeHtml
- chat_scripts_notifications.html — thumbnail_url escapeHtml
- chat_scripts_extras.html — result.*는 이미 escapeHtml 적용
- chat_scripts_core.html, dom.html, helpers.html, file.html, lightbox.html — 사용자 데이터 직접 삽입 없음

## 추가 수정 (SyntaxError 지속 시)
- **chat_scripts_extras.html:**  
  - 전역 검색 결과 행을 템플릿 리터럴 대신 **문자열 연결**로 생성, `room_id`/`message_id` **숫자 강제**.  
  - **파일 말미의 `</script>` 제거** — 상위 `<script>` 블록을 조기 종료해 그 다음 줄이 JS가 아닌 HTML로 해석되며 `Unexpected token ')'` 유발하던 원인.

## 재발 방지
- **onclick/onchange 등 인라인 핸들러에 넣는 모든 사용자/API 문자열** → `escapeJsString(...)` 사용.
- **HTML/속성에 넣는 모든 사용자/API 문자열** → `escapeHtml(...)` 사용.
- **템플릿 리터럴에 사용자 데이터**를 넣을 때는 반드시 위 둘 중 하나 적용하거나, 문자열 연결(`+`)로 삽입.
- **partial 내부에 `</script>` 태그 금지** — 상위 script가 조기 종료됨.
