"""고객 공유 UI 3표면 배선 계약 (Phase A T4·T9).

PC/모바일/태블릿 어느 한 표면만 배선하고 나머지를 빠뜨리는 회귀를 소스 문자열로
고정한다(test_alimtalk_ui_contract.py 선례 — 렌더 파이프라인이 아니라 파일 내용을
보므로 DB/브라우저 없이 즉시 실패한다).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUTTON_CLASS = "erp-share-open-btn"
MODAL_PARTIAL = "orders/partials/erp_share_modal.html"
SHARE_JS = "js/orders/erp-share.js"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_pc_tab_has_share_button_next_to_alimtalk() -> None:
    """PC: 알림톡 버튼 옆 고객 공유 버튼."""
    html = _read("templates/orders/partials/erp_order_tab.html")
    assert BUTTON_CLASS in html
    assert 'id="erp-share-open-btn"' in html
    assert html.index("erp-alimtalk-send-btn") < html.index(BUTTON_CLASS)


def test_mobile_tab_has_share_button_in_sticky_footer() -> None:
    """모바일: sticky action bar 에 foms-btn 체계로 노출."""
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    button = footer[: footer.index("</footer>")]
    assert BUTTON_CLASS in button, "공유 버튼이 sticky footer 밖에 있다"
    assert "foms-btn" in button


def test_modal_partial_included_on_both_surfaces() -> None:
    """공유 모달 partial 은 PC/모바일 두 표면 모두에 include 된다."""
    assert MODAL_PARTIAL in _read("templates/orders/partials/erp_order_tab.html")
    assert MODAL_PARTIAL in _read("templates/orders/partials/erp_order_tab_mobile.html")

    modal = _read("templates/orders/partials/erp_share_modal.html")
    assert 'id="erpShareModal"' in modal
    assert 'id="erp-share-create-btn"' in modal
    assert 'id="erp-share-copy-btn"' in modal
    assert 'id="erp-share-kakao-btn"' in modal
    assert 'id="erp-share-sms-btn"' in modal  # T8: 문자 발송(발급 직후 화면 한정)
    assert 'id="erp-share-list"' in modal
    assert "data-kakao-js-key" in modal
    assert "style=" not in modal, "인라인 스타일 금지 — bootstrap/erp-pro.css 사용"
    # T7 해금: 견적서 kind 는 활성 radio 로 노출된다(disabled 회귀 금지).
    assert 'value="estimate"' in modal
    assert 'value="estimate" disabled' not in modal


def test_tablet_measure_form_renders_share_button_and_handler() -> None:
    """태블릿(T9): 채널톡 섹션에 data-tmf-share-open 버튼 + 위임 핸들러 분기(알림톡 선례)."""
    js = _read("static/js/foms/tablet-measure-form.js")
    assert "data-tmf-share-open" in js
    assert BUTTON_CLASS in js
    assert 'closest("[data-tmf-share-open]")' in js
    assert "/api/share/create/" in js
    assert "/api/share/send-sms/" in js
    # 토큰 원문은 발급 응답 지역변수에만 — 저장 금지(해시-온리).
    assert "localStorage" not in js
    assert "sessionStorage" not in js


def test_share_js_wired_in_erp_order_script_chain_with_version() -> None:
    """알림톡 JS 와 같은 체인에서 defer + ?v 로 로드된다(perf G1)."""
    chain = _read("templates/orders/partials/erp_order_js.html")
    line = next(ln for ln in chain.splitlines() if SHARE_JS in ln)
    assert "defer" in line
    assert "?v=" in line
    assert chain.index("js/orders/erp-alimtalk-send.js") < chain.index(SHARE_JS)


def test_share_js_singleton_lazy_sdk_and_endpoints() -> None:
    """전역 리스너 싱글톤(perf G4) + API 3종 + Kakao SDK 는 클릭 시점 lazy 로드."""
    js = _read("static/js/orders/erp-share.js")
    assert "window.__FOMS_SHARE_BOUND" in js
    assert "document.addEventListener('click'" in js
    assert "/api/share/list/" in js
    assert "/api/share/create/" in js
    assert "/api/share/revoke/" in js
    assert "/api/share/send-sms/" in js  # T8 — 발송 중 버튼 잠금(§1 ①)은 disabled 로 구현
    assert "kakao_js_sdk" in js  # lazy 로드 URL — eager <script> 태그 금지
    assert "sendDefault" in js
    # 카톡 공유 문구는 kind 를 따라간다(T7 — 견적 링크에 "도면 확인" 회귀 금지).
    assert "견적서 확인" in js
    # 태블릿 버튼은 자체 핸들러 소유(T9) — 이중 처리 방지 제외 선택자.
    assert ":not([data-tmf-share-open])" in js
    # 토큰·URL 은 발급 응답 메모리에만 — localStorage/sessionStorage 격납 금지.
    assert "localStorage" not in js
    assert "sessionStorage" not in js
