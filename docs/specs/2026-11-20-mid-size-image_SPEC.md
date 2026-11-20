# 중간 크기 그림(긴 변 640) — 설계서 (1판)

> 작성일 2026-11-20 | 상태 **승인됨 → 구현**(2026-11-20, 워킹트리 변경 — 커밋 전) | 등급 `**B`(파일 길 · 워커 작업 = 코어 변경)
> 계기: 작은 그림 설계서(`docs/specs/2026-11-19-list-drawing-small-image_SPEC.md`) 2판 조사에서 "칸이 커서 320 으로는 흐린 자리" 16곳이 남았다. 그중 가장 많이 받는 화면이 AS 태블릿 전후 대조 격자다. 사용자 선택 "AS 태블릿 대조 격자 설계서로 넘어가기"(11-20).

## 0. 한 줄

320 작은 그림으로는 흐려지는 **중간 크기 칸**(화면에서 160~320px 로 보이는 칸)에 원본 대신 긴 변 640 그림을 준다. 이미 운영에 있는 작은 그림 길에 크기 하나를 더하는 일이다. 눌러서 크게 볼 때는 지금처럼 원본이다.

## 1. 왜 하나

AS 태블릿 전후 대조 격자(로컬 가짜 자료, 1194x834 · 2배 화면, 사진 71칸):

| | 지금 |
|---|---|
| 첫 화면에서 받는 그림 | 10,830KB (원본 11장 + 옛 300px 썸네일 2장) |
| 끝까지 내리면 | 58,437KB |
| 다시 들어가면 | 같은 양을 또 받는다 |

- 칸은 234x176px 인데 주는 것은 폰 사진 원본(3024x4032, 장당 약 1MB 이상)이다.
- 2배 화면에서 이 칸을 또렷하게 채우려면 긴 변 468px 가 필요하다. 320 은 모자라고, 640 이면 넉넉하다.
- 숫자는 가짜 그림으로 잰 값이다. 운영 실제 사진 크기 · 장수로는 아직 재지 않았다(§8).

## 2. 지금 코드의 사실 (직접 확인)

- 대조 격자 칸: `templates/cs/partials/tablet_as_compare_body.html:183`, `:197` — `<img src="{{ p.thumb }}" loading="lazy">`, 눌러 크게 보기는 `data-foms-lightbox-src="{{ p.full }}"`(원본). **칸 주소와 뷰어 주소가 이미 나뉘어 있어** 칸 주소만 바꾸면 된다.
- 주소 만드는 곳: `foms/services/as_dashboard_display.py:216-219` — 옛 썸네일(`thumbnail_key`)이 있으면 그것, 없으면 원본. 둘 다 `/api/files/view/`(no-store 302)라 브라우저가 기억하지 못한다.
- 칸 크기: `static/css/foundation/foms-tablet-as-compare.css:294-307` — `minmax(120px, 1fr)` · 4:3. 태블릿 폭에 따라 약 120~240px.
- 작은 그림 길(운영 #873~#876): `GET /api/files/thumb/<원본 key>` — 문지기는 원본 보기와 같은 함수, 저장본(`sthumb320_<이름>.jpg`)이 있으면 30일 immutable, 없으면 워커에 한 번 예약하고 이번만 원본 302. web 은 그림을 줄이지 않는다(`foms/api/files/routes.py` 의 `thumb`, `foms/services/files/list_thumb.py`, `list_thumb_schedule.py`).
- 그리기 함수 `render_white_jpeg_thumb(raw, long_edge, ...)` 는 이미 긴 변을 인자로 받는다(생산 파트 720 이 같은 함수를 쓴다).

## 3. 동작 (제안)

### 3-1. 작은 그림 길에 크기 하나를 더한다

`GET /api/files/thumb/<원본 key>?w=640`

1. 허용 크기는 **320(기본) · 640 둘뿐**. 다른 값은 400. 아무 크기나 받으면 저장소에 파생 파일이 끝없이 쌓인다.
2. 문지기 · 감사 기록 규칙 · 캐시 머리글 · "없으면 워커 예약 + 이번만 원본" 은 320 과 똑같다.
3. 저장 이름은 원본 옆 `sthumb640_<원본 이름>.jpg`. 주소에 크기가 들어가므로 브라우저 캐시도 크기별로 따로다.
4. 워커 작업 · 중복 막기 자물쇠 · 작업 id 에 크기를 넣는다(같은 key 의 320 과 640 이 서로 막지 않게).
5. 원본을 지울 때 640 형제도 같이 지운다. 파생 파일 접두 목록에 `sthumb640_` 를 더한다(작은 그림의 작은 그림 금지).
6. 주소 만들기: `list_thumb_url(key, size=640)`. 그림 판정은 지금 정본(`is_list_thumb_source`) 그대로.

- 크기: 긴 변 640 JPEG(품질 85), 흰 바탕, 회전 반영. 장당 약 50~110KB(추정 — 320 실측 5~29KB 에서 넓이 4배).
- 720 이 아니라 640 인 까닭: 2배 화면에서 320px 칸까지 맞고, 720 보다 약 20% 가볍다. 생산 파트 카드의 720(`pthumb720_`)은 다른 길 · 다른 문지기라 그대로 둔다.

### 3-2. AS 태블릿 대조 격자가 640 을 쓴다 (1판 범위)

`foms/services/as_dashboard_display.py` 의 전후 사진 항목: `thumb` = 640 길(그림이 아니면 지금처럼 옛 썸네일 · 원본), `full` = 원본 그대로. 템플릿은 안 바꾼다.

### 3-3. 미리 만들기

1판은 **처음 본 순간 채우기만** 한다(320 과 같은 방식). AS 사진을 올릴 때 미리 만드는 것은 하지 않는다 — 올린 사진을 태블릿 대조 화면에서 다시 볼지 알 수 없고, 안 볼 사진까지 만들면 저장소만 쓴다.

## 4. 하지 않는 것 (1판)

- **AS 폰 카드 사진(44px).** 사진을 켜는 스위치가 설정값이 비면 늘 꺼지게 짜여 있고(`as_dashboard_display.py:119`), 운영 설정값을 아직 모른다. 켜고 끄는 것은 화면이 바뀌는 일이라 따로 정한다.
- 다른 중간 크기 칸(§7 의 후보). 1판 숫자를 보고 정한다.
- 원본 주소의 `no-store` 규칙, 고객 공유 링크, 생산 파트 720 길.

## 5. 위험 · 막는 법

| 위험 | 막는 법 |
|---|---|
| 크기 인자로 파생 파일이 끝없이 생긴다 | 허용 크기 둘뿐, 그 밖은 400. 시험으로 굳힌다 |
| 640 길이 권한을 비켜 간다 | 320 과 같은 문지기 · 같은 시험(남의 주문 · 지운 첨부 · 협력사 범위) |
| 태블릿에서 흐리다 | 표시 칸 최대 240px × 2배 = 480 < 640. 스테이징 태블릿 화면에서 naturalWidth 로 확인 |
| 워커가 한꺼번에 바쁘다 | 대조 화면 첫 방문 때 보이는 칸만(lazy) 예약된다. 320 과 같은 큐 · 같은 중복 막기 |
| 320 과 640 이 서로의 예약을 막는다 | 자물쇠 · 작업 id 에 크기 포함. 시험 |
| 원본을 지운 뒤 640 이 남는다 | 삭제 작업이 두 형제를 다 지운다. 문지기는 원본 key 로 판정하므로 남아도 열리지 않는다 |

## 6. 검증

1. 시험: 허용 크기 · 그 밖 400, 저장본 있음/없음, 크기별 저장 이름 · 자물쇠 · 작업 id, 삭제 형제 둘, 대조 격자 `thumb`/`full` 주소, 그림 아닌 파일.
2. 로컬 준비물 서버: AS 태블릿 대조 화면 첫 화면 · 끝까지 · 다시 방문 KB 전 · 후, 칸 그림 naturalWidth ≥ 480, 눌러 크게 보기 = 원본.
3. 스테이징: 같은 숫자(원본이 남아 있는 AS 주문이 있으면).
4. 운영: 올린 뒤 한 번(사용자 요청 때, 읽기만).

성공 기준: 대조 화면 **다시 방문 때 받는 그림 0 에 가깝게**, 첫 방문도 지금의 1/5 아래.

## 7. 다음 판 후보 (같은 640 을 쓸 수 있는 칸 — 조사 보고의 "큰 자리" 가운데)

- 도면 작업실 태블릿 갤러리(220~320 x 180)
- PC 대시보드 첨부 창 카드 · 주문 수정 첨부 카드(높이 180~220)
- 도면 작업실 전달 · 수정 창 대상 카드 · 고객 발송 창 칸(폭 230~470 — 470 은 640 으로도 2배 화면엔 모자람)
- PC 교체 대상 카드, 협력사 완공 · AS 사진(약 175px)
- 시공 완료 태블릿 시트 사진(태블릿 반 폭 — 640 으로 모자랄 수 있음)

무대 · 뷰어 · 인쇄 · 도면 마법사 캔버스는 원본이 목적이라 대상이 아니다.

## 8. 사용자 결정

1. 이 방식(작은 그림 길에 640 을 더함)으로 만들지.
2. 1판 범위를 AS 태블릿 대조 격자만으로 할지, §7 후보 가운데 또렷하게 맞는 칸(도면 태블릿 갤러리 · PC 첨부 창 카드 · 교체 대상 카드 · 협력사 완공 사진)까지 넣을지.

### 결정 기록

- **2026-11-20 사용자: 승인.** 1판 범위 = AS 태블릿 대조 격자 + §7 후보 가운데 **도면 작업실 태블릿 갤러리 · PC 대시보드 첨부 창 카드 · PC 교체 대상 카드 · 협력사 완공 / AS 사진.** AS 폰 카드(44px) · 회차 표 · `as_thumb_enabled` 스위치, 주문 수정 첨부 카드, 도면 작업실 전달 · 수정 창 · 고객 발송 창, 시공 완료 태블릿 시트는 여전히 범위 밖.

## 9. 확인 못 한 것

- 운영 AS 사진의 실제 크기 · 주문당 장수, 태블릿으로 AS 대조 화면을 얼마나 자주 여는지.
- 640 JPEG 실제 바이트(추정만 했다 — 만들면서 잰다).
- 스테이징에 원본이 남아 있는 AS 사진이 있는지.

## 10. 실제 구현 (2026-11-20, 워킹트리 — 커밋 전)

### 10-1. 바꾼 파일

| 무엇 | 파일 |
|---|---|
| 크기 규칙 · 이름 · 주소 · 작업 id · 워커 본체 | `foms/services/files/list_thumb.py` — `LIST_THUMB_SIZES = {320: sthumb320_, 640: sthumb640_}`, `list_thumb_key(key, size=320)` · `list_thumb_url(key, size=320)` · `mid_thumb_url(key)` · `list_thumb_query` · `list_thumb_sibling_keys` · `list_thumb_job_id(key, size=320)` · `create_list_thumb(..., size=320)`, `_DERIVED_PREFIXES` 에 `sthumb640_` |
| 길 | `foms/api/files/routes.py` — `?w=` 판정(`_thumb_size_arg`: 없음=320, 글자 그대로 `320` · `640` 만, 그 밖 400), `build_file_thumb_url(key, size=320)` |
| 예약 · 큐 · 작업 | `list_thumb_schedule.py` `schedule_list_thumb(key, size=320)` · `jobs/queue.py` `enqueue_list_thumb_generation(..., size=320)` · `jobs/tasks.py` `create_list_thumb_for_key(storage_key, size=320)` |
| 지우기 | `foms/services/storage_delete_handler.py` — 원본 다음 `sthumb320_` · `sthumb640_` 둘(없어도 성공, 실패면 재시도) |
| Jinja 필터 | `foms/services/erp_template_filters.py` — `mid_thumb_url` 추가(`list_thumb_url` 그대로) |
| AS 태블릿 대조 격자 | `foms/services/as_dashboard_display.py` `_compare_photo_entry` — `thumb` = 640 길(만들 수 없으면 옛 썸네일 · 원본), `full` 원본. 템플릿은 그대로(이미 `data-foms-lightbox-src="{{ p.full }}"`). AS 폰 카드 · 스위치와 함수가 갈려 있어 따로 가를 일 없음 |
| 도면 작업실 태블릿 갤러리 | `foms/services/drawing_workbench_display.py`(`mid_url` 칸 더함, 폰 카드 `thumb_url` 320 그대로) · `templates/drawing/partials/tablet_gallery_body.html`(칸 `src` = `mid_url or view_url`) |
| PC 첨부 창 카드 4곳 | `foms/api/files/common.py` `serialize_attachment` 에 `mid_url` 더함 · `erp-dashboard-core.js` · `construction/dashboard.js` · `templates/production/partials/scripts.html` · `cs/as-dashboard.js` 칸 = `a.mid_url \|\| 지금 주소`(뷰어는 목록의 `view_url`) |
| PC 교체 대상 카드 | `erp-dashboard-gateway.js` `gatewaySmallUrl(key, size)`(640 이면 `?w=640`, 320 은 그대로 · 파생 접두에 `sthumb640_`) · `erp-dashboard-attachments.js` `buildDrawingTargetCards` = 640 + `onerror` 로 원본 한 번 되돌림 |
| 협력사 완공 · AS 사진 | `foms/web/partner/__init__.py` `_with_urls` — `thumb_url` = 640 길(없으면 옛 썸네일 · 원본), 확대 창은 `url`(원본) |
| 핀 `20261120m` | `erp-dashboard-entry.js`(core · gateway · attachments) · `layout_scripts.html`(entry) · `construction/partials/scripts.html` · `cs/partials/as_dashboard_body.html` |
| 인벤토리(줄 번호만) | `docs/harness/foms_failopen_inventory.json` · `foms_audit_coverage_inventory.json` |
| 시험 | 새 `tests/domains/test_mid_thumb.py`(길 · 워커 · 지우기) · `test_mid_thumb_screens.py`(화면 · Node 실행) · `tests/security/test_partner_mid_thumb.py` |

### 10-2. 설계와 달라진 점

1. **320 은 작업 인자 · job id · 자물쇠 키를 예전 그대로 둔다**(`(key,)` · `list_thumb_<sha1>` · `foms:list_thumb_<sha1>:lock`). 640 은 `(key, 640)` · `list_thumb640_<sha1>`. 배포 순간 큐에 든 옛 작업(인자 1개)은 새 워커에서 320 으로 돈다(인자 기본값). 반대로 **새 web 이 넣은 640 작업을 아직 옛 워커가 받으면** 인자 2개라 실패하고, 그 key 의 640 은 자물쇠 6시간 동안 다시 예약되지 않는다(원본이 계속 나간다) — WORKER 를 web 과 같이 올리면 생기지 않는다.
2. **`?w=` 는 글자 그대로만** 받는다(`0640` · ` 640` · 빈 값 = 400). 같은 그림에 주소가 여럿 생기지 않게. 크기 판정은 문지기보다 먼저라, 남의 주문 key 라도 허용 밖 크기는 403 이 아니라 400 이다(파일 존재 여부는 드러나지 않는다).
3. **640 이 아직 없을 때는 옛 300px 썸네일이 아니라 원본으로 떨어진다**(320 2판 결정과 같은 순서 — 옛 썸네일도 no-store 302 라 다시 받는다). 그래서 워커가 만들기 전 첫 방문은 지금보다 무겁다(아래 표 A). 워커가 돌고 나면 다시 방문 0KB.
4. PC 교체 대상 카드는 서버가 아니라 JS 가 key 로 주소를 만든다(2판 도면 창구와 같은 방식, 판정은 서버와 같은 key 묶음으로 시험).

### 10-3. 로컬 실측(가짜 자료 · 가짜 R2, `scratchpad/thumb_impl/mid/mid_summary.json`)

| 화면 | 상태 | 첫 화면 | 끝까지(또는 창) | 다시 방문 |
|---|---|---|---|---|
| AS 태블릿 대조 격자(1194x834 · 2배, 71칸) | 고치기 전(조사 때 옛 코드, 같은 씨앗) | 10,830KB | 58,437KB | 11,799KB · 끝 58,437KB |
| | 고친 뒤 · 640 아직 없음 | 12,459KB | 86,953KB | 14,356KB · 끝 86,953KB |
| | 고친 뒤 · 640 저장됨 | **961KB** | **5,626KB** | **0KB** |
| 도면 작업실 태블릿 갤러리(1칸) | 없음 → 저장됨 | 730KB → **133KB** | 같음 | 730KB → **0KB** |
| PC 첨부 창 카드(1440 · 2배, 8칸) | 없음 → 저장됨 | 창 7,819KB → **552KB** | — | 7,819KB → **0KB** |
| PC 교체 대상 카드(2장) | 없음 → 저장됨 | 창 6,391KB → **258KB** | — | 6,391KB → **0KB** |
| 협력사 완공 사진(폰 390 · 3배, 8칸) | 저장됨 | 552KB | — | 0KB |

- 칸 그림 naturalWidth: 세운 사진 480x640 · 누운 도면 640x453 — 대조 격자 칸 234x176(2배 = 468x352)을 cover 로 채운다. 눌러 크게 보기 = `/api/files/view/<원본>`(3024x4032 · 2480x1754).
- 640 실제 바이트(가짜 그림): 사진 원본(3024x4032 JPEG 약 1MB) → 66~70KB(평균 68KB), 도면 원본(2480x1754 PNG, 잡음 많은 가짜) → 127~132KB. 같은 그림 320 은 21~33KB. 운영 도면은 흰 바탕이 넓어 이보다 작을 가능성(추정).
- 워커 예약: 71칸 대조 화면 두 번 방문에 640 작업 71개(같은 key 두 번째는 자물쇠가 막음 71번), 같은 key 의 320 예약과 서로 안 막음.
- 협력사 화면은 가짜 R2 가 같은 앱 안이라 협력사 문지기가 원본 302 뒤 주소를 막는다(준비물 한계) — 640 없는 상태 · 확대 창 그림 읽기는 재지 못했고, 확대 창 주소가 원본인 것만 확인했다.

### 10-4. 남은 것

- PC 교체 대상 카드의 칸 CSS(`static/css/contexts/orders/dashboard-grid.css` 의 `.drawing-target-card-*`)가 `@media (max-width: 992px)`(884행~1686행) 안에 들어 있어, 993px 넘는 PC 에서는 칸 크기가 안 먹고 그림이 제 크기로 그려진다(전부터 — 640 으로 바꾼 뒤 2480px → 640px). 이번 범위 밖, 따로 고칠 일.
- 768px 아래(두 칸 격자) 교체 대상 카드는 칸 폭이 약 370px 까지 넓어져 2배 화면에서 640 이 약간 모자랄 수 있다(1.7배).
- 스테이징 · 운영 실측(§6-3 · 6-4).
