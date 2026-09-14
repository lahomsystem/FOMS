# erporder 첨부 미리보기 — 이미지 클릭 시 전체화면 뷰어 브리프 (2026-09-14, 초안)

> 이 문서는 **초안**이다. CEO 에이전트가 계약(이름·시그니처)과 워커 브리프를 확정한다.
> 다만 아래 "고정" 표시 항목은 총괄이 실제 코드에서 확인한 사실이므로 바꾸지 않는다.

## 1. 문제 (사용자 보고)

erporder 주문 상세에서 첨부(도면 이미지)를 미리보기로 열면, 이미지가 Bootstrap 모달
(`#erpAttachmentPreviewModal`, `modal-lg`) 안에 갇혀 아주 작게 보인다. 도면 치수 글자가 읽히지
않는다. 사용자 요구: **"다른 미리보기처럼 이미지를 클릭하면 크게 볼 수 있게. 다른 미리보기와 같은
방식으로 작동되게."**

### 근본 원인 (고정 — 총괄이 코드에서 확인)

- `static/css/components/foms-form-field.css:644-667` — 데스크톱에서
  `.erp-attachment-preview-zoom-stage` 와 그 안의 `.erp-attachment-preview-img` 가
  `max-height: min(60vh, 520px)`, 스테이지는 `overflow: hidden`. 즉 도면은 520px 높이로 축소되고,
  클릭 확대(2배)는 스테이지 밖으로 잘린다.
- `static/js/foms/attachment-preview-zoom.js:104-127` — 클릭은 `toggleTapZoom()`, 즉 모달 안
  transform scale(최대 4배) 토글일 뿐이다. 모달 밖으로 커질 수 없다.

### "다른 미리보기" 가 무엇인지 (고정)

큐 카드 갤러리·대시보드·모바일 읽기전용 경로는 전체화면 몰입 뷰어
`window.GlobalImageViewer.open(files, index)` 로 간다.

- 정의: `templates/partials/shared/layout_scripts.html:371` (`window.GlobalImageViewer = ...`),
  마크업 `templates/partials/shared/layout_scripts.html:36-59`, 스타일 동 파일 `:1076-1200`.
- 기능: 전체화면(`position:fixed; inset:0; z-index:10600`), 배경 blur, 휠 줌·드래그 팬,
  좌우 화살표·키보드 ←→, ESC 닫기, 다운로드 버튼, 카운터, 모바일 핀치·스와이프.
- 이미 이 경로로 가는 곳: `static/js/foms/erp-attachment-preview-open.js:151-170`(갤러리 다중 이미지),
  `:70-82`(모바일 읽기전용), `static/js/foms/attachment-preview-modal-bridge.js:19-31`.

즉 **데스크톱 erporder 상세만 예외적으로 모달 안 축소 뷰**에 머물러 있다. 그 예외를 없애는 작업이다.

## 2. 목표 / 비목표

**목표**
1. 첨부 미리보기 모달에서 이미지를 클릭(또는 Enter/Space)하면 `GlobalImageViewer` 전체화면으로 열린다.
2. 같은 주문의 다른 이미지 첨부가 있으면 뷰어 좌우 화살표로 넘길 수 있다(클릭한 이미지에서 시작).
3. 편집 모드 기능(항목 연결 select, 공통 첨부로 이동, 삭제)은 모달에 그대로 남는다 —
   뷰어를 닫으면 모달이 그대로 보인다.
4. `GlobalImageViewer` 가 없는 표면에서는 지금의 모달 안 확대가 그대로 남는다(폴백).

**비목표**
- 모달 자체를 없애지 않는다. 모바일 동작(이미 뷰어로 감)을 바꾸지 않는다.
- `#erpEstimatePreviewModal`(견적 미리보기)은 이번 범위 밖. 단 CSS 선택자를 공유하므로
  견적 미리보기가 깨지지 않는지 확인은 범위 안.
- 뷰어 자체(`layout_scripts.html`)는 수정하지 않는다.

## 3. 계약 초안 (이름은 고정, 시그니처는 CEO 가 확정)

`static/js/foms/attachment-preview-zoom.js` 에 추가:

```js
// 전체화면 위임이 가능하면 true 를 돌려주고 뷰어를 연다. 불가하면 false(호출부는 폴백).
window.fomsOpenAttachmentPreviewFullscreen = function (payload) { /* ... */ };
// payload: { files: [{view_url, download_url, filename, key}], index: <number> }
```

`fomsBindAttachmentPreviewImageZoom(bodyEl, options)` 의 `options` 에 추가:

```js
options.fullscreen = function () { return { files: [...], index: n }; }  // 또는 객체
```

- `options.fullscreen` 이 주어지고 `window.GlobalImageViewer.open` 이 있으면,
  이미지 클릭/Enter/Space 는 **전체화면 뷰어**를 연다(모달 안 scale 토글 대신).
- 없으면 지금 동작(`toggleTapZoom`) 유지.
- 모바일 경로(`window.fomsIsMobileImageViewer()` true)는 호출부가 이미 뷰어로 보내므로 변경 없음.

호출부:
- `static/js/orders/erp-order-shared.js:4208 erpOpenAttachmentPreview()` — `__erpAttachments` 중
  이미지 첨부만 모아 `files`, 클릭한 첨부의 위치를 `index` 로 넘긴다.
  **URL 은 그 함수가 이미 계산하는 `stableViewUrl`/`stableDownloadUrl` 규칙을 써야 한다**
  (서명된 R2 URL 은 만료된다 — `:4217-4226`).
- `static/js/foms/erp-attachment-preview-open.js:96-118 openErpAttachmentPreviewModal()` —
  단일 첨부라도 `files: [현재 파일]` 로 넘겨 전체화면이 되게 한다.

## 4. 함정 (반드시 처리 — 총괄이 코드에서 확인한 사실)

1. **Bootstrap 포커스 트랩**: 모달이 열린 채 뷰어를 열면, Bootstrap 5 모달의 focus trap 이
   모달 밖(뷰어 닫기·화살표 버튼)으로 간 포커스를 모달로 되끌어온다. 대책은
   `#erpAttachmentPreviewModal` 에 `data-bs-focus="false"` 를 주거나, 뷰어를 열 때만 모달 인스턴스의
   포커스 트랩을 무력화하는 것이다. 선택은 CEO 가 하되 **실제로 뷰어 버튼이 눌리는지**가 완료 기준.
2. **ESC 중복**: 뷰어는 `document` keydown 으로 ESC 를 처리하고, Bootstrap 모달도 ESC 로 닫힌다.
   뷰어가 열려 있는 동안 ESC 는 **뷰어만** 닫아야 한다(모달은 남는다).
3. **body 스크롤 잠금**: 뷰어 `open()` 은 `document.body.style.overflow = 'hidden'`,
   `close()` 는 이를 되돌린다. 모달이 아직 열려 있으면 잠금이 풀려 뒤 배경이 스크롤된다.
   뷰어를 닫은 뒤 모달이 살아 있으면 잠금을 복구한다.
4. **z-index 는 이미 안전**: `#global-image-viewer` 가 `z-index: 10600`(모달 1055 위).
   새 z-index 를 만들지 마라.
5. **자산 핀(`?v=`) 과 그것을 박은 테스트**: 편집한 JS 파일마다 참조 템플릿의 핀을 올려야 한다.
   - `attachment-preview-zoom.js?v=20260629a` — `templates/orders/object.html:150`,
     `templates/orders/partials/erp_order_js.html:14`,
     `templates/orders/wizard/wizard_shell.html:89`,
     `templates/orders/mobile_order_detail.html:18`,
     `templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html:3`
   - `erp-attachment-preview-open.js?v=20260724a` — `templates/orders/object.html:151`,
     `templates/orders/wizard/wizard_shell.html:90`,
     `templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html:4`
   - `erp-order-shared.js?v=20260904c` — `templates/orders/partials/erp_order_js.html:27`
     그리고 **`tests/domains/test_erp_order_shared_form_scripts.py:73` 이 이 핀 문자열을 단언한다**.
     핀을 올리면 이 테스트도 같이 고쳐야 한다.
6. **`templates/orders/wizard/wizard_shell.html` 은 이미 다른 작업으로 더티**하다.
   그 파일에서는 **핀 한 줄 말고 아무것도 건드리지 마라.**
7. 프로젝트 규약: jQuery 금지, 인라인 스타일 금지(ratchet 테스트가 강제 — 새 스타일은
   `static/css/` 로), `fetch` 는 try/catch + `data.success`, CRLF 등 기존 줄바꿈 보존.

## 5. 파일 소유권 표 (겹치면 안 된다)

| 워커 | 편집 허용 파일 |
| --- | --- |
| W1 zoom-core | `static/js/foms/attachment-preview-zoom.js` |
| W2 erporder | `static/js/orders/erp-order-shared.js` |
| W3 shared+pins | `static/js/foms/erp-attachment-preview-open.js`, `templates/partials/shared/foms_attachment_preview_modal.html`, `templates/orders/object.html`, `templates/orders/partials/erp_order_js.html`, `templates/orders/wizard/wizard_shell.html`(핀 줄만), `templates/orders/mobile_order_detail.html`, `templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html`, `tests/domains/test_erp_order_shared_form_scripts.py`(핀 단언 줄만) |
| W4 test+css | `tests/domains/test_attachment_preview_fullscreen.py`(신규), `static/css/components/foms-form-field.css` |

모든 핀(`?v=`) 편집은 W3 한 명이 한다. W1·W2·W4 는 템플릿을 건드리지 않는다.

## 6. 검증 명령 (완료 기준)

```bash
python -m pytest tests/domains/test_static_js_syntax.py tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_attachment_preview_fullscreen.py -q
python -c "import app; print('APP_OK')"
```

- `test_static_js_syntax.py` 는 `static/js` 전체를 node 로 파싱한다(정적 JS 구문 오류는 여기서만 잡힌다).
- 신규 테스트는 계약을 문자열로 고정한다: zoom 모듈이 `fomsOpenAttachmentPreviewFullscreen` 을
  노출하는지, 호출부 2곳이 `fullscreen` 옵션을 넘기는지, 핀이 올랐는지.
- 화면 확인(총괄 몫): 데스크톱 erporder 상세 → 첨부 클릭 → 모달 → 이미지 클릭 →
  전체화면 뷰어, 화살표·ESC·닫기 후 모달 잔존.

## 7. 워커 공통 규칙

- 워크트리 경로에서 `cd <worktree> && pwd` 로 위치를 확인한 뒤 작업한다.
- git 명령 금지(커밋·브랜치·stash 전부). 편집만 한다.
- 소유권 표 밖의 파일은 **읽기만** 한다.
- 기존 줄바꿈(CRLF/LF)·들여쓰기 스타일을 보존한다.
- 주석·문서는 한국어, 한자 금지.


## 8. 후속 판단 — 견적 미리보기는 범위 밖으로 확정 (2026-09-14)

사용자 요청으로 견적 미리보기(`#erpEstimatePreviewModal`)에도 같은 전체화면 위임을 붙였다가
(`e4cc34622`) **되돌렸다**(`c9827f29c`). 이유는 그 모달에 **데스크톱 진입로가 없기 때문**이다.

- 여는 길은 둘뿐이다: 모바일 미리보기 카드(`_bindEstimateMobilePreview` → `est-mobile-preview`,
  `_isMobileEstimateView()` = `max-width: 991.98px` 일 때만 표시)와 iOS 다운로드 경로(`_isIosLike()`).
- 데스크톱(≥992px)에서는 `_applyEstimateViewMode()` 가 그 카드를 숨기고 견적서를 **파일로 바로 내려받는다**.
- 그래서 "데스크톱만 전체화면" 가드는 한 번도 실행되지 않는 죽은 코드였다.

모바일까지 위임하지 않은 이유도 남긴다: 아이폰에서 사진 보관함에 넣는 경로는 이 모달의
`사진에 저장` 버튼(버튼 탭이라는 새 사용자 제스처)뿐이고, 뷰어의 다운로드 단추는 `data:` URL 이라
저장되지 않는다. 모바일 모달은 이미 화면을 꽉 채우고 핀치 확대가 되므로 얻을 것도 적다.

**다음에 이 요구가 다시 오면** 고칠 자리는 zoom 모듈이 아니라 "데스크톱에 견적 미리보기 진입로를
만드는 것"이다(지금은 바로 다운로드). 그건 새 기능이므로 설계부터 간다.
