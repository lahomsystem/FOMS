"""erporder 첨부 미리보기 — 이미지 클릭 시 전체화면 뷰어 계약 테스트 (2026-09-14).

정적 파일/템플릿 계약(문자열 부분일치, whitespace-exact 블록 미잠금):
  - attachment-preview-zoom.js : 전체화면 위임 진입점 + 모달 공존 생명주기
    (Bootstrap 포커스 트랩 무력화 · ESC 1회 · 스크롤 잠금 복구) + 모달 안 scale 폴백 보존.
  - erp-order-shared.js / erp-attachment-preview-open.js : 호출부가 fullscreen 페이로드를 넘긴다.
  - 템플릿 5개 : 편집한 JS 3개의 자산 핀(?v=)이 함께 올랐고 옛 핀은 사라졌다.
  - layout_scripts.html : 뷰어는 무수정(공개 API 4종 유지).
  - estimate-preview.js / mobile-detail-attachments.js : 음성 대조군 — 모달 안 scale 폴백 유지.

app 을 임포트하지 않는 순수 정적 파일 읽기다(렌더 본문 단언은
tests/domains/test_erp_order_shared_form_scripts.py 의 몫 — 목적이 다르다).
따옴표 스타일·들여쓰기는 잠그지 않는다(부분일치 또는 공백 유연 정규식).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ZOOM_JS = "static/js/foms/attachment-preview-zoom.js"
OPEN_JS = "static/js/foms/erp-attachment-preview-open.js"
SHARED_JS = "static/js/orders/erp-order-shared.js"
VIEWER_TPL = "templates/partials/shared/layout_scripts.html"
MODAL_TPL = "templates/partials/shared/foms_attachment_preview_modal.html"
ESTIMATE_JS = "static/js/orders/estimate-preview.js"
MOBILE_DETAIL_JS = "static/js/foms/mobile-detail-attachments.js"

PIN = "?v=20260914a"

#: erp-order-shared.js 만 ADMIN-OVERRIDE-01(퀘스트 승인 거부 → 관리자 강제 진행 재시도)로
#: 다시 바뀌었다. 나머지 두 JS 는 그때 안 바뀌었으니 핀을 따로 둔다.
SHARED_PIN = "?v=20260921a"

ZOOM_SRC = "attachment-preview-zoom.js') }}"
OPEN_SRC = "erp-attachment-preview-open.js') }}"
SHARED_SRC = "erp-order-shared.js') }}"

# 옛 핀 — 범프 뒤에는 아래 템플릿 어디에도 남아 있으면 안 된다.
OLD_PINS = (
    ZOOM_SRC + "?v=20260629a",
    OPEN_SRC + "?v=20260724a",
    SHARED_SRC + "?v=20260904c",
)

# 핀을 올려야 하는 템플릿 전수(무관 파일로 범프가 번졌는지도 이 목록으로만 갈린다).
PIN_TEMPLATES = (
    "templates/orders/object.html",
    "templates/orders/partials/erp_order_js.html",
    "templates/orders/wizard/wizard_shell.html",
    "templates/orders/mobile_order_detail.html",
    "templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html",
)


def _read(rel: str) -> str:
    """Return the UTF-8 text of a repo-relative file."""
    return (ROOT / rel).read_text(encoding="utf-8")


def _has_any(text: str, *variants: str) -> bool:
    """따옴표 스타일만 다른 변형 중 하나라도 있으면 True(공백·따옴표 고정 방지)."""
    return any(v in text for v in variants)


def test_zoom_module_exposes_fullscreen_entrypoint() -> None:
    """전체화면 위임 진입점은 zoom 모듈이 노출한다: 호출부(erp-order-shared /
    erp-attachment-preview-open)는 이 이름 하나만 알면 되고, 실제 뷰어는 공용
    GlobalImageViewer(루트 id = global-image-viewer)로 간다."""
    js = _read(ZOOM_JS)
    assert "window.fomsOpenAttachmentPreviewFullscreen" in js
    assert "GlobalImageViewer" in js
    # 뷰어 루트 id — 세션 관찰(MutationObserver)과 focusin 가드가 이 요소를 기준으로 판정한다.
    assert "global-image-viewer" in js


def test_zoom_module_reads_fullscreen_option() -> None:
    """fullscreen 옵션은 바인드 시점이 아니라 **클릭 시점**에 평가한다. 그래서 옵션은
    img._fomsPreviewFullscreenOption 에 매번 다시 실려야 하고(재바인드 대비),
    핸들러는 resolveFullscreenPayload → tryOpenFullscreen 경로로만 뷰어를 연다."""
    js = _read(ZOOM_JS)
    assert "_fomsPreviewFullscreenOption" in js
    assert "resolveFullscreenPayload" in js
    assert "tryOpenFullscreen" in js


def test_zoom_module_neutralizes_bootstrap_focus_trap() -> None:
    """함정 1 — Bootstrap 모달 포커스 트랩이 뷰어 버튼으로 간 포커스를 되끌어온다.
    대책은 document **캡처** focusin 리스너에서 stopPropagation() 하는 것이다
    (Bootstrap FocusTrap 은 document 버블 리스너라 캡처에서 끊으면 실행되지 않는다).
    대안(data-bs-focus="false")은 공유 파셜이라 전 표면 회귀 — 쓰지 않았음을 함께 고정한다."""
    js = _read(ZOOM_JS)
    assert "focusin" in js
    assert "stopPropagation" in js
    # 캡처 true 로 등록해야 버블 단계의 Bootstrap 핸들러가 아예 안 돈다.
    assert "onFocusin, true" in js
    # 공유 모달 파셜에는 data-bs-focus 를 넣지 않는다(모달 단독 ESC 닫기가 깨진다).
    assert "data-bs-focus" not in _read(MODAL_TPL)


def test_zoom_module_handles_escape_once() -> None:
    """함정 2 — ESC 가 뷰어와 Bootstrap 모달을 동시에 닫으면 안 된다. 캡처 keydown 에서
    Escape 를 stopPropagation() 한 뒤 우리가 직접 GlobalImageViewer.close() 를 부른다.
    stopImmediatePropagation 은 쓰지 않는다(무관한 캡처 리스너까지 죽인다)."""
    js = _read(ZOOM_JS)
    assert "Escape" in js
    assert "stopPropagation" in js
    assert "GlobalImageViewer.close()" in js
    assert "stopImmediatePropagation" not in js


def test_zoom_module_watches_viewer_close_and_restores_scroll_lock() -> None:
    """함정 3 — 뷰어에는 close 콜백이 없고 닫기 버튼·배드드롭이 내부 close 에 직접 바인드라
    래핑으로는 모든 닫힘 경로를 못 잡는다. 그래서 루트 속성(style/aria-hidden)을
    MutationObserver 로 관찰하고, 모달이 아직 .show 일 때만 body overflow 잠금을 복구한다."""
    js = _read(ZOOM_JS)
    assert "MutationObserver" in js
    assert "aria-hidden" in js
    assert "document.body.style.overflow" in js
    # 모달이 살아 있을 때만 복구한다(이미 닫혔으면 배경이 영구 잠긴다).
    assert _has_any(js, 'classList.contains("show")', "classList.contains('show')")


def test_zoom_module_keeps_modal_scale_fallback() -> None:
    """목표 4 — GlobalImageViewer 가 없는 표면(뷰어 마크업 미포함)·files 빈 경우·resolver 예외는
    지금의 모달 안 scale 확대로 폴백한다. 폴백의 본체인 toggleTapZoom 과 TAP_SCALE 이 살아 있어야
    한다(전체화면으로 갈아치우면 폴백 표면이 통째로 죽는다)."""
    js = _read(ZOOM_JS)
    assert "toggleTapZoom" in js
    assert "TAP_SCALE" in js


def test_erp_order_shared_passes_fullscreen_payload() -> None:
    """erporder 상세는 같은 주문의 이미지 첨부를 모아 fullscreen 페이로드로 넘긴다(뷰어 좌우 이동).
    URL 은 서명된 R2 URL 이 아니라 만료되지 않는 /api/files/view/ 안정 경로여야 한다
    (서명 URL 은 뷰어가 열려 있는 동안 만료될 수 있다)."""
    js = _read(SHARED_JS)
    assert "erpBuildAttachmentFullscreenPayload" in js
    assert "erpStableAttachmentUrls" in js
    assert "fullscreen:" in js
    assert "/api/files/view/" in js


def test_attachment_preview_open_passes_single_file_payload() -> None:
    """공유 진입로는 첨부가 하나뿐이어도 files: [현재 파일] · index: 0 으로 넘겨
    전체화면이 되게 한다(단일 첨부만 모달에 갇히는 예외를 만들지 않는다)."""
    js = _read(OPEN_JS)
    assert "fullscreen:" in js
    assert "index: 0" in js


def test_asset_pins_bumped_together() -> None:
    """편집한 JS 3개를 참조하는 템플릿 전수의 핀(?v=)이 같은 값으로 올라야 한다 — 하나라도
    빠지면 그 표면만 옛 파일을 캐시로 받아 전체화면이 안 열린다. 옛 핀이 사라졌는지도 같이 본다
    (범프가 무관 파일로 번졌는지는 이 전수 목록으로만 갈린다)."""
    object_html = _read("templates/orders/object.html")
    assert ZOOM_SRC + PIN in object_html
    assert OPEN_SRC + PIN in object_html

    erp_order_js = _read("templates/orders/partials/erp_order_js.html")
    assert ZOOM_SRC + PIN in erp_order_js
    assert SHARED_SRC + SHARED_PIN in erp_order_js

    wizard_shell = _read("templates/orders/wizard/wizard_shell.html")
    assert ZOOM_SRC + PIN in wizard_shell
    assert OPEN_SRC + PIN in wizard_shell

    mobile_detail = _read("templates/orders/mobile_order_detail.html")
    assert ZOOM_SRC + PIN in mobile_detail

    queue_bundle = _read(
        "templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html"
    )
    assert ZOOM_SRC + PIN in queue_bundle
    assert OPEN_SRC + PIN in queue_bundle

    for rel in PIN_TEMPLATES:
        body = _read(rel)
        for old in OLD_PINS:
            assert old not in body, rel


def test_viewer_partial_untouched() -> None:
    """뷰어 자체는 수정하지 않는다(비목표). 마크업 id 와 공개 API 4종(init/open/close/getIndex)이
    그대로여야 zoom 모듈의 상태 관찰·직접 close 호출이 성립한다."""
    tpl = _read(VIEWER_TPL)
    assert re.search(r"window\.GlobalImageViewer\s*=\s*\(function\s*\(\s*\)\s*\{", tpl)
    assert 'id="global-image-viewer"' in tpl
    assert re.search(
        r"return\s*\{\s*init\s*,\s*open\s*,\s*close\s*,\s*getIndex\s*,?\s*\}", tpl
    )
    # 닫힘 신호의 가정을 못 박는다 — zoom 모듈의 viewerIsOpen() 은 루트의 인라인
    # style.display 와 aria-hidden 을 읽어 열림/닫힘을 가른다. close() 가 클래스(d-flex)만
    # 건드리도록 바뀌면 그 판정이 깨지므로 여기서 먼저 red 로 잡는다.
    assert re.search(r"root\.style\.display\s*=\s*['\"]none['\"]", tpl)
    assert re.search(
        r"root\.setAttribute\(\s*['\"]aria-hidden['\"]\s*,\s*['\"]true['\"]\s*\)", tpl
    )


def test_other_zoom_callers_keep_modal_scale() -> None:
    """음성 대조군 — 견적 미리보기와 모바일 상세 첨부는 이번 범위 밖이다. 두 호출부는
    fullscreen 옵션을 넘기지 않아 모달 안 scale 확대를 그대로 유지해야 한다.
    바인드 호출 자체는 살아 있어야 한다(대조군은 모집단 안에서 고른다)."""
    estimate = _read(ESTIMATE_JS)
    mobile_detail = _read(MOBILE_DETAIL_JS)
    assert "fullscreen" not in estimate
    assert "fullscreen" not in mobile_detail
    assert "fomsBindAttachmentPreviewImageZoom" in estimate
    assert "fomsBindAttachmentPreviewImageZoom" in mobile_detail
