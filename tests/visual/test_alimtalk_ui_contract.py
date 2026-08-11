"""알림톡 수동 발송 UI 3표면 배선 계약 (v1 T5).

PC/모바일/태블릿 어느 한 표면만 배선하고 나머지를 빠뜨리는 것이 이 기능의 대표 회귀라
(스펙 §6.5 H5 — "자동 커버" 아님), 세 표면의 버튼·모달·JS 로드 체인을 소스 문자열로
고정한다. 렌더 파이프라인이 아니라 파일 내용을 보므로 DB/브라우저 없이 즉시 실패한다.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUTTON_CLASS = "erp-alimtalk-send-btn"
MODAL_PARTIAL = "orders/partials/erp_alimtalk_modal.html"
SEND_JS = "js/orders/erp-alimtalk-send.js"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_pc_tab_has_alimtalk_button_and_status_line() -> None:
    """PC: 채널톡 PUSH 버튼 옆 알림톡 버튼 + 상태 한 줄."""
    html = _read("templates/orders/partials/erp_order_tab.html")
    assert BUTTON_CLASS in html
    assert 'id="erp-alimtalk-send-btn"' in html
    assert "erp-alimtalk-status" in html
    # 채널톡 버튼 묶음 안(= 변환/PUSH 카드 헤더)에 있어야 한다.
    assert html.index("erp-channeltalk-push-as-btn") < html.index(BUTTON_CLASS)


def test_mobile_tab_has_alimtalk_button_in_sticky_footer() -> None:
    """모바일: sticky action bar 에 foms-btn 체계로 노출."""
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    assert BUTTON_CLASS in html
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    button = footer[: footer.index("</footer>")]
    assert BUTTON_CLASS in button, "알림톡 버튼이 sticky footer 밖에 있다"
    assert "foms-btn" in button


def test_tablet_measure_form_renders_alimtalk_button_and_handler() -> None:
    """태블릿: 채널톡 섹션에 data-tmf-* 버튼 + 위임 핸들러 분기."""
    js = _read("static/js/foms/tablet-measure-form.js")
    assert "data-tmf-alimtalk-send" in js
    assert BUTTON_CLASS in js
    assert 'closest("[data-tmf-alimtalk-send]")' in js
    assert "/api/kakao/alimtalk/preview/" in js
    assert "/api/kakao/alimtalk/send-manual/" in js


def test_modal_partial_included_on_both_html_surfaces() -> None:
    """미리보기 모달 partial 은 PC/모바일 두 표면 모두에 include 된다(코호트 게이트가 한쪽 제거)."""
    assert MODAL_PARTIAL in _read("templates/orders/partials/erp_order_tab.html")
    assert MODAL_PARTIAL in _read("templates/orders/partials/erp_order_tab_mobile.html")

    modal = _read("templates/orders/partials/erp_alimtalk_modal.html")
    assert 'id="erpAlimtalkModal"' in modal
    assert 'id="erp-alimtalk-preview"' in modal
    assert 'id="erp-alimtalk-confirm-btn"' in modal
    assert 'id="erp-alimtalk-last"' in modal
    assert "style=" not in modal, "인라인 스타일 금지 — erp-pro/erp-channel-push.css 사용"


def test_send_js_wired_in_erp_order_script_chain_with_version() -> None:
    """erp-channel-push-confirm.js 와 같은 체인에서 defer + ?v 로 로드된다(perf G1)."""
    chain = _read("templates/orders/partials/erp_order_js.html")
    line = next(ln for ln in chain.splitlines() if SEND_JS in ln)
    assert "defer" in line
    assert "?v=" in line
    assert chain.index("js/orders/erp-channel-push-confirm.js") < chain.index(SEND_JS)


def test_send_js_singleton_guard_and_click_time_fetch() -> None:
    """전역 리스너 싱글톤(perf G4) + preview 는 클릭 시점 fetch(전역 프리페치 없음)."""
    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "window.__FOMS_ALIMTALK_BOUND" in js
    assert "document.addEventListener('click'" in js
    assert "/api/kakao/alimtalk/preview/" in js
    assert "/api/kakao/alimtalk/send-manual/" in js
    # dirty 가드: 미저장 편집이 있으면 발송 차단.
    assert "fomsErpAutosave" in js and "isDirty" in js
    # 태블릿 버튼은 자체 핸들러 소유 — 이중 처리 방지 제외 선택자.
    assert ":not([data-tmf-alimtalk-send])" in js
