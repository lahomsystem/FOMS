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
PICKER_PARTIAL = "orders/partials/erp_alimtalk_picker_modal.html"
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
    """모바일: sticky action bar 에 foms-btn 체계로 노출(PUSH 와 같은 선택 시트 트리거)."""
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    button = footer[: footer.index("</footer>")]
    assert 'id="erp-alimtalk-picker-btn"' in button, "알림톡 버튼이 sticky footer 밖에 있다"
    assert "foms-btn" in button
    # dropdown 은 좁은 폭에서 액션바를 덮어 터치가 막힌다 — 시트로만 연다.
    assert "erp-alimtalk-menu-mobile" not in html
    assert PICKER_PARTIAL in html


def test_mobile_alimtalk_picker_sheet_reuses_push_sheet_markup() -> None:
    """모바일 알림톡 선택 시트: PUSH 시트와 같은 클래스 + PC 드롭다운과 같은 3항목."""
    sheet = _read("templates/orders/partials/erp_alimtalk_picker_modal.html")
    assert 'id="erpAlimtalkPickerModal"' in sheet
    # PUSH 시트 CSS(erp-channel-push.css)를 그대로 물려받는다.
    assert "erp-channel-push-picker-modal" in sheet
    assert "erp-channel-push-picker-options" in sheet
    # 선택지는 기존 위임 핸들러가 그대로 처리하는 클래스를 단다.
    assert BUTTON_CLASS in sheet
    # 알림톡 발송 2종(도면·계약서) + 내 문자로 보내기 2종.
    assert sheet.count('class="foms-btn foms-btn--secondary erp-share-alimtalk-quick-btn"') == 2
    assert sheet.count("data-share-kind=") == 4
    assert 'data-share-kind="drawing"' in sheet
    assert 'data-share-kind="estimate"' in sheet

    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "erpOpenAlimtalkPicker" in js
    assert "erpAlimtalkReplay" in js


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


def test_send_js_autosaves_dirty_form_before_preview() -> None:
    """T13: 미저장 입력은 preview 전에 기존 통합 저장으로 반영한다(화면값 직접 조립 금지)."""
    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "erpAlimtalkEnsureSaved" in js
    # 저장 SSOT = 기존 ERP 통합 저장(리다이렉트 없이 호출).
    assert "window.erpSaveStructured" in js
    assert "redirect: false" in js
    # 저장 실패 시 발송 중단 + 문구 표면화(조용한 통과 금지).
    assert "저장 실패 — 저장 후 다시 시도해주세요." in js
    # 공유 링크(erp-share.js)가 재사용하는 전역 헬퍼.
    assert "window.fomsErpEnsureSavedForSend" in js


def test_send_js_persists_new_and_draft_orders_like_channel_push() -> None:
    """저장 안 한 주문도 **저장(승격)한 뒤** 발송한다 — 채널 PUSH 와 같은 규칙.

    예전에는 draft 백업 주문이면 저장을 건너뛰고 서버의 ``not_eligible`` 을 그대로
    보여줬다. 사용자에게는 "입력해 놨는데 발송이 안 된다"로만 읽혔다(2026-08-24 보고).
    이제 미저장 변경뿐 아니라 **주문 id 가 없거나 draft 인 경우에도** 저장한다.
    """
    js = _read("static/js/orders/erp-alimtalk-send.js")
    # 저장 조건 = dirty ∨ (id 없음 ∨ draft) — 채널 PUSH(_isDirty || _needsPersist) 미러.
    assert "needsPersist" in js
    assert "erpAlimtalkOrderId()" in js
    assert "erpIsDraftBackedOrder" in js
    assert "if (!dirty && !needsPersist) return true;" in js
    # draft 를 그냥 통과시키던 옛 분기가 되살아나면 같은 사고가 난다.
    assert "window.erpIsDraftBackedOrder()) {\n            return true;" not in js
    # id 는 저장 **뒤에** 읽는다(저장이 주문을 만들거나 승격하므로).
    open_body = js.split("async function erpOpenAlimtalkModal()", 1)[1]
    assert open_body.index("erpAlimtalkEnsureSaved()") < open_body.index("erpAlimtalkOrderId()")


def test_share_js_saves_before_reading_order_id() -> None:
    """공유 발급·내 문자 보내기도 저장 뒤에 주문 id 를 읽는다(같은 사고 자리)."""
    js = _read("static/js/orders/erp-share.js")
    for entry in ("async function _create()", "async function _selfSms(kind)"):
        body = js.split(entry, 1)[1][:1200]
        assert body.index("_ensureSaved(") < body.index("_orderId()"), entry


def test_share_js_reuses_alimtalk_autosave_guard() -> None:
    """T13(공유): 링크 발급·원클릭 알림톡도 저장본을 보여주므로 같은 dirty 가드를 탄다."""
    js = _read("static/js/orders/erp-share.js")
    assert "fomsErpEnsureSavedForSend" in js
    # 헬퍼 정의 1 + 발급/원클릭 호출 2.
    assert js.count("_ensureSaved(") >= 3
