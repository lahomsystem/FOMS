# 긴급 호출 — 맨 위 줄 ⚡ + 주문 선택(또는 주문 없이) SPEC

- 작성: 2026-10-01 · 상태: **승인 (2026-10-01)**
- 근거 목업: https://claude.ai/artifact/GXep95iGUL8yGzwjhcEoVa (심플 안 — 스테이징 실제 화면에 얹어 찍음)
- 선행: `51a8858fe` (도면 PC 긴급 호출 선택 표시 결함 + erp-pro.css 닫는 괄호 누락, deploy 반영)

## 1. 사용자 결정 (2026-10-01)

1. 긴급 호출 버튼은 **모든 화면 맨 위 줄, "내 할 일만" 아이콘 왼쪽**에 ⚡ 아이콘 하나. 새 줄·고정 자리를 차지하지 않는다.
2. 모바일도 같은 자리(모바일 셸 머리줄, 내 할 일 왼쪽). 누르면 아래에서 시트가 올라온다.
3. 창은 심플하게: 주문 한 줄 · 팀 버튼 한 줄 · 사람 이름 · 사유 칸 · `○○에게 보내기` 버튼 하나.
4. **주문은 추가할 수 있고, 주문 없이도 부를 수 있다.**

## 2. 지금 상태 (조사 결과)

| 항목 | 지금 | 근거 |
|---|---|---|
| 긴급 호출 API | 주문에 묶여야만 받음 `POST /erp/api/orders/<id>/urgent-mention` | `foms/api/notifications/__init__.py:933` |
| 호출 대상 목록 | 주문에 묶임 `GET /erp/api/orders/<id>/urgent-targets` (실제로는 주문과 무관한 활성 사용자 전원) | 같은 파일 `:760` |
| 알림 표 | `Notification.order_id` 는 이미 **nullable** | `models.py:1452` |
| 주문 없는 알림 선례 | 공지 발송이 `order_id=None` 으로 만든다 | `__init__.py` `api_notifications_send` |
| 폰 푸시 링크 | 주문 없으면 `/erp` 로 | `push_sender._deep_link` |
| 알림 목록 링크 | 주문 없으면 링크 없음(목록 안에서 읽음) | `mobile-notification.js deepHref` |
| 진입점 3곳 | 도면 PC 창(`drawing-urgent-call-pc.js`) · 모바일 시트(`urgent-call-sheet.js`) · 대시보드 주문 상세 "동료 호출" 줄(`erp-dashboard-detail-dom.js:540`) | |
| 대시보드 "동료 호출" 결함 | "메시지 (선택)" 인데 서버는 사유 필수 → 사유 없이 누르면 항상 400. 클릭 바인딩이 상세 안 첫 `button[data-order-id]` 를 잡는다 | `erp-dashboard-detail-dom.js:549·622` |

결론: 저장·배달 쪽은 주문 없는 알림을 이미 처리한다. 바뀌는 것은 **받는 API 2개 + 화면**이다. DB 마이그레이션 없음.

## 3. 서버 변경

### 3.1 서비스 한 곳으로 모으기
`foms/services/notifications/urgent_call.py` (신규) — `send_urgent_call(db, sender, target_user_id, message, order=None) -> Result`.
지금 `api_order_urgent_mention` 본문(검증 · 한 tx 알림+수신자 상태+이벤트+SIDEFX outbox · 감사 로그 · 배지 캐시 · 실시간 표시)을 그대로 옮긴다. 차이는 `order=None` 일 때뿐:

| | 주문 있음 (지금과 같음) | 주문 없음 (신규) |
|---|---|---|
| 보내는 사람 검사 | `user_can_read_order` | 로그인 활성 사용자 |
| 제목 | `[긴급 멘션] ○○님이 #id 고객 주문에서 호출했습니다` | `[긴급 호출] ○○님이 호출했습니다` |
| `Notification.order_id` | 주문 id | `None` |
| 횟수 제한 | 보낸 사람+주문당 시간당 5회 (지금 그대로) | **없음** (사용자 결정 2026-10-01) |
| 감사 로그 | `describe_order_action(... URGENT_MENTION_SENT)` | `action="URGENT_MENTION_SENT", target_type="user", target_id=받는사람` |
| 폰 푸시 누르면 | 주문 상세 | `/erp` (지금 규칙 그대로) |

검사·문구(사유 1..500자, 자기 자신 금지, 비활성 422, 없는 사용자 404)는 둘 다 같다.

### 3.2 새 API
- `GET /erp/api/urgent-targets` — 주문 없이 호출 대상 목록(활성 사용자, 자기 제외, 팀 순→이름 순, `team_label`). 지금 주문용 목록과 같은 함수를 쓴다.
- `POST /erp/api/urgent-call` — 본문 `{target_user_id, message, order_id?}`. `order_id` 가 있으면 주문을 찾아 주문 있음 규칙, 없으면 주문 없음 규칙. `@login_required` + `@notification_write_guard`. 응답 `{success, message}` (지금 엔드포인트와 같은 모양).
- 지금 두 엔드포인트(`/orders/<id>/urgent-targets`, `/orders/<id>/urgent-mention`)는 **남겨 두고** 같은 서비스를 부르게 바꾼다(호환, 캐시된 옛 JS 대비). 진입점이 모두 새 창으로 옮겨진 뒤 다음 정리 묶음에서 지운다.

### 3.3 주문 고르기 (사용자 요청: 이름 · 전화번호 일부 · 주소 등으로 검색)
새 API 없이 기존 통합 검색 `GET /api/foms/search?q=&group=all` 을 쓴다(로그인, 시공팀 범위 제한 이미 있음). 이 검색이 이미 찾는 것:
- 고객 이름 (structured_data `parties.customer.name` → `Order.customer_name`)
- 전화번호 일부 — 숫자 4자리 이상은 `erp_phone_digits` 인덱스 contains (`foms/services/foms_unified_search.py:305`)
- 주소 — 단어 순서 무관 토큰 교집합 (`:75`)
- 주문번호 · 제품 · 담당자
`customer` 버킷과 `order` 버킷을 합치고 `order_id` 로 중복을 뺀 뒤 최대 8줄. 한 줄 = 고객명 + 단계 배지 / `#번호 · 전화 · 주소`(한 줄 말줄임). 입력 200ms 디바운스, 2글자부터.
스테이징 확인(2026-10-01): `0000`(전화 일부) · `테헤란`(주소) · `CLAUDE`(이름) 모두 테스트 주문이 나온다.

## 4. 화면 변경

### 4.1 공용 창 하나
- `templates/partials/shared/urgent_call.html` (신규) + `static/js/foms/urgent-call.js` (신규). 앱 셸에 한 번 넣는다.
- 폭 992px 이상 = 가운데 창(Bootstrap modal, 폭 420px). 그보다 좁으면 = 아래에서 올라오는 시트(offcanvas-bottom). 안의 내용은 같다.
- 내용(위에서 아래로):
  1. 주문 줄: 골라진 주문 `#번호 고객명 ×` / 없으면 점선 `+ 주문 추가 (안 해도 돼요)` — 누르면 검색 칸이 펼쳐진다. 검색 칸 안내 글(placeholder)은 `이름, 전화, 주소 등 입력`(사용자 지정 2026-10-01). 고른 주문 옆 `×` 로 빼면 "주문 없이". 처음 상태는 지금 보던 주문(있으면) 또는 비어 있음.
  2. 팀 버튼 한 줄: CS · 영업 · 도면 · 시공 · 회계 (기타는 맨 끝, 인원 있을 때만).
  3. 사람 이름 버튼(직급 글자 없음). 고르면 빨간 바탕 + ✓ (`.foms-urgent-pick.is-selected`, 오늘 만든 클래스 재사용).
  4. 사유 칸(필수, 500자).
  5. 맨 아래 버튼: 사람 없음 = `받을 사람을 골라 주세요`(잠김) · 사유 없음 = `사유를 적어 주세요`(잠김) · 준비됨 = `구범진에게 보내기`.
- 보낸 뒤: 창 닫고 토스트 `구범진님에게 보냈어요`. 실패: 창 안에 서버 문구.
- 주문 미리 고르기: 버튼(또는 페이지)이 `data-urgent-order-id`·`data-urgent-order-label` 을 실으면 그 주문으로 연다. 전달 취소 경고 흐름의 `data-urgent-team`·`data-urgent-message` 미리 채우기도 그대로 받는다.
- 인라인 스타일 없음 → `erp-pro.css`. 리스너는 document 위임 + `window.__*_BOUND` 한 번 가드(G4).

### 4.2 ⚡ 버튼 자리
- PC: `templates/partials/shared/layout_nav.html` 의 `#global-mine-only-btn` 왼쪽. 옆 아이콘과 같은 크기, 빨간색.
- 모바일: `templates/partials/shared/erp_mobile_shell_header.html` 내 할 일 왼쪽. 머리줄 grid 칸을 하나 늘린다(지금 `44px 1fr 44px 44px 44px` → 칸 하나 추가, 각 버튼 `grid-column` 재배치).
- 주문 화면에서 누르면 그 주문이 미리 골라진다: 대시보드 주문 상세가 펼쳐져 있으면 그 주문, 주문 수정·도면 작업실은 페이지 주문.

### 4.3 옛 진입점 정리
- 대시보드 주문 상세 "동료 호출" 줄: **지운다**(사유 필수 결함·첫 버튼 바인딩 결함도 함께 사라짐).
- 도면 작업실 PC `[긴급 호출]` 버튼·전달 취소 경고의 `영업에게 먼저 알리기`: 공용 창을 연다. `#dwUrgentCallModal` 과 `drawing-urgent-call-pc.js` 의 긴급 호출 부분 삭제(전달 취소 경고 시트 부분은 남김).
- 모바일 주문 상세·도면 모바일의 `[data-foms-urgent-call]` 버튼: 공용 창을 연다. `erp_mobile_urgent_call_panel.html`·`urgent-call-sheet.js` 삭제.

## 5. 결정 (사용자 2026-10-01)

1. 주문 없는 호출 횟수 제한: **없음**. 주문 있는 호출은 지금처럼 보낸 사람+주문당 시간당 5회.
2. ⚡ 를 보는 사람: **로그인한 모든 직원**.
3. 주문 고르기에 "최근에 본 주문" 목록: **넣지 않음** — 지금 보던 주문 + 검색만.

## 6. 검증

- 서버(pytest): 주문 없음 성공(알림 `order_id is None`, outbox 1행, 감사 로그 1행) · 주문 있음은 지금 테스트(`tests/domains/test_urgent_call.py`) 전부 통과 · 사유 빈칸 400 · 자기 자신 400 · 비활성 422 · 없는 사용자 404 · 주문 없음은 연속 발송해도 429 없음 · 옛 엔드포인트가 같은 서비스로 같은 결과.
- 화면(Node 동작 테스트, 기존 `drawing_customer_js_harness` 방식): 주문 미리 고르기 · 주문 빼기 → 요청 본문에 `order_id` 없음 · 버튼 글자 3상태 · 보내기 성공 시 닫힘.
- 실화면(스테이징, claude_master): PC·모바일 ⚡ → 주문 있음/없음 각각 **자기 테스트 계정끼리** 실제 발송 1회(실직원에게 보내지 않는다) · 알림 목록·폰 푸시 링크 확인 · 대시보드 상세에 "동료 호출" 줄 없음 · 도면 작업실 전달 취소 경고 흐름.
- `pre_push_smoke.ps1` exit 0 → deploy → CI 초록 → `check_deploy_drift.py`.

## 7. 순서

1. 서버: 서비스 추출 + 새 API 2개 + 옛 API 위임 + 테스트.
2. 공용 창 + ⚡ (PC·모바일).
3. 옛 진입점 3곳을 공용 창으로 바꾸고 옛 창·JS 삭제.
4. 스테이징 실화면 확인 → 운영은 사용자 요청 시 이 묶음의 커밋만 승격.
