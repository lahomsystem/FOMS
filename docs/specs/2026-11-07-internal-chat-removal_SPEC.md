# FOMS 사내 채팅 삭제 (CHAT-DEL-01)

- 상태: **1단계 운영(#762)** · **2단계(표 지우기) 설계 11-09 — 승인 대기**(11-09 사용자 "채팅 표 지우기 2단계" 선택, 설계서 먼저)
- 결정 원장: `docs/plans/2026-11-06-freelancer-commission-ledger.md` "채팅" 줄
- 범위 밖: 채널톡(ChannelTalk — `foms/api/channel/channel_*.py`, `foms/services/channel_*.py`, 공유 상담), 브레인 채팅(`/api/brain/chat`), 휴대폰 주문 화면의 "채팅"(= 문자 `sms:` 링크)

## 1. 왜

사용자(11-07): "FOMS 채팅 기능은 아예 삭제해. 아니면 필요한 이유가 있는지 검토해봐 — 전사 직원이 채널톡을 써."

운영 실측(11-07, 읽기 전용 집계 — 글 내용은 읽지 않음):

| 항목 | 값 |
|---|---|
| 방 | 1개(2026-02-20, 주문 연결 없음) |
| 방 회원 | 1명 |
| 글 | 2개(둘 다 2026-02-20, 한 사람) |
| 첨부 | 0 |
| 최근 30일 글 | 0 |

필요한 이유를 찾지 못했다. 사내 대화는 채널톡이 맡고, 주문 단위 연락은 긴급 호출 · 알림 · 채널톡 PUSH 가 맡는다. 남겨 두면 프리랜서(D24 · D27)처럼 새 권한 규칙이 생길 때마다 막을 틈(주문 검색 · 주문 보기 · 방에 주문 잇기 · 방 정보)을 같이 고쳐야 한다.

## 2. 남길 것(같이 지우면 안 됨)

- **Socket.IO 서버와 `connect` · `disconnect`** — `connect` 가 개인 방 `user_<id>` 에 넣는데, ERP 실시간 알림(`erp_notification`, `foms/services/notifications/realtime_notifications.py`)이 이 방으로 간다. `register_chat_socketio_handlers` 에서 연결 · 끊김만 떼어 알림 쪽 이름(`register_realtime_socketio_handlers`)으로 옮긴다. 협력사 · 비활성 거절도 그대로.
- `foms/services/auth/freelancer_designation.disconnect_realtime` — 프리랜서 지정 때 실시간 연결 끊기(알림용).
- `static/js/runtime/layout-scripts-chat.js` — 이름만 채팅이고 내용은 알림 배지 · 패널. 이름은 그대로 둔다(바꾸면 묶음 빌드 · 크기 기준선 · 계약 시험이 함께 흔들린다).
- `foms/api/channel/utils.build_file_view_url` 처럼 채팅 밖에서 쓰는 도우미.

## 3. 1단계 — 코드 지우기(DB 그대로)

| 묶음 | 지울 것 |
|---|---|
| API | `chat` 블루프린트 전체(HTTP 19개: `foms/api/channel/{blueprint,routes,rooms,messages,files}.py`), `utils.py` 의 채팅 전용 함수, `__init__.py` 의 채팅 내보내기 |
| 화면 | `/chat` · `/chat/scripts.js`(`foms/web/channel/`), 템플릿 14개(`templates/channel/chat.html`, `templates/partials/chat_*.html`) |
| 실시간 | 채팅 이벤트 5개(`join_room` · `leave_room` · `send_message` · `typing` · `mark_read`) |
| 화면 껍데기 | `menu_config.py` 채팅 메뉴, `layout_nav.html` 채팅 링크, `layout_head.html` 채팅 알림 CSS · `new_message` 받기 · 채팅 토스트 · `/chat` 이동, `layout_scripts.html` 채팅 알림 상자 |
| 권한 · 정책 | `chat_room_access.py`, 정책 `CHAT_ROOM` · `MARK_ROOM_READ` · `SEND_CHAT_MESSAGE` · `UPLOAD_CHAT_ATTACHMENT`, 요청 크기 한도 3줄 |
| 저장소 | `storage.upload_chat_file`, 업로드 정책 `CHAT_ALLOWED_EXTENSIONS` |
| 프리랜서 | `remove_chat_memberships`(지정 때 방 빼기) · 결과 키 `chat_memberships_removed` · `chat_closed_for` — 채팅이 없으니 필요 없다. 설계서 §6 의 채팅 줄을 "삭제됨"으로 |
| 직원 지우기 | `user_deletion._purge_owned_chat_rooms` 는 **남긴다**(표가 남아 있는 동안 FK 때문에 필요) — 2단계에서 같이 지운다 |
| 하네스 | 정책 · 쓰기 가드 · 감사 · ORM 우회 목록의 `chat.*` 줄 — `refresh_inventories.py` 로 다시 만든다 |
| 시험 | 채팅 전용 2개 파일 지움, 섞인 파일 11곳에서 채팅 부분만 지우거나 "없는 길 = 404" 로 바꿈 |

### 1단계에서 지우지 않는 것

- 컷오버 이름 `CHAT_SCOPE`(`FOMS_CHAT_SCOPE_MODE`) — `foms/build_compatibility.json` · 컷오버 표에 묶여 있어 빼면 배포 때 빌드 호환 검사가 흔들린다. 지금 이 이름을 읽는 코드는 없다(동작 없음).
- 감사 문구 `CHAT_MESSAGE_SENT` — 운영에 옛 감사 줄(글 2개)이 남아 있어 화면 표시용으로 둔다.
- 부하 시험 스크립트(`tests/harness/load/*.js`)의 채팅 흐름 — 기본 비중 0 으로 끄고(켜면 404) 200명 스크립트에서는 뺐다.
- 모델 4개(`ChatRoom` · `ChatRoomMember` · `ChatMessage` · `ChatAttachment`)와 표, 작업 대기열(`domain_side_effect_outbox`)의 `chat_attachment_id` 칸 · 한-칸-만 규칙(CHECK). 표를 지우려면 이 CHECK 를 다시 써야 해서 위험이 코드 삭제와 다른 급이다. 표는 비어 있는 것과 같고 남아도 비용이 없다.
- 옛 운영 스크립트(`scripts/ops/db_admin.py` · `erp_build_step_runner.py` · `scripts/migrations/migrate_local_uploads_to_r2.py`)의 채팅 표 이름 — 표가 남아 있으니 그대로 돈다.

## 4. 2단계 — 표 지우기(11-09 설계, 승인 대기)

### 4.1 실측(11-09, 운영 읽기 전용 — 글 내용은 읽지 않음)

- `chat_rooms` 1 · `chat_room_members` 1 · `chat_messages` 2(둘 다 2026-02-20, 시험으로 보임) · `chat_attachments` 0. 네 표 합 200kB.
  주문에 붙은 방 0.
- 대기열 `domain_side_effect_outbox` 의 `CHAT_ATTACHMENT` 줄 0(칸 · 도메인 둘 다).
- 채팅 표를 **바깥에서** 가리키는 FK 는 대기열 `chat_attachment_id` 하나(`domain_side_effect_outbox_chat_attachment_id_fkey`).
  채팅 표가 바깥을 가리키는 FK: `users` 3 · `orders` 1(지우면 같이 없어진다).
- 운영 alembic head `fcomm_02`.
- 백업: 11-09 06:28(KST) 오프사이트 덤프 69.5MB 검증 통과 · R2 업로드 완료(`foms-ops-backup`, 환경변수 스냅샷 단계만 실패 —
  Railway 토큰, 알려진 이슈). 지우는 3줄은 이 덤프에 남는다.

### 4.2 마이그레이션 `chat_drop_01`(down `fcomm_02`)

upgrade:
1. 대기열 CHECK 두 개(`ck_dseo_source_one_of` · `ck_dseo_source_domain`)를 `CHAT_ATTACHMENT` 를 뺀 7도메인으로 다시 쓴다
   (선례 `order_import_00` — 작성 시점 스냅샷 dict, models 를 import 하지 않음, ORM 식과 byte-identical).
2. FK `domain_side_effect_outbox_chat_attachment_id_fkey` → 칸 `chat_attachment_id` 지우기.
3. 표 4개 지우기: `chat_attachments` → `chat_messages` → `chat_room_members` → `chat_rooms`(색인 · trgm 색인 같이 없어짐).

downgrade: 빈 표 4개 · 색인(trgm 2개 포함) · 칸 · FK · 8도메인 CHECK 를 다시 만든다. **지운 3줄은 돌아오지 않는다**(백업에 있음).

### 4.3 코드(같은 커밋 — 필수)

배포는 새 빌드에서 predeploy `alembic upgrade head` → `tools/ops/ensure_schema.py` 순이다. 모델이 남아 있으면 ensure_schema 가
표를 되살리므로 모델 삭제와 마이그레이션을 **한 커밋**에 넣는다.

- `models.py`: 모델 4개, `DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN` 의 `CHAT_ATTACHMENT`, 대기열 `chat_attachment_id` 칸.
- `db.py` `init_db` import, `foms/services/user_deletion.py` 채팅 3줄 · `_purge_owned_chat_rooms`.
- 옛 운영 스크립트: `scripts/ops/db_admin.py` 표 목록, `scripts/ops/erp_build_step_runner.py` 의 `chat_attachments` UPDATE,
  `scripts/migrations/migrate_local_uploads_to_r2.py` 채팅 단계.
- 시험: `test_user_delete` · `test_user_deletion` · `test_format_datetime_kst` · `tests/postgres/test_sidefx_outbox` · `test_delete_retention`.
- 남기는 것: 컷오버 이름 `CHAT_SCOPE`, 감사 문구 `CHAT_MESSAGE_SENT`(옛 감사 줄 표시), 옛 마이그레이션 파일(불변).

### 4.4 순서 · 확인 · 위험

- 시험 → smoke → deploy → PG 레인(빈 PG 에 `alembic upgrade head` + 모델과 스키마 대조) 초록 → 스테이징 배포 뒤 스테이징 DB 에
  표 · 칸이 없는지 읽기 전용 확인 → 운영 승격 PR(predeploy 가 운영에서 upgrade) → 운영 DB 읽기 전용 확인.
- 위험: 배포 전환 몇 초 사이 옛 replica 가 직원 지우기를 부르면 오류(드묾, 다시 누르면 됨). 채팅 첨부 파일은 0건이라 R2 정리 없음.
- 되돌리기: 코드 `git revert` + `alembic downgrade fcomm_02`(빈 표로 돌아옴).

## 5. 확인

- `python -c "import app; print('APP_OK')"`, 바뀐 파일에 닿는 시험 → `pre_push_smoke.ps1` → push → CI 초록 → 스테이징 배포.
- 스테이징 실화면: 위 메뉴에 "채팅" 없음, `/chat` · `/api/chat/rooms` 가 404, **실시간 알림이 그대로 뜸**(긴급 호출 한 건을 보내 받는 쪽 화면에 바로 뜨는지 — 음성 대조군은 소켓을 끊은 탭).
- 운영은 사용자 요청 때만(이 세션 커밋만 cherry-pick → PR).

## 6. 되돌리기

1단계는 DB 를 안 건드리므로 `git revert` 하나로 돌아온다.
