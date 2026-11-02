# FOMS 공지사항(본사 · 협력사) — 설계 (사용자 승인 2026-11-02 · 구현)

요청(사용자 2026-11-02): "FOMS 에도 공지사항을 별도로 만들어(본사, 협력사 포함). 본사, 협력사 공지는 별도로 또는 같이 안내할 수
있게." 목업: https://claude.ai/artifact/B82TneVFW69exDRpAHWXPf (관리자 쓰기 · 확인 현황 · 본사 목록/창 · 협력사 목록/창) — 승인.
결정(사용자): 공지 표를 따로 둔다(공지 한 줄 + 사람마다 확인 기록). 긴급 알림(빨간 전체 화면, `/admin/notifications`)은 그대로 따로 둔다.

## 1. 데이터 (새 표 2개, alembic 마이그레이션 + downgrade)

`notices`
- id, title(200), body(Text), created_by_user_id(FK users, null 가능), created_by_name(100)
- audience_staff_all(bool), audience_staff_teams(JSONB list[str] — 팀 코드, 정규화 `normalize_team`), 
  audience_partner_all(bool), audience_partner_org_ids(JSONB list[int])
- display_mode(String 20: `POPUP` 확인 눌러야 닫힘 | `LIST` 목록에만), pinned(bool)
- starts_at(DateTime UTC naive, null=바로), ends_at(DateTime, null=끝 없음)
- created_at, updated_at, deleted_at(DateTime, 지우기는 soft)

`notice_acks`
- id, notice_id(FK notices ON DELETE CASCADE), user_id(FK users), read_at(DateTime null), ack_at(DateTime null), created_at
- UNIQUE(notice_id, user_id), 인덱스 user_id

## 2. 받는 사람 판정 (서비스 한 곳 `foms/services/notices/audience.py`)
- 본사 직원 = `User.partner_org_id IS NULL` · is_active. `audience_staff_all` 이면 모두, 아니면 `normalize_team(user.team)` 이 `audience_staff_teams` 안.
- 협력사 직원 = `User.partner_org_id` 있고 is_active · 그 PartnerOrg.is_active. `audience_partner_all` 이면 모두, 아니면 org_id 가 `audience_partner_org_ids` 안.
- 공지 하나가 둘 다 고를 수 있다. 게시 중 = deleted_at 없음 · (starts_at 없거나 ≤ 지금) · (ends_at 없거나 > 지금).
- **나중에 들어온 계정도 받는다**(받는 사람을 미리 펼치지 않고 볼 때 판정 — 표를 따로 둔 까닭).

## 3. 서비스 `foms/services/notices/` (패키지)
- `audience.py`: `user_matches(notice, user, org_active: bool) -> bool`, `recipients(db, notice) -> list[User]`, `audience_label(notice) -> str`("본사 전체" · "본사: 영업 · 도면" · "협력사 전체" · "협력사: 라운즈" · 둘이면 " + " 로 잇기).
- `service.py`:
  - `visible_notices(db, user) -> list[dict]` 게시 중 · 받는 사람인 공지, 고정 먼저 · 최근 순. dict: id, title, body, pinned, display_mode, created_at(KST 문자열), created_by_name, read(bool), acked(bool), audience_label.
  - `pending_popups(db, user) -> list[dict]` POPUP 이고 ack 안 한 것, 오래된 것부터 최대 5 (id, title, body, created_by_name, created_at).
  - `ack_notice(db, user, notice_id) -> bool`(받는 사람이 아니거나 없으면 False) — ack_at · read_at 채움(없으면 행 만듦). `mark_read(db, user, notice_id)`.
  - `unread_count(db, user) -> int` (목록 배지).
  - `create_notice(db, actor, payload) -> Notice` · `update_notice` · `delete_notice`(soft) — 검증: 제목 필수(≤200), 받는 쪽 하나 이상, display_mode 두 값, ends_at > starts_at. 감사 SecurityLog action `NOTICE_CREATED/UPDATED/DELETED` + `foms/services/audit_message_display.py` 라벨.
  - `ack_status(db, notice_id) -> dict` {total, acked, staff:{total,acked,people:[{user_id,name,team_label,acked_at,read_at}]}, partner:{total,acked,people:[{user_id,name,org_name,acked_at,read_at}]}}.
- 기존 협력사 공지(`foms/services/partners/notices.py`, Notification 종류 `PARTNER_NOTICE`)는 그대로 둔다(운영 2건 이미 나감). 협력사 화면 창은 두 출처를 다 띄운다(기존 PARTNER_NOTICE 먼저, 그다음 새 공지).

## 4. API (JSON `{success, data, error}`)
관리자(ADMIN · MANAGER) — 블루프린트 `notices_admin_api`, 접두 `/api/admin/notices`:
- `GET ""` 목록(지운 것 빼고) · 각 {id,title,pinned,display_mode,audience_label,starts_at,ends_at,created_at,created_by_name,ack:{total,acked}}
- `POST ""` 만들기 · `PUT /<id>` 고치기 · `DELETE /<id>` 지우기(soft)
- `GET /<id>/status` 확인 현황(§3 ack_status)
- `GET /audience-options` {teams:[{code,label}], partners:[{id,name}], counts:{staff_all, by_team:{code:n}, partner_all, by_org:{id:n}}}
- 페이로드: title, body, audience:{staff_all, staff_teams[], partner_all, partner_org_ids[]}, display_mode, pinned, starts_at, ends_at('YYYY-MM-DDTHH:MM' KST 또는 빈 값)

받는 사람(본사 직원 · 협력사 직원 둘 다 로그인) — 블루프린트 `notices_api`, 접두 `/api/notices`:
- `GET ""` 내 공지 목록 {items, unread}
- `POST /<id>/ack` → {pending: [...남은 창 공지]} · `POST /<id>/read`
협력사 문지기 허용 목록(`foms/services/auth/partner_scope.py`)에 `notices_api.list_notices`, `notices_api.ack_notice`, `notices_api.read_notice`, 협력사 화면 `partner_portal.notices` 추가. 쓰기 라우트는 `docs/harness/foms_write_guard_manifest.json` · `foms_order_mutation_policy_manifest.json` 에(협력사 쓰기는 policy_id PARTNER_PORTAL, 본사·관리자 쓰기는 비슷한 기존 항목 따라).

## 5. 화면
관리자(`/admin/notices`, `/admin/notices/new`, `/admin/notices/<id>/edit`, `/admin/notices/<id>/status`) — HTML 블루프린트 `notices_admin`:
- 목록 + "공지 쓰기". 쓰기 화면은 목업대로: 받는 쪽 칩(본사 전체/팀들 · 협력사 전체/회사들, 둘 다 가능), 받는 사람 수 실시간(audience-options counts),
  보이는 방식(확인 창 / 목록만), 게시 시작 · 끝, 맨 위 고정, 오른쪽 휴대폰 미리보기. 확인 현황: 진행 막대, 본사/협력사 탭, "안 한 사람만" 기본.
- 관리자 첫 화면(`templates/admin/admin.html`)에 "공지사항" 단추.
본사 직원: `/notices` 목록(고정 · 안 읽음 점 · 대상 칩, 전체/안 읽음 필터). 공지 창은 본사 화면 공용 레이아웃(`templates/partials/shared/layout_head.html` 또는 layout_scripts 의 기존 공용 스크립트 자리)에서
  `GET /api/notices` 를 한 번 불러 POPUP 미확인이 있으면 가운데 흰 창(FOMS 보라, 확인으로만 닫힘, "1 / 2"). 긴급 빨간 창과 섞지 않는다.
협력사: `/partner/notices` 목록, 머리줄/더보기에 "공지사항"(안 읽음 배지). 창은 기존 `templates/partner/partials/notice_modal.html` · `partner-notice.js` 를 넓혀 새 공지도 띄운다(새 공지 확인은 `/api/notices/<id>/ack`).
규약: 인라인 style 금지(erp-pro.css 래칫), fetch try/catch + data.success, Jinja→JS 는 data-* + safeJsonParse, 새 JS 파일 300줄 · 파이썬 500줄 래칫, asset_url 로 싣는다.

## 6. 파일 담당(병렬 구현 — 남의 파일을 고치지 않는다)
- **A 백엔드**: `models.py`(Notice · NoticeAck), `migrations/versions/notice_00_*.py`, `foms/services/notices/*`, `foms/api/notices/*`(두 JSON 블루프린트), `foms/platform/blueprints.py` 등록, `partner_scope.py`, 두 manifest, `audit_message_display.py`, 시험 `tests/domains/test_notices_service.py` · `tests/security/test_notices_api.py`.
- **B 관리자 화면**: `foms/web/admin/notices.py`(HTML 블루프린트 `notices_admin`, 등록 줄은 A 가 blueprints.py 에 미리 넣는다), `templates/admin/notices/*.html`, `templates/admin/admin.html` 단추, `static/js/admin/notices-*.js`, `static/css/contexts/admin/notices.css`, 시험 `tests/domains/test_notices_admin_pages.py`.
- **C 받는 사람 화면**: 본사 `foms/web/notices.py`(HTML 블루프린트 `notices_web`, `/notices`; 등록 줄은 A 가 넣는다), `templates/notices/*.html`, 본사 공용 창 `templates/partials/shared/notice_popup.html` + `static/js/foms/foms-notice-popup.js` + `static/css/components/foms-notice.css` 와 레이아웃에 싣는 한 줄, 협력사 `foms/web/partner/__init__.py` 의 `/partner/notices` 라우트 · 머리줄 링크, `templates/partner/notices.html`, `notice_modal.html` · `partner-notice.js` 넓히기, 시험 `tests/security/test_notices_screens.py`.
- 서로 부르는 이름(블루프린트 · 엔드포인트 · 서비스 함수)은 이 설계서 그대로. 등록 줄(blueprints.py)은 A 가 세 HTML/JSON 블루프린트 모두 넣고, B · C 의 모듈이 아직 없으면 import 가 깨지므로 A 는 B · C 모듈 파일을 **빈 블루프린트 뼈대**로 먼저 만들어 둔다(B · C 가 내용을 채운다).

## 7. 폰 알림 · 배지 (사용자 결정 2026-11-02 · 구현)
- 결정: 모든 공지(POPUP · LIST)를 받는 사람 폰으로 보낸다(Web Push) + 앱 아이콘 배지 · 종 배지 숫자에 잡힌다. 읽거나 확인하면 숫자가 준다. 예약 공지(`starts_at` 미래)는 게시가 시작될 때 보낸다(몇 분 늦어도 됨). 잠금화면: 제목 "📢 공지사항", 본문 = 공지 제목만(120자에서 자름 — 본문 내용은 싣지 않는다).
- 데이터(마이그레이션 `notice_01`, downgrade 포함): `notices.push_sent_at`(보낸 · 보내지 않기로 정한 때, UTC) · `notice_acks.notification_id`(FK `notifications.id` ON DELETE SET NULL, `fk_notice_acks_notification_id`). 올릴 때 이미 있는 공지는 `push_sent_at` = 지금(배포 직후 옛 공지가 한꺼번에 울리지 않게). 머리 하나를 지키려고 `notice_00` 이 아니라 그때 머리 `csagent_05` 뒤에 잇는다.
- 알림 종류 `FOMS_NOTICE`(정본 `foms/services/notifications/notice_push.py` — 글 · 주소 규칙도 거기). 발송 `foms/services/notices/push.py` `dispatch_notice_push(db, notice, *, now, enqueue)`:
  1) 선점 `UPDATE notices SET push_sent_at=:now WHERE id=:id AND push_sent_at IS NULL` — 0줄이면 끝(웹과 SIDEFX 이중 발송 방지). 게시 중이 아니면 선점하지 않는다.
  2) `recipients(db, notice)` 마다 `Notification`(FOMS_NOTICE · target_type USER · target_user_id · is_urgent False · title = 공지 제목 · message 빈 글) → `fan_out_new_notification` → 그 사람 `NoticeAck` 줄(없으면 만든다)에 `notification_id`. 받는 사람이 없어도 보낸 때는 채운다.
  3) 커밋 뒤 `enqueue=True` 면 `enqueue_push_for_notification`(웹 · RQ), False 면 `send_push_for_notification` 바로(SIDEFX — REDIS 없음). 실패는 로그만.
- 즉시: 관리자 API 만들기 · 고치기 커밋 뒤 `push_notice_if_due` — 지금 게시 중이고 `push_sent_at` 이 비었으면 보낸다(이미 보낸 공지는 고쳐도 다시 안 보냄, 예약 → 지금 게시로 고치면 보냄). 실패해도 응답은 그대로(SIDEFX 스캔이 다시 본다).
- 예약: SIDEFX 루프(`tools/ops/run_domain_side_effect_outbox.py`)가 60초마다 `sweep_due_notice_pushes` — 지우지 않음 · 미발송 · 시작 지남 · 끝 안 지남이면 보내고, 끝난 미발송 공지는 보내지 않고 `push_sent_at` 만 채운다.
- 배지: 공지 `mark_read` · `ack_notice` 가 그 사람 `NoticeAck.notification_id` 의 `NotificationUserState.read_at`(확인은 `ack_at` 도)을 채운다(이미 있으면 그대로). 공지 지우기(soft)는 연결된 상태를 `archived_at` 으로 — 배지에서 빠진다.
- 푸시 글(`push_sender._build_payload`): FOMS_NOTICE 는 협력사 분기보다 먼저 — title "📢 공지사항", body = 공지 제목, tag `foms-notice-<알림 id>`, `data.deep_link` 는 받는 사람(`target_user_id` → `User.partner_org_id`)이 협력사면 `/partner/notices`, 아니면 `/notices`. `FOMS_PUSH_P1_TYPES` 로 P1 집합을 줄여도 늘 보낸다(협력사 알림과 같다). 벨 목록 링크(`_resolve_notification_deep_link`)도 같은 규칙.
- 시험: `tests/domains/test_notices_push.py`(받는 사람 · 음성 대조군 · 선점 · 예약 · 끝난 예약 · 배지 · 보관 · 글 · 주소), `tests/postgres/test_notices_push_pg.py`(동시 선점 · 마이그레이션 왕복).

## 8. 사진 첨부 (사용자 요청 2026-11-02 · 구현)
요청(사용자): "공지에 사진도 올릴 수 있게 변경 > 미리보기는 모달 : thumbnail with blur outside (FOMS 스타일 그대로)". 아래 기본값은 위임자가 정했다.
- **데이터**(마이그레이션 `notice_02`, 그때 머리 `brain_00` 뒤, downgrade 포함): `notices.images` JSONB NOT NULL DEFAULT `'[]'` — 보이는 순서 그대로의 목록,
  항목 `{key, thumb_key, name, width, height, size}`. 고치기는 새 목록을 다시 넣고 `flag_modified(notice, 'images')`. 뺀 사진의 저장소 파일은 지우지 않는다.
- **받기**(`foms/services/notices/images.py`): 공지당 최대 5장, 한 장 15MB 이하, Pillow 로 열어 판정 — JPEG(MPO) · PNG · WebP · HEIC/HEIF(아이폰 원본 —
  `pillow-heif` 로 이 모듈 안에서만 풀어 JPEG/PNG 로 다시 그린다. Pillow 전체 등록은 하지 않아 다른 업로드 규칙은 그대로, 사용자 요청 2026-11-02). 방향(EXIF)을 바로잡고 긴 변 2000px 본 +
  긴 변 480px 썸네일로 다시 그린다(EXIF · 위치 정보 빠짐, 투명 칸이 있으면 PNG 아니면 JPEG). 저장은 `StorageAdapter.put_private_bytes`(비공개, R2) —
  key `notices/images/<YYYYMM>/<uuid>.<jpg|png>` · 썸네일 `..._thumb.<같은 확장자>`. 로컬 저장소(개발 전용)는 업로드 폴더에 바로 쓴다.
- **API**: 관리자 `POST /api/admin/notices/images`(multipart `image` 한 장, ADMIN · MANAGER, 본문 상한 15MB+256KB `request_limits` `notice_image`)
  → `{key, thumb_key, name, width, height, size, preview_url, thumb_url}` · `GET /api/admin/notices/images/file?key=` 관리자 보기(아직 저장 안 한 사진 ·
  지운 · 예약 공지). 만들기 · 고치기 페이로드 `images: [{key, thumb_key, name, width, height, size}]` — `payload.clean_images` 가 key 꼴(업로드 API 가 만든
  `notices/images/...` 만)을 보고 썸네일 key 는 본 key 에서 다시 만든다(남의 파일 key 끼워 넣기 금지). 칸이 없으면 고치기에서 사진을 그대로 둔다.
  받는 사람 `GET /api/notices/<id>/images/<차례>`(`?thumb=1` 썸네일) — `service.viewable_notice` 로 판정(게시 중 · 받는 사람, 관리자는 지운 · 예약 공지도),
  아니면 404. 클라우드면 10분 서명 주소로 302, 로컬은 바이트 — 둘 다 `Cache-Control: private, no-store`. 협력사 문지기 허용 목록에 `notices_api.notice_image`.
  쓰기 manifest 두 곳에 `notices_admin_api.upload_image`(MANAGER_MUTATION).
  올리기마다 감사 원장 한 줄(`NOTICE_IMAGE_UPLOADED`, 라벨 "공지 사진 올림" — key · 이름 · 크기, 대상 id 없음).
- **창 · 목록**: `notice_summary` 의 창 공지 항목과 `visible_notices` 항목에 `images: [{url, thumb_url, name, width, height}]`(주소만 — 저장소 key 는 싣지 않는다).
  창 · 배지 요약은 사진 목록도 본문과 같은 한 번(`id IN (...)`)에 읽는다(질의 수 그대로). 협력사 창 차례(`_pending_notice_queue`)도 `images` 를 싣는다.
- **화면**: 본문 아래 작은 썸네일 줄(`[data-foms-notice-images]` · `[data-foms-notice-thumb]`) — 본사 공지 창 · `/notices` · 협력사 공지 창 · `/partner/notices` ·
  관리자 휴대폰 미리보기. 누르면 가운데 사진 창(`static/js/foms/foms-notice-gallery.js`, 모양 `foms-notice.css`): 흰 카드 · 둥근 모서리 · 보라 윗줄, 바깥은
  `backdrop-filter: blur(8px)` + 어둡게. 여러 장이면 좌우 단추 · 화살표 키 · 밀기, 닫기는 X · 바깥 · Esc. z-index 105460(공지 창 105450 위, 도면 확인 105500 ·
  긴급 106000 아래). 공지 창의 초점 가두기(document 잡기 단계)와 겹치지 않게 사진 창은 window 잡기 단계에서 keydown · focusin 을 먼저 받아 내려보내지 않고,
  두 공지 창 스크립트도 열린 사진 창을 "더 위 창"으로 보고 가두기를 쉰다. 사진 창을 닫으면 누른 썸네일로 초점이 돌아가고 공지 창은 그대로다.
  관리자 쓰기 화면: 내용 아래 "사진" 칸(끌어놓기 · 고르기, 올리는 중 표시, 썸네일 줄 — 빼기 X · 좌우 순서, 5장 넘으면 안내, `static/js/admin/notices-images.js`).
- 폰 알림(잠금화면 글 · 배지)은 바꾸지 않는다(제목만).
- 시험: `tests/domains/test_notices_images.py`(받기 · 페이로드 · 업로드 API · 사진 주소 권한 + 음성 대조군 · 창 항목), `tests/security/test_notices_photo_screens.py`
  (썸네일 · 사진 창 훅 · 정적 검사), `tests/postgres/test_notices_images_pg.py`(`notice_02` 왕복 — 옛 공지는 `[]`).
