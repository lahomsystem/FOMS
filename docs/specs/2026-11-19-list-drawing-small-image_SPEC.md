# 목록 화면 도면 작은 그림 — 설계서 (1판)

> 작성일 2026-11-19 | 상태 **승인됨 → 구현**(2026-11-19, 워킹트리 변경 — 커밋 전) | 등급 `**B`(파일 길 · 워커 작업 = 코어 변경)
> 계기: 폰 성능 점검(원장 `docs/plans/2026-11-09-tablet-production-ui-ledger.md`) 중 발견. 사용자 선택 "카드 미루기 + 그림 설계서도"(11-18).

## 0. 한 줄

목록 화면의 손톱만 한 도면 칸(40~112px)에 **원본 그림**을 통째로 받고 있다. 작은 그림을 한 번 만들어 저장해 두고, 목록에서는 그것만 받게 한다. 눌러서 크게 볼 때는 지금처럼 원본이다.

## 1. 왜 하나 (운영 실측, 11-18)

| 화면(폰) | 들어갈 때마다 받는 그림 |
|---|---|
| 생산 탭 | 약 13.2MB |
| 시공 탭 | 약 12.5MB |
| 도면 작업실 | 약 8.3MB |
| 출고 탭 | 약 6.9MB |

- 화면이 뜨는 시간은 거의 안 바뀐다(로컬 실측 −17ms, 흔들림 수준). 바뀌는 것은 **휴대폰 데이터 사용량**과 그림이 다 뜰 때까지 폰이 바쁜 시간이다.
- 탭을 한 바퀴 돌면 40MB 가 넘고, 같은 탭에 다시 들어가도 **또 받는다**(아래 원인 3).

## 2. 지금 코드의 사실 (직접 확인)

원인은 셋이다.

1. **목록이 원본 주소를 작은 칸에 그대로 쓴다.** 확정 도면 목록(`structured_data.drawing_current_files`)에는 작은 그림 칸이 없고, 읽는 쪽이 원본 주소를 `thumb` 에 넣는다 — `foms/services/construction_dashboard_display.py:164-173`. 도면 작업실 · 생산 시트 · 협력사 목록도 같다.
2. **도면을 전달할 때 만드는 첨부 행에 작은 그림을 안 만든다** — `foms/api/drawing/erp_orders_drawing.py:401-409`(`thumbnail_key` 없음). 그래서 첨부 행을 보는 화면(출고 · 생산 목록)도 원본으로 떨어진다.
3. **원본 주소는 브라우저가 기억하지 못한다.** `/api/files/view` 는 매번 `no-store` 302 와 새 서명 주소를 준다 — `foms/api/files/routes.py:196-201`, `:233`. 이 규칙의 이유는 보안이 아니라 "만료된 서명 주소를 다시 써서 그림이 깨지는 것"을 막으려는 것이다(커밋 `1d451ae99`, 2026-06-30).

이미 있는 선례(그대로 넓힌다): 생산 파트 카드 작은 그림 길 `foms/web/production/part_thumb.py`.
- 원본 옆에 `pthumb720_<원본 이름>.jpg` 로 한 번 저장, 응답은 `private, max-age=2592000, immutable`(30일, 다시 묻지 않음).
- 도면 key 는 올릴 때마다 새 이름이라, 도면을 바꾸면 작은 그림 이름도 바뀐다. **옛 작은 그림이 새 도면 자리에 나올 수 없다.**
- 투명 칸을 흰 바탕으로 깔고 사진 회전 정보를 반영한다(기존 300px 함수 `storage.py:517-583` 은 투명 칸이 검정이 되고 회전을 안 본다 — 쓰지 않는다).

함정 둘(고치면서 같이 챙긴다).
- 시공 태블릿 작업 화면은 `thumb` 를 **큰 무대 그림**으로 쓴다 — `templates/construction/partials/tablet_workmode_body.html:120`. `thumb` 를 작게 바꾸면 무대가 흐려지므로 이 자리는 원본(`view`)으로 바꿔 둔다.
- 운영 web 은 gevent 워커 2개다(`Procfile:3`). 그림을 줄이는 일을 web 에서 하면 그동안 그 프로세스의 다른 요청이 멈춘다.

## 3. 동작 (제안)

### 3-1. 작은 그림 길 하나를 새로 낸다

`GET /api/files/thumb/<원본 key>`

1. 문지기는 원본 보기와 **같은 함수**(`_deny_file_access(원본 key)`)를 쓴다. 원본을 못 보는 사람은 작은 그림도 못 본다. 지운 첨부면 404.
2. 저장된 작은 그림(`sthumb320_<원본 이름>.jpg`, 원본과 같은 폴더)이 있으면 그 바이트를 `private, max-age=2592000, immutable` 로 준다. 주소가 늘 같아서 브라우저가 30일 기억한다.
3. 없으면 **web 은 만들지 않는다.** 워커 큐에 "이 key 작은 그림 만들기"를 넣고(같은 key 는 한 번만), 이번 한 번은 지금처럼 원본으로 보낸다(`no-store` 302). 다음 방문부터 작은 그림이 나간다.
4. 그림이 아닌 파일(PDF 등)은 404 — 지금도 미리보기 칸에 안 나온다.

- 크기: 긴 변 320px JPEG(품질 85), 흰 바탕, 회전 반영. 가장 큰 목록 칸(112px)의 3배 화면에도 맞는다. 장당 약 20~40KB(추정).
- 감사 기록: 작은 그림은 안 남긴다(지금 `thumb_` 규칙과 같음 — `foms/services/audit_writer.py:67-71`). 원본을 열면 지금처럼 남는다.
  - 구현: 작은 그림 길(`thumb`)은 **감사 기록 함수를 아예 부르지 않는다** — 저장본 200 도, 저장본이 없어 원본으로 보내는 302 도(목록 미리보기가 한 화면에 서로 다른 key 수백 건을 만들지 않게). 눌러 크게 보기는 보기 길(`view`)이라 지금처럼 `FILE_VIEW` 가 남는다.
- 협력사 · 프리랜서 허용 목록에 새 길을 넣는다(`foms/services/auth/partner_scope.py`, `freelancer_scope.py`). 범위 검사는 1번 문지기가 한다.

### 3-2. 미리 만들어 둔다

- 도면 전달이 커밋된 뒤, 새 도면 key 마다 워커에 만들기 작업을 건다(`erp_orders_drawing.py` 전달 끝).
- **옛 도면은 따로 되채우지 않는다.** 3-1 의 3번이 "처음 본 순간 만들기"라서, 쓰는 도면부터 저절로 채워진다. 한 번도 안 열리는 옛 주문 도면은 만들지 않는다.
- 워커가 없거나 큐가 막히면 그냥 원본이 계속 나간다(지금과 같음). web 안에서 대신 만들지 않는다.

### 3-3. 목록이 작은 그림 주소를 쓰게 한다 (1판 범위)

| 화면 | 바꾸는 곳 |
|---|---|
| 시공 폰 카드 | `foms/services/construction_dashboard_display.py` — `thumb` = 작은 그림 길, `view` = 원본 |
| 시공 태블릿 작업 화면 | `tablet_workmode_body.html:120` — 무대는 `view` |
| 출고 폰 카드 · 생산 목록 | `foms/services/erp_mobile_order_display.py:157-176` — 썸네일 없는 그림 행은 작은 그림 길 |
| 생산 태블릿 시트 도면 줄 | `foms/services/production_sheet_view.py:115-130` |
| 도면 작업실 폰 카드 | `foms/services/drawing_workbench_display.py:110-135` (시험 `tests/domains/test_drawing_workbench_mobile.py:247-252` 가 지금 동작을 굳히고 있어 같이 고친다) |
| 협력사 포털 목록(도면 작업 중, 96x68 · 36x26) — **1판에 넣음(§7 결정 2)** | `foms/services/partners/drawing_list_thumbs.py` 에 `thumb` 칸, `templates/partner/partials/drawing_thumbs.html` · `order_rows.html` 이 그것을 `<img src>` 로. 확대 창(lightbox)은 `url`(원본) 그대로. 주문 도면 탭 큰 카드(16:9)는 원본 유지 |
| 주문 상세 폰 첨부 칸(3열 약 110px) — **1판에 넣음(§7 결정 2)** | `foms/services/erp_mobile_order_display.py` `_mobile_attachment_item_dict` 에 `tile_url`(만들어 둔 `thumbnail_key` 우선, 없고 그림이면 작은 그림 길), `templates/orders/partials/order_detail_mobile_v2.html` 의 `<img src>` 만 바꿈. `data-foms-attachment-view-url`(눌러 크게 보기)은 원본 그대로 |

스키마 · 저장 자료는 **안 바꾼다.** 작은 그림 이름은 원본 key 에서 계산하므로 DB 칸도, `drawing_current_files` 수정도, 마이그레이션도 없다. 대시보드 캐시를 비울 일도 없다(주소가 처음부터 작은 그림 길이다).

### 3-4. 지우기

저장소 삭제 작업이 원본을 지울 때 형제 작은 그림(`sthumb320_`)도 같이 지운다 — `foms/services/storage_delete_handler.py:63-66`. 원본이 지워진 뒤에는 문지기가 404 를 주므로 남아 있어도 열리지는 않는다.

## 4. 하지 않는 것 (1판)

- **원본 주소의 `no-store` 규칙은 안 건드린다.** 크게 보기는 지금 그대로다. 캐시를 풀면 권한이 바뀐 뒤에도 기기에 남는 문제가 따라와서 따로 정할 일이다.
- 고객 공유 링크 — 큰 보기가 목적이라 원본이 맞다.
- ~~협력사 포털 목록, 주문 상세 폰 첨부 칸~~ — §7 결정으로 1판에 넣었다. 채널톡 작은 창만 2판 후보.
- PDF 미리보기, Cloudflare 쪽 그림 변환, 옛 300px 썸네일 함수 고치기.

## 5. 위험 · 막는 법

| 위험 | 막는 법 |
|---|---|
| 작은 그림 길이 권한을 비켜 간다 | 원본과 같은 문지기 함수, 원본 key 로 판정. 남의 주문 · 지운 첨부 · 협력사 범위 밖 = 403/404 시험 |
| 도면을 바꿨는데 옛 그림이 보인다 | key 가 판마다 새 이름 → 주소가 바뀐다(생산 파트 길과 같은 전제). 교체 뒤 새 주소 시험 |
| web 이 그림 줄이다 멈춘다 | web 은 만들지 않는다. 있나 보기(HEAD) + 읽기만 |
| 첫 방문에 만들기 작업이 수백 개 쌓인다 | 같은 key 는 한 번만 넣는다. 워커 `default` 큐, 작업 시간 상한 |
| 큰 그림(16MP 넘는)으로 워커 메모리가 찬다 | 공유 합본의 픽셀 상한 선례(`foms/api/share.py:107-120`)를 그대로 쓴다. 넘으면 만들지 않고 원본 유지 |
| 태블릿 무대가 흐려진다 | 무대는 `view` 로 바꾸고 시험으로 굳힌다 |
| 작은 그림을 받느라 web 대역폭을 쓴다 | 장당 수십 KB, 기기마다 30일에 한 번. 생산 파트 길이 이미 같은 방식 |

## 6. 검증

1. 시험: 문지기(직원 · 협력사 · 프리랜서 · 지운 첨부), 있음 → 바이트 + 머리글, 없음 → 원본 302 + 작업 한 번만, 그림 아님 404, 투명 PNG 흰 바탕, 회전, 전달 뒤 작업 걸림, 각 화면의 `thumb`/`view` 주소, 지우기 형제.
2. 로컬 준비물 서버(운영 크기 가짜 자료)에서 탭마다 받는 양 전 · 후.
3. 스테이징: 시공 · 출고 · 생산 · 도면 작업실 폰 화면 받는 양 전 · 후, 두 번째 방문에서 0 에 가까운지, 눌러 크게 보기가 원본인지.
4. 운영: 올린 뒤 같은 숫자를 한 번 잰다(사용자 요청 때, 읽기만).

성공 기준: 네 탭 모두 두 번째 방문에서 받는 그림이 **1MB 아래**(지금 7~13MB).

## 7. 사용자 결정

1. 이 방식으로 만들지(작은 그림 길 + 워커가 만들기 + 처음 본 순간 채우기).
2. 1판 범위를 네 탭(시공 · 출고 · 생산 · 도면 작업실)으로 할지, 협력사 포털 · 주문 상세까지 넣을지.

### 결정 기록

- **2026-11-19 사용자: 승인.** 범위 = §3-3 네 탭 + §4 에서 2판 후보로 미뤘던 **협력사 포털 목록 · 주문 상세 폰 첨부 칸까지 1판에 넣는다.** 고객 공유 링크 · 채널톡 작은 창 · PDF · 원본 `no-store` 규칙은 여전히 범위 밖.

## 8. 확인 못 한 것

- 생산 탭 13.2MB 가 정확히 어느 칸에서 나오는지(코드만으로는 못 가름 — 만들면서 잰다).
- 운영 도면 형식 · 크기 분포(읽기 전용 SQL 은 준비됨, 아직 안 돌림).
- 운영 워커 큐가 첫날 얼마나 쌓이는지(스테이징에서 먼저 본다).

## 9. 실제 구현 (2026-11-19, 워킹트리 — 커밋 전)

### 9-1. 바꾼 파일

| 무엇 | 파일 |
|---|---|
| 이름 규칙 · 그리기 · 워커 본체(새 파일) | `foms/services/files/list_thumb.py` — `list_thumb_key`(`sthumb320_<원본 이름>.jpg`) · `list_thumb_url`(서비스용 주소, 그림 아니면 None) · `render_white_jpeg_thumb`(흰 바탕 · EXIF 회전 · LANCZOS · JPEG 85, 긴 변 인자) · `create_list_thumb`(이미 있으면 건너뜀 · 16MP 초과 건너뜀) |
| 예약(새 파일) | `foms/services/files/list_thumb_schedule.py` — `schedule_list_thumb(s)`. 큐 실패 뒤 60초 이 프로세스는 다시 시도하지 않는다 |
| 큐 · 워커 작업 | `foms/services/jobs/queue.py` `enqueue_list_thumb_generation`(Redis `SET NX` 자물쇠 6시간 + job id = key 해시, 3상태) · `foms/services/jobs/tasks.py` `create_list_thumb_for_key` |
| 작은 그림 길 | `foms/api/files/routes.py` `thumb`(`GET /api/files/thumb/<path>`, endpoint `files.thumb`) · `build_file_thumb_url` · `foms/api/files/__init__.py` 내보내기 |
| 허용 목록 | `foms/services/auth/partner_scope.py` · `freelancer_scope.py` 에 `files.thumb`, 분류 표 `tests/support/freelancer_order_scope_tables.py` `HANDLER_CHECKED` |
| 전달 때 미리 만들기 | `foms/api/drawing/erp_orders_drawing.py` `perform_drawing_transfer` — 커밋 · 캐시 무효화 뒤 새 key 마다 예약(try 로 감싸 전달을 깨지 않음) |
| 지우기 | `foms/services/storage_delete_handler.py` `_delete_object` — 원본 다음 `sthumb320_` 형제(그림일 때만), 실패면 재시도 |
| 생산 파트 그리기 공용화 | `foms/web/production/part_thumb.py` `render_part_thumb` = `render_white_jpeg_thumb(raw, 720)`(동작 그대로) |
| 시공 폰 카드 · 태블릿 무대 | `foms/services/construction_dashboard_display.py`(`thumb` = 작은 그림 길, `view` = 원본) · `templates/construction/partials/tablet_workmode_body.html`(무대 `src` = `view`) · `static/js/foms/tablet-construction-workmode.js`(시트 바꿀 때 view-url 먼저) · 핀 `templates/construction/partials/dashboard_body.html` `?v=20261119a` |
| 출고 · 생산 목록 · 주문 대시보드 큐 · 주문 태블릿 시트 · 주문 상세 | `foms/services/erp_mobile_order_display.py` `_attachment_small_url`(큐 카드 `thumb`, 상세 `tile_url`) · `templates/orders/partials/order_detail_mobile_v2.html` |
| 생산 태블릿 시트 · 생산 시트 페이지 | `foms/services/production_sheet_view.py`(`thumb` 칸) · `templates/production/partials/tablet_sheet.html`(112x80 줄) · `templates/production/sheet.html`(112x76 줄만, 큰 그림 · 넘기기는 원본) |
| 도면 작업실 | `foms/services/drawing_workbench_display.py`(`thumb_url` = 행 썸네일 또는 작은 그림 길, 조회 0 그대로) · `templates/drawing/partials/tablet_gallery_body.html`(갤러리 칸 = 원본) |
| 협력사 포털 목록 | `foms/services/partners/drawing_list_thumbs.py`(`thumb` 칸) · `templates/partner/partials/drawing_thumbs.html` · `order_rows.html` |
| 인벤토리 | `docs/harness/foms_failopen_inventory.json`(넓은 catch 5개 추가 — 모두 로그 남김) · 줄 번호만 밀린 `foms_order_mutation_writer_inventory.json` · `foms_audit_coverage_inventory.json` · `foms_orm_bypass_write_inventory.json` |
| 시험 | 새 `tests/domains/test_list_thumb_route.py` · `test_list_thumb_screens.py`, 고친 `test_drawing_workbench_mobile.py` · `test_construction_dashboard_mobile.py` · `test_erp_mobile_order_display.py` · `test_file_access_log.py` · `test_drawing_cancel_transfer_retention.py` · `test_drawing_tablet_review_rows.py` · `test_erp_order_shared_form_scripts.py` · `tests/contracts/runtime/foms_namespace_surface_tests.py`(큐 · 작업 공개 이름) · `tests/postgres/test_wiz_delete.py`(PG 레인 — 로컬 미실행) · `tests/security/test_partner_gate.py` · `test_freelancer_order_scope.py` |

### 9-2. 설계와 달라진 점

1. **큐 중복 막기 = Redis `SET NX` 자물쇠(6시간)** + job id 고정. job id 만으로는 RQ 가 같은 id 를 다시 넣는 것을 막지 않아서다. 자물쇠가 살아 있는 동안 워커가 건너뛴 key(16MP 초과 · 깨진 그림)는 다시 넣지 않는다.
2. **예약 모듈을 따로 뺐다**(`list_thumb_schedule.py`). `foms.services.jobs` 패키지가 열릴 때 `tasks` 를 같이 열어, 한 파일에 두면 순환 import 가 된다.
3. 서비스 레이어 화면들은 주소를 `foms.services.files.list_thumb.list_thumb_url` 로 만든다(서비스 → api import 는 레이어 래칫이 막는다). 주소 앞부분은 한 상수(`LIST_THUMB_ROUTE_PREFIX`)라 `build_file_thumb_url` 과 갈리지 않는다(시험이 `url_for('files.thumb')` 와 셋을 맞춰 본다).
4. **도면 작업실 태블릿 갤러리 칸은 원본 유지.** 칸이 높이 최대 180px · 폭 220~320px 이상(`static/css/foundation/foms-tablet-drawing-gallery.css` 4/3 · `max-height: 180px` · `minmax(220~320px, 1fr)`)이라 태블릿 2배 화면에서 320px 은 흐리다. 폰 카드(76px)만 작은 그림.
5. 주문 상세 칸은 만들어 둔 `thumbnail_key`(옛 300px 썸네일)가 있으면 그것을 먼저 쓴다(큐 카드와 같은 순서). 없을 때만 작은 그림 길.
6. 로컬 저장소: 작은 그림 길은 저장본이 있으면 그것(`immutable`), 없으면 원본을 `no-store` 로 준다(워커가 로컬에 저장하지 못해 자동으로 생기지는 않는다 — 개발용).

### 9-3. 로컬 실측(가짜 자료 · 가짜 R2, 폰 390x844 DPR3, 시공 탭)

| 상태 | 첫 화면 그림 | 끝까지 내린 뒤 | 두 번째 방문(같은 브라우저) |
|---|---|---|---|
| 고치기 전 코드 | 14,667KB(11장) | 207,435KB(112장) | 20,332KB · 끝까지 207,435KB |
| 고친 뒤 · 작은 그림 아직 없음(워커 없음) | 14,667KB | 207,435KB | 같음(원본으로 떨어짐 — 지금과 같다) |
| 고친 뒤 · 작은 그림 저장됨 | **229KB** | **3,240KB** | **0KB** |

- 작은 그림 평균 28.7KB(771장, 원본 0.7~3.3MB). 카드 칸 110장 모두 그려짐(깨짐 0). 눌러 크게 보기 = `/api/files/view/...`(원본 3024x4032). 태블릿 작업 화면 무대 = 원본(naturalWidth 2480, 시트 바꾼 뒤도 2480).
- 재는 법 함정: Playwright `context.route` 를 쓰면 HTTP 캐시가 꺼져 두 번째 방문이 늘 다시 받는다 — 캐시를 잴 때는 CDP Fetch 로만 막는다.

## 10. 스테이징 확인 뒤 고친 것 (2026-11-19)

- 스테이징 실측: 원본이 있는 그림 10개 모두 첫 요청 302 → 약 34초 안에 200(320px, 5~13KB, 30일 immutable). 워커 · Redis 자물쇠 실동작 확인. 다시 방문 0KB.
- **옛 300px 썸네일(`thumb_`)이 있는 첨부도 작은 그림 길을 먼저 쓴다.** 처음엔 옛 썸네일을 먼저 골랐는데, 그 주소는 원본 보기 길(no-store 302)이라 탭에 다시 들어갈 때마다 또 받았다(생산 70칸 · 시공 15칸). 투명 PNG 검정 · 누운 사진 문제도 같이 피한다.
- 남는 것: 확장자 없는 옛 key 는 작은 그림 대상이 아니라 원본으로 나간다(스테이징 시공 2칸 · 생산 8칸).

