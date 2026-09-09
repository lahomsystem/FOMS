# 도면방 채널톡 PUSH 신설 — 워커 브리프 (2026-09-09)

## 0. 무엇을 만드는가

도면 워크벤치 상세와 도면 마법사 두 화면에 **[도면방 PUSH]** 버튼을 만든다. 누르면 그 주문의
**현재 전달본 도면 파일 전부**를 채널톡 **도면방 그룹 230331** 로 보낸다. 재전송(수정 push)
흐름은 기존 PUSH 와 동일하다(변경 내용 입력 → change_log 누적).

사용자 확정 사항(재논의 금지):
- 보낼 파일 = `structured_data['drawing_current_files']` 에 있는 **현재 전달본 전부**.
  마법사 pending(전달 대기)은 보내지 않는다.
- 보낼 방 = 도면방 `230331`. 지금 코드의 `push_kind='drawing'`(그룹 229625)은 **발주 PUSH**라
  다른 방이다. 재사용하지 말고 새 종류를 만든다.
- 두 화면 모두에 버튼(워크벤치 상세, 마법사).

## 1. 계약 (이름 고정 — 바꾸지 마라)

| 항목 | 값 |
|---|---|
| push_kind | `drawing_room` |
| structured_data 이력 키 | `channeltalk_push_drawing_room` |
| 그룹 환경변수 | `CHANNEL_GROUP_DRAWING_ROOM`, 폴백 `"230331"` |
| 첨부 선택 함수 | `select_drawing_room_push_attachments(order, attachments)` |
| 첨부 선택 모듈 | `foms/services/channel_drawing_attachments.py` (신규 flat 모듈) |
| 라우트 | **신규 없음** — 기존 `POST /api/channel/push-manual` 에 push_kind 확장 |
| 감사 action | **신규 없음** — 기존 `CHANNEL_PUSH_SENT` 그대로 |
| 워크벤치 버튼 id | `dw-btn-drawing-room-push` |
| 마법사 버튼 id | `dws-btn-room-push` |
| 본문 조립 | 기존 `build_message_template('manual', ...)` 경로 그대로 |

## 2. 앵커 (읽고 시작하라)

**백엔드**
- `foms/api/channel/channel_integration.py:68-92` — `_PUSH_KIND_CONFIG` (push_kind → category·history_key·group_env)
- `foms/api/channel/channel_integration.py:376-440` — `api_channel_push_manual` 진입·검증·그룹 결정
- `foms/api/channel/channel_integration.py:475-500` — 첨부 조회(category 필터) + AS 전용 선택 분기(`push_kind == 'as'`)
- `foms/api/channel/channel_integration.py:207` — `_record_push_metadata()` 이력 기록(pushed·message_id·group_id·sent_at·is_modified·change_log·attachment_ids)
- `foms/services/channel_policy.py:125-165` — `get_routing_group_id()` push_kind 분기
- `foms/services/channel_as_attachments.py:84` — `select_as_push_attachments()` — **선택자 모듈의 본보기**
- `foms/api/drawing/erp_orders_drawing.py:176-190` — 전달 시 `drawing_current_files` 갱신 + 그 키들의 OrderAttachment.category 를 'drawing' 으로 표시

**프론트**
- `templates/drawing/partials/workbench_detail_body.html:1488-1523` — 워크벤치 데스크톱 액션 버튼 블록
- `templates/drawing/partials/workbench_detail_body.html:1559-1586` — 워크벤치 모바일 하단 액션 바
- `foms/web/drawing/workbench.py:840-883` — 워크벤치 권한 변수 결정(`can_transfer`·`can_confirm_receipt`·`can_request_revision`)
- `templates/drawing/wizard.html` 앱바 우측 버튼 그룹 — 실제 줄 번호는 워커가 직접 확인
- `static/js/drawing/wizard.js` `wireStatic()` — 앱바 버튼 이벤트 배선
- `static/js/orders/erp-channel-push-confirm.js:8-14` — `HISTORY_KEYS`(push_kind ↔ 이력 키), 76-79 중복 클릭 차단
- `static/js/orders/erp-order-shared.js:5543` — 기존 발주 PUSH 호출부(호출 패턴 본보기)
- `templates/orders/partials/erp_channel_push_resend_modal.html` — 재전송(변경 내용) 모달

## 3. 파일 소유권 (워커끼리 절대 겹치지 마라)

**W1 백엔드**
- `foms/services/channel_drawing_attachments.py` (신규)
- `foms/services/channel_policy.py`
- `foms/api/channel/channel_integration.py`
- `tests/domains/test_channel_drawing_room_push.py` (신규)

**W2 워크벤치 프론트**
- `templates/drawing/partials/workbench_detail_body.html` (핀 줄 포함 — 이 파일의 `?v=` 는 W2 몫)
- `static/js/orders/erp-channel-push-confirm.js` (drawing_room 이력 키 등재)
- `tests/domains/test_drawing_room_push_workbench_ui.py` (신규)

**W3 마법사 프론트**
- `templates/drawing/wizard.html` (핀 줄 포함 — 이 파일의 `?v=` 는 W3 몫)
- `static/js/drawing/wizard.js`
- `static/css/contexts/drawing/wizard.css`
- `tests/domains/test_drawing_room_push_wizard_ui.py` (신규)

W2·W3 는 **서버 API 를 바꾸지 않는다**. 둘 다 W1 이 만든 `push_kind='drawing_room'` 을
`POST /api/channel/push-manual` 로 부른다. 계약(1절)이 이미 고정돼 있으므로 W1 완료를
기다리지 말고 그 이름 그대로 호출하면 된다.

## 4. 함정 (여기서 다 터졌다)

1. **첨부를 category='drawing' 로 전량 발사하면 옛 도면까지 나간다.** 전달 때마다 그 파일들의
   category 가 'drawing' 으로 표시되므로 1차·2차 전달본이 전부 남아 있다. `drawing_room` 은
   반드시 `structured_data['drawing_current_files']` 의 **storage_key 집합으로 교집합**을 잡아라
   (AS 의 AS-FRESH-01 과 같은 이유·같은 모양).
2. **이력 키를 `channeltalk_push_drawing` 과 공유하지 마라.** 발주 PUSH 를 보냈다고 도면방 PUSH 가
   재전송으로 취급되면 안 된다(실측방이 `channeltalk_push_measure_room` 을 따로 쓰는 이유와 동일).
3. **`_OPERATIONAL_TOP_LEVEL_KEYS`**(`foms/api/erp_orders_structured.py`)에 새 이력 키를 등재하지
   않으면 **주문을 한 번 저장하는 것만으로 발송 이력이 사라진다**. W1 이 등재한다.
4. **인라인 스타일 금지**, jQuery 금지, `fetch` 는 try/catch + `data.success` 검증.
5. **JS/템플릿 내용을 바꾸면 `?v=` 핀을 반드시 올려라**(SW staticCacheFirst 스테일). 핀 문자열을
   문자로 단언하는 계약 테스트가 있으면 같이 고친다.
6. **신규 라우트·신규 감사 action 을 만들지 마라.** 만드는 순간 write guard manifest·mutation
   policy manifest·audit 라벨 3종 등재가 걸린다. 기존 `/push-manual` 확장으로 끝내라.
7. 도면 파일이 0장이면 버튼은 **막고** 안내한다(도면 없이 방에 알림만 가면 안 된다).
8. 권한: 도면방 PUSH 는 워크벤치 참여자(도면팀·배정자)와 관리자가 누른다. 새 권한 축을 만들지
   말고 그 화면이 이미 계산한 변수를 쓴다.

## 5. 검증 명령 (워커가 직접 돌린다)

```
cd /c/tmp/dwpush && pwd            # 반드시 이 워크트리에서
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_channel_integration_smoke.py -q          # W1 필수
python -m pytest <자기 신규 테스트 파일> -q
node --check static/js/drawing/wizard.js                                     # W3
node --check static/js/orders/erp-channel-push-confirm.js                    # W2
```

## 6. 워커 공통 규칙

- **git 명령 금지**(add/commit/push/checkout 전부). 총괄이 커밋한다.
- 파일 줄바꿈(CRLF) 보존. 파이썬 치환 스크립트로 고칠 때 `newline=''` 주의.
- 자기 소유 파일만 편집. 남의 파일이 고쳐져야 하면 **보고서에 적기만** 하라.
- `docs/` 를 읽는 테스트를 새로 만들지 마라(CI-DOCSCOPE 등재 게이트에 걸린다).
- 인벤토리(`docs/harness/*.json`) 재생성은 총괄 몫이다. 건드리지 마라.
- 함수 50줄 이하·docstring·타입 힌트, bare except 금지.
- 보고서에 **실제로 돌린 명령과 출력 마지막 줄**을 적어라. 안 돌렸으면 안 돌렸다고 적어라.
