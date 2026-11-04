# 아이폰 사진(HEIC) 서버에서 JPG로 바꾸기 SPEC (2026-11-04 초안 · 승인 전)

등급: 코어 변경(파일 업로드 API · R2 저장 · 백그라운드 작업). 아래 §4 결정을 받은 뒤 구현한다.
선행: `docs/specs/2026-11-02-foms-notices_SPEC.md`(공지 사진 — HEIC 를 이미 서버에서 다시 그린다).
같이 들어간 첫 단계: 주문 모바일 갤러리 업로드 `accept` 에서 `.heic,.heif` 제거(커밋 33a1e74).

## 0. 왜 하나

- Windows 크롬은 HEIC 를 화면에 띄우지 못한다. 사무실 PC 에서 아이폰 원본 사진이 깨져 보인다.
- 브라우저에서 바꾸기는 HEIC 를 여는 브라우저(사파리)에서만 된다. 정작 문제가 되는 PC 크롬에서 올리는 HEIC 는 못 바꾼다. 그래서 서버에서 바꾼다.
- 서버에는 `pillow-heif==1.8.1` 이 이미 있고, 공지 사진(`foms/services/notices/images.py:97` `_open`)이 같은 방법을 쓰고 있다.

## 1. 지금 코드의 사실 (2026-11-04 확인)

| 경로 | HEIC 를 받나 | 지금 결과 |
|---|---|---|
| 주문 첨부(실측·도면·시공·AS) direct 업로드 `/api/upload/session(/batch)` → `/api/orders/<id>/attachments/complete` | **안 받음** — `ERP_MEDIA_ALLOWED_EXTENSIONS`(`foms/services/files/upload_policy.py:12`)에 없음, 세션 발급 단계 `allowed_erp_attachment_file` 에서 400 | "허용되지 않은 파일 형식입니다." 로 실패. R2 에는 안 올라감 |
| 채팅 `/api/chat/upload/*` | **안 받음** — `CHAT_ALLOWED_EXTENSIONS` 에 없음 | 실패 |
| 협력사 도면 수정 요청 사진 `_upload_photos`(`foms/api/partner/__init__.py:357`) | **받음** — `_PHOTO_EXTS` 에 `heic` | **HEIC 원본 그대로 R2 저장.** 썸네일 없음, PC 크롬에서 안 보임 |
| 공지 사진 `foms/services/notices/images.py` | 받음 | 서버에서 JPG(긴 변 2000px, 품질 85)로 다시 그려 저장 — 이미 해결됨 |
| 클라이언트 압축 `static/js/runtime/upload-progress.js:57` | 대상 아님 | (참고) JPG·PNG·WEBP 만 줄임 |

바로잡음: 앞선 대화에서 "HEIC 는 원본 그대로 R2 에 올라간다"고 했지만, 주문 첨부와 채팅은 **올라가지 않고 실패**한다. HEIC 원본이 R2 에 쌓이는 곳은 협력사 수정 요청 사진뿐이다.

그래서 현장 사용자가 겪는 문제는 둘이다.
1. 주문 첨부·채팅에서 HEIC 를 고르면 "허용되지 않은 형식"으로 실패한다(사진을 다시 골라야 한다).
2. 협력사가 올린 HEIC 는 우리 PC 에서 보이지 않는다.

## 2. 동작 (제안)

### 2-1. 공통 변환 함수 `foms/services/files/heic_convert.py` (새 파일)
- `is_heic(filename, data) -> bool` — 확장자 `heic/heif` 이거나 `pillow_heif.is_supported(data)`.
- `heic_to_jpeg(data) -> bytes`
  - `pillow_heif.open_heif(data, convert_hdr_to_8bit=True)` → Pillow 그림 → `ImageOps.exif_transpose`.
  - 긴 변 **2560px** 까지 줄이고(그보다 작으면 그대로) JPEG 품질 **85** 로 저장.
  - 메타데이터(EXIF · GPS 위치)는 지운다 — 공지 사진과 같은 규칙.
  - 픽셀 상한 60,000,000 · 바이트 상한 20MB 초과면 `HeicConvertError`.
- Pillow 전체에 `register_heif_opener` 하지 않는다(공지 사진과 같은 이유 — 다른 업로드의 받는 형식 규칙을 바꾸지 않게).
- 공지 사진은 이번에 바꾸지 않는다(이미 잘 돈다). 나중에 이 함수로 옮길 수 있다.

### 2-2. 주문 첨부 (direct 업로드)
1. `ERP_MEDIA_ALLOWED_EXTENSIONS` 에 `heic`, `heif` 추가. `storage._get_content_type` 에 `image/heic`·`image/heif`, `DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES` 에도 추가. `get_erp_media_max_size` 의 사진 목록에 넣어 20MB 상한.
2. 업로드는 지금처럼 브라우저 → R2 직접(HEIC 원본).
3. `complete` 에서 첨부 줄을 만들고 커밋한 뒤, HEIC 면 썸네일 대신 **변환 작업**을 예약한다(기존 `schedule_order_attachment_thumbnail_generation` 과 같은 길: RQ 먼저, 안 되면 ThreadPool).
4. 변환 작업:
   - R2 에서 HEIC 를 읽는다 → `heic_to_jpeg` → 같은 폴더 `<이름>.jpg` 새 key 로 올린다.
   - 첨부 줄을 잠그고(`FOR UPDATE`) `storage_key`·`filename`(.jpg)·`file_size` 를 바꾼다. 줄이 이미 지워졌으면 새 JPG 를 지우고 끝낸다.
   - 첨부 이벤트 `ATTACHMENT_CONVERTED`(새로 추가, 이전 key → 새 key)를 남긴다.
   - 이어서 JPG 썸네일을 만든다(기존 함수 재사용).
   - 원본 HEIC 처리는 §4 결정 1 에 따른다.
   - 대시보드 첨부 캐시 무효화(`ATTACHMENT_DASHBOARD_FAMILIES`).
   - 실패하면 HEIC 를 그대로 두고 오류만 기록한다(업로드 자체는 성공 상태 유지).
5. 변환이 끝나기 전 몇 초 동안은 PC 에서 파일 아이콘으로 보일 수 있다. 화면은 이번에 따로 바꾸지 않는다.

### 2-3. 협력사 수정 요청 사진
- 서버가 바이트를 직접 받는 길이라 **올리기 전에 바로** `heic_to_jpeg` 로 바꾸고 `.jpg` 이름으로 저장한다(최대 10장, 작업 예약 불필요).
- 바꾸지 못하면 "사진을 읽지 못했습니다. JPG 로 다시 올려 주세요." 400.

### 2-4. 이번에 하지 않는 것
- 채팅 HEIC 받기(§4 결정 3 에서 고르면 같은 함수로 2-3 방식 적용).
- 동영상 변환.
- 브라우저에서 HEIC 바꾸기.

## 3. 검증

- 단위: `tests/domains/test_heic_convert.py` — `pillow_heif` 로 테스트용 HEIC 를 만들어 JPEG 로 바뀌는지, 회전(EXIF) 반영, GPS 제거, 긴 변 2560 제한, 깨진 파일은 `HeicConvertError`.
- 계약: 주문 첨부 허용 목록에 `heic/heif`, 협력사 업로드가 `.jpg` 로 저장, `register_heif_opener` 를 부르지 않음.
- 변환 작업: 가짜 저장소로 key·filename·size 갱신, 지워진 첨부일 때 새 JPG 정리, 실패 시 원본 유지.
- 앱: `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1`.
- 스테이징: 아이폰(사파리)과 PC 크롬에서 각각 HEIC 를 주문 첨부로 올려 PC 크롬에서 보이는지 확인.

## 4. 사용자 결정 (받아야 함)

1. **원본 HEIC 를 남길까?** — 추천: **지운다.** 화질 차이가 거의 없고, 위치정보가 담긴 원본이 남지 않는다. (남기면 R2 용량이 사진 1장당 2~5MB 늘어난다.)
2. **바꾼 JPG 크기** — 추천: **긴 변 2560px · 품질 85.** (PC 화면에서 확대해도 충분. 클라이언트 압축의 1920px 보다 조금 크게 둔다.)
3. **범위** — 추천: **주문 첨부 + 협력사 사진.** 채팅은 다음에.
4. **이미 R2 에 있는 협력사 HEIC 도 바꿀까?** — 추천: 먼저 개수를 세어 보고 정한다(postgres 연결 후 `OrderAttachment`·수정 요청 기록에서 `.heic` 수 조회).
