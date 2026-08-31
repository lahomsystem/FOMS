# 브리프 — 모바일 도면 일괄 저장을 '합본 사진 1장'으로 (2026-08-31)

작업 트리: `c:\tmp\foms-s-kakaoshare` (branch `session/kakaoshare2`, base origin/deploy)

## 배경

고객이 카톡으로 받는 도면 공유 링크(`/s/<token>`)에 "도면 전체 저장 (N개 · ZIP)" 버튼이 있다.
사용자(대표) 지적: **모바일에서 ZIP 은 압축을 풀어야 해서 못 쓴다. 모바일에선 ZIP 을 빼라.**

배경 사실(이미 확인됨):
- 카카오톡 인앱 웹뷰는 `<a download>` 를 무시하는 사례가 있고 `window.print()` 는 구현 자체가 없다.
- 반면 **이미지를 길게 누르면 사진첩 저장**은 다운로드 권한 없이 동작한다 — 인앱 브라우저에서 유일하게 확실한 길.
- `Pillow==10.1.0` 이 이미 requirements 에 있고 `foms/services/storage.py` 가 쓴다.
- `foms/services/storage.py:346` 에 `read_file_bytes(key)` 가 있다(R2/S3 get_object, 실패 시 None).

## 만들 것

### 1) 합본 사진 라우트 — `GET /s/<token>/drawings-sheet.png`

`foms/api/share.py` (`share_view_bp`). 기존 ZIP 라우트 `download_shared_drawings_zip` 바로 아래에 둔다.

- 토큰 검증은 **반드시 `_resolve_share_target(token)` 재사용** (해시→회수→만료→주문 활성). 새로 구현 금지.
- `row.kind` 가 `drawing`/`bundle` 일 때만. `estimate` 는 404.
- storage_type 이 r2/s3 아니면 503 (기존 fail-closed 규약).
- 파일 수집은 `_collect_drawing_files(order)` 재사용(주문 격리 allow-list 승계).
  그중 **이미지만**(`_is_image`) 합친다. PDF 등 비이미지는 이번 범위 밖 — 합치지 않고 무시한다.
- 이미지 0장이면 404.
- 합성 규칙: 세로로 이어 붙인다. 폭은 가장 넓은 장 기준으로 통일하되 상한 `_SHEET_MAX_WIDTH`(1400px)
  — 그보다 넓으면 비율 유지 축소. 장 사이 여백 `_SHEET_GAP`(16px), 배경 흰색.
  총 픽셀이 `_SHEET_MAX_PIXELS`(40_000_000) 를 넘으면 전체를 비율대로 축소해 맞춘다(거절하지 말 것 —
  고객이 받을 길이 없어진다). 축소해도 못 맞추는 극단이면 503 + 개별 저장 안내.
- 한 장이라도 못 읽으면 **503**(ZIP 라우트와 같은 규칙 — 일부만 담긴 결과물을 내보내지 않는다).
  기존 `_MSG_ZIP_PARTIAL` 과 같은 뜻의 문구를 쓰되 '사진' 표현으로.
- 응답: `image/png`. 기본은 **inline**(길게 눌러 저장하려면 화면에 떠야 한다).
  `?download=1` 이면 `_attachment_disposition()` 으로 attachment. `Cache-Control: no-store`.
- 감사 1건: `record_file_access('FILE_DOWNLOAD', storage_key=f'share/{row.id}', user_id=None, ip=..., user_agent=..., order_id=order.id)`
  — ZIP 라우트와 같은 액션명 재사용(새 액션 문자열은 `audit_message_display` 등재가 없으면 CI red).
- `share_service.record_view` 는 호출하지 않는다(ZIP 라우트와 같은 판단 — 열람 카운트 부풀림 방지).
- **broad `except Exception` 을 새로 만들지 마라** — `foms_failopen_inventory.json` 게이트가 빨강이 된다.
  Pillow 예외는 좁은 타입(`OSError`, `PIL.UnidentifiedImageError`)으로 잡고 `logger.error` 로 남긴 뒤 503.
- 렌더 라우트(`view_shared_order`)에 템플릿 변수 `share_sheet_url` 을 추가한다(`url_for(...)`).
  기존 `share_zip_url`·`share_drawing_count` 옆에.
  이미지 도면 수 `share_image_count` 도 함께 내려라(합본 버튼 라벨·노출 판정용).

### 2) 열람 페이지 UI — `templates/orders/partials/share_drawing_body.html`

- **모바일(좁은 화면)**: 주 버튼 = "도면 전체 저장 (N장 · 사진 1장)". ZIP 버튼은 **감춘다**.
- **PC(넓은 화면)**: 지금처럼 ZIP 주 버튼. 합본 사진 버튼은 감춘다.
  분기는 **CSS 미디어쿼리(599.98px)** 로 한다 — UA 스니핑 금지(둘 다 마크업에 두고 breakpoint 로 노출 전환).
- 이미지 도면이 0장이면 합본 버튼 자체를 렌더하지 않는다(마크업에서 `{% if %}`).
- 이미지가 1장뿐이면 합본은 의미가 없다 — 지금의 "도면 저장 (1개)" 단건 버튼 그대로 둔다.
- 개별 저장 목록(`<details> 하나씩 저장`)은 그대로 유지한다. PDF 등 비이미지는 여기서 받는다.

### 3) 카드마다 저장 아이콘 — 사용자 명시 요구

각 미리보기 카드 **오른쪽 위**에 미니멀한 다운로드 아이콘 버튼을 얹는다.
- 아이콘은 인라인 SVG(외부 아이콘 폰트 금지, 이 페이지엔 셸이 없다). 아래 화살표 + 받침선, `stroke` 만 쓰는 선형.
- `<a href="{개별 presign attachment URL}" download aria-label="이 도면 저장">` 형태.
  URL 은 `share_download_files` 의 것과 같은 값이어야 한다 — 새 presign 만들지 말고 카드와 인덱스로 짝지어라.
  짝짓기가 불안하면 `_collect_drawing_files` 순서를 그대로 쓰는 구조로 서버에서 카드에 URL 을 실어 내려라.
- **카드 클릭(lightbox 확대)과 아이콘 클릭이 겹치면 안 된다** — 아이콘에서 `event.stopPropagation()`.
  카드는 `<button>` 이고 그 안에 `<a>` 를 중첩하면 HTML 이 깨진다. 아이콘을 카드 **바깥 형제**로 두고
  래퍼에 `position: relative` 를 주는 구조로 만들어라(중첩 인터랙티브 금지).
- 터치 타깃 44px(겉모양은 작게, 히트 영역만 넓히는 `::after` 기법이 `foms-share-contract.css` 에 선례가 있다).
- 이 카드 마크업은 `templates/drawing/partials/drawing_mobile_v2_gallery.html` 공용이다.
  **ERP 화면에는 아이콘이 나오면 안 된다** — 기존 `share_mode` 플래그 안에서만 렌더하라.

### 4) 합본 사진 저장 흐름 — `static/js/orders/share-view.js`

주 버튼(합본)을 누르면:
1. 버튼을 "만드는 중…" 으로 잠그고 `GET /s/<token>/drawings-sheet.png` 를 `<img>` 로 페이지에 붙인다.
2. 이미지 아래에 안내: "이미지를 길게 눌러 사진첩에 저장하세요."
3. 동시에 `<a download>` 로 저장도 시도한다(되는 브라우저에서는 바로 저장).
4. 실패 시 조용히 죽지 말고 안내 문구를 띄운다.
- 기존 presign 만료 안내(`[data-share-expiry-note]`)와 ZIP 버튼 잠금 로직은 유지.
- IIFE + 싱글톤 가드 유지. jQuery 금지.

### 5) 자산 핀

`static/css/orders/foms-share-view.css` / `share-view.js` 를 고쳤으면
`share_view.html`·`share_estimate_view.html`·`share_bundle_view.html` 의 `?v=` 를
`20260831c` → `20260831d` 로 **세 파일 모두** 올려라(핀 드리프트 계약 테스트가 불일치를 잡는다).

## 불변 계약 (깨면 안 됨)

- D6 동결: 계약서 렌더는 스냅샷만. 이번 작업은 도면 축이라 무관하지만 계약서 쪽 파일을 건드리지 마라.
- 주문 격리: 파일 수집은 반드시 `_collect_drawing_files` 경유.
- 인라인 `style=` 속성 금지. 인라인 `<script>` 블록 추가 금지.
- 공용 CSS `static/css/components/foms-drawing-mobile.css` 를 고치지 마라 — ERP 큐 화면이 같이 바뀐다.
  공유 전용 규칙은 `foms-share-view.css` 에 `.foms-share-view` 스코프로.

## 완료 기준 (검증 명령 — 출력 원문을 보고에 붙일 것)

1. `python -c "import app; print('APP_OK')"`
2. `tests/domains/test_order_share_view.py` 에 계약 테스트 추가:
   - 합본 200 + `Content-Type: image/png` + PIL 로 열어 **높이가 개별 장 높이 합보다 크다**(정말 이어붙였는지)
   - 회수/만료 410, 없는 토큰 404, estimate 토큰 404, 이미지 0장 404
   - 한 장 읽기 실패 시 503 (`monkeypatch` 로 `read_file_bytes` 하나만 None)
   - 다른 주문 key 가 섞이지 않는다(주문 격리)
   - `?download=1` 이면 `Content-Disposition` 에 attachment
   - 열람 페이지 HTML 에 합본 버튼 마커·카드 저장 아이콘 마커가 있다
   - ERP 렌더(share_mode 아님)에는 카드 저장 아이콘이 **없다**
3. `python -m pytest tests/domains/test_order_share_view.py tests/domains/test_order_share_api.py tests/contracts tests/domains/test_failopen_inventory.py -q` 전부 통과
4. `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1` exit 0

## 하지 말 것

- PDF → 이미지 변환 (사용자가 "당장은 하지마" 라고 명시)
- git commit/push (총괄이 한다)
- 계약서 관련 파일 수정
