"""Template contract tests for the ERP Order shared-form script island."""

from pathlib import Path

from werkzeug.security import generate_password_hash

import pytest

from db import db_session
from models import Order, User


@pytest.fixture
def erp_editor_client(client):
    """Login a user that can open ERP Order add/edit pages."""
    user = User(
        username="erp_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Admin",
    )
    db_session.add(user)
    db_session.commit()

    client.post(
        "/login",
        data={"username": "erp_admin", "password": "admin"},
        follow_redirects=True,
    )
    return client


def _create_erp_order() -> Order:
    order = Order(
        received_date="2026-04-14",
        customer_name="ERP Order Contract",
        phone="010-1111-2222",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _assert_shared_form_script_contract(body: str) -> None:
    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    channel_push_confirm_idx = body.index("js/orders/erp-channel-push-confirm.js")
    as_push_confirm_idx = body.index("js/cs/as-push-confirm.js")
    erp_order_shared_idx = body.index("js/orders/erp-order-shared.js")
    stage_override_idx = body.index("js/orders/erp-stage-override.js")
    estimate_preview_idx = body.index("js/orders/estimate-preview.js")
    estimate_columns_idx = body.index("js/orders/estimate-table-columns.js")
    column_resizer_idx = body.index("js/runtime/column-resizer.js")

    assert (
        payment_urls_idx
        < channel_push_confirm_idx
        < as_push_confirm_idx
        < erp_order_shared_idx
        < stage_override_idx
        < column_resizer_idx
        < estimate_preview_idx
        < estimate_columns_idx
    )
    assert "html2canvas.min.js" not in body
    assert "js/orders/erp-channel-push-confirm.js?v=20260821a" in body
    assert "js/cs/as-push-confirm.js?v=20260820a" in body
    assert "js/orders/erp-order-shared.js?v=20260904a" in body
    assert "js/cs/as-attachment-order.js?v=20260819a" in body
    assert "js/orders/erp-alimtalk-send.js?v=20260824b" in body
    # T15 발송 흔적: 칩 자리·이력 패널이 실제 렌더에 붙어 있어야 한다(템플릿 계약만으로는
    # 코호트 게이트가 한쪽 표면을 통째로 지워도 초록이다).
    assert "js/orders/erp-alimtalk-trace.js?v=20260901b" in body
    assert "data-erp-alimtalk-trace" in body
    assert 'id="erpAlimtalkTraceModal"' in body
    assert "js/orders/erp-share.js?v=20260901b" in body
    assert "css/orders/erp-share.css?v=20260821a" in body
    assert "js/orders/erp-stage-override.js?v=20260825a" in body
    assert "erp_stage_override_modal.html" not in body  # include renders modal markup, not path
    assert 'id="erpStageOverrideModal"' in body
    assert 'id="asPushConfirmModal"' in body
    assert "(8자 이상)" not in body
    assert "css/orders/erp-channel-push.css?v=20260824b" in body
    assert "css/orders/erp-items-master-detail.css?v=20260701f" in body
    assert "js/orders/erp-items-master-detail.js?v=20260630c" in body
    assert "erp-items-master-detail-shell" in body
    assert 'id="erp-md-rail-list"' in body
    assert "js/orders/estimate-preview.js?v=20260720b" in body

    estimate_preview_js = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "orders"
        / "estimate-preview.js"
    ).read_text(encoding="utf-8")
    assert "html2canvas.min.js" in estimate_preview_js
    assert "document.createElement('script')" in estimate_preview_js

    # W5-B8: giant inline shared-form code was moved out of the partial.
    assert "function erpRecalcItemsTotal()" not in body
    assert "async function erpSaveStructured(opts = {})" not in body
    assert "window.erpTogglePayment = async function" not in body

    # Shared host DOM contract remains provided by the ERP Order tab partial.
    assert 'id="erp-items"' in body
    assert 'id="erp-save-btn"' in body
    assert 'id="erp-attachments-input"' in body



def test_erp_amount_caret_is_preserved_and_ios_reapplied() -> None:
    """금액칸 재포맷 후 caret 은 끝 오프셋으로 보존되고, iOS 되돌림은 다음 프레임에 교정된다."""
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "function restoreAmountCaret(" in js
    assert "restoreAmountCaret(this, prevValue, prevCaret, formatted)" in js
    assert "window.requestAnimationFrame(function () {" in js
    assert "document.activeElement !== el || el.selectionStart === pos" in js

def test_add_order_page_renders_thin_erp_order_partial_contract(erp_editor_client) -> None:
    response = erp_editor_client.get("/add")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    erp_order_shared_tag_idx = body.index("js/orders/erp-order-shared.js")
    config_idx = body.index('id="erp-order-config"')
    order_enabled_idx = body.index("var ERP_ORDER_ENABLED = _aoCfg ? safeJsonParse(_aoCfg.getAttribute('data-erp-order-enabled'), false) : false;")
    draft_mode_idx = body.index("window.__ERP_ORDER_DRAFT_MODE = true;")

    assert payment_urls_idx < erp_order_shared_tag_idx < config_idx < order_enabled_idx < draft_mode_idx
    _assert_shared_form_script_contract(body)
    assert 'data-erp-order-draft-mode="true"' in body


def test_inject_status_list_erp_order_enabled_prefers_explicit_erp_order_env(app, monkeypatch) -> None:
    """ERP_ORDER_ENABLED=true enables the canonical ERP Order surface."""
    monkeypatch.setenv("ERP_ORDER_ENABLED", "true")
    with app.test_request_context("/"):
        from foms.services.context_processors import inject_status_list

        ctx = inject_status_list()
        assert ctx["erp_order_enabled"] is True


def test_inject_status_list_erp_order_enabled_defaults_true_when_unset(app, monkeypatch) -> None:
    """Without an explicit env override, ERP Order remains enabled by canonical default."""
    monkeypatch.delenv("ERP_ORDER_ENABLED", raising=False)
    with app.test_request_context("/"):
        from foms.services.context_processors import inject_status_list

        ctx = inject_status_list()
        assert ctx["erp_order_enabled"] is True


def test_inject_status_list_erp_order_false_stays_false(app, monkeypatch) -> None:
    """Explicit ERP_ORDER_ENABLED=false must disable the canonical ERP Order surface."""
    monkeypatch.setenv("ERP_ORDER_ENABLED", "false")
    with app.test_request_context("/"):
        from foms.services.context_processors import inject_status_list

        ctx = inject_status_list()
        assert ctx["erp_order_enabled"] is False


def test_add_order_page_uses_canonical_open_erp_order_deep_link_only(erp_editor_client) -> None:
    """The add page should only honor the canonical ?open=erp-order deep link."""
    response = erp_editor_client.get("/add?open=erp-order")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "openTarget === 'erp-order'" in body
    assert "erp-beta" not in body


def test_edit_order_page_uses_canonical_open_erp_order_deep_link_only(erp_editor_client) -> None:
    """Edit surface honors ?open=erp-order (and erp-estimate) deep links; legacy erp-beta gone."""
    order = _create_erp_order()
    response = erp_editor_client.get(f"/edit/{order.id}?open=erp-order")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-order" in body
    assert "bootstrap.Tab.getOrCreateInstance(btn).show()" in body
    assert "erp-beta" not in body


def test_edit_order_supports_open_erp_estimate_and_embedded_chrome(erp_editor_client) -> None:
    """태블릿 견적 iframe: ?open=erp-estimate 탭 딥링크 + embedded=1 크롬 은닉 클래스."""
    order = _create_erp_order()
    response = erp_editor_client.get(
        f"/edit/{order.id}?open=erp-estimate&embedded=1"
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-estimate" in body
    assert 'id="erp-estimate-tab"' in body
    assert "foms-edit-embedded" in body
    assert "openTarget === 'erp-estimate'" in body or "openTarget == 'erp-estimate'" in body


def test_estimate_preview_forces_pc_view_when_embedded() -> None:
    """태블릿 iframe(embedded=1)에서는 패널 폭과 무관하게 PC 견적 뷰 강제."""
    text = Path("static/js/orders/estimate-preview.js").read_text(encoding="utf-8")
    assert "_isEmbeddedEstimate" in text
    assert "foms-edit-embedded" in text
    assert "embedded') === '1'" in text or 'embedded") === "1"' in text


def test_erp_order_edit_renders_pc_wdc_split_contract(erp_editor_client) -> None:
    """PC ERP Order edit page exposes lazy WDCalculator split pane without loading WDC bundle inline."""
    order = _create_erp_order()
    response = erp_editor_client.get(f"/edit/{order.id}?open=erp-order")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert 'id="erpWdcSplitToggle"' in body
    assert 'id="erpWdcSplitPane"' in body
    assert 'id="erpWdcSplitFrame"' in body
    assert "embedded=1" in body
    assert f"order_id={order.id}" in body
    assert "js/orders/erp-wdc-split.js?v=20260624c" in body
    assert "css/orders/erp-wdc-split.css" in body
    assert "js/wdcalculator/pricing-core.js" not in body


def test_wdcalculator_embedded_mode_renders_pc_split_contract(erp_editor_client) -> None:
    """Embedded calculator fixes the PC shell and folds saved estimates into an overlay."""
    response = erp_editor_client.get("/wdcalculator?embedded=1&order_id=4001&customer_name=Split%20Customer")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "ERP 대시보드" not in body
    assert "wdcalculator-container--embedded" in body
    assert 'id="wdEmbeddedSavedToggle"' in body
    assert 'id="wdEmbeddedSavedBackdrop"' in body
    assert 'id="wdEmbeddedSavedClose"' in body
    assert "css/orders/erp-wdc-split.css" in body
    assert "js/wdcalculator/embedded-shell.js" in body
    assert "js/wdcalculator/mobile-enhance.js" not in body
    assert "js/wdcalculator/estimate-lifecycle.js?v=20260805b" in body
    assert "주문으로 돌아가기" not in body


def test_erp_wdc_split_bridge_js_contract() -> None:
    """Split bridge stays lazy, idempotent, and customer-name synced via same-origin postMessage."""
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-wdc-split.js").read_text(encoding="utf-8")

    assert "window.__erpWdcSplitBound" in js
    assert 'document.getElementById("erpWdcSplitToggle")' in js
    assert 'frame.setAttribute("src", buildFrameSrc(frame))' in js
    assert 'type: "foms:wdc:set-customer-name"' in js
    assert 'window.location.origin' in js
    assert 'document.getElementById("erp-customer-name")' in js
    assert 'customerInput.addEventListener("input"' in js
    assert "setOpen(!shell.classList.contains(\"is-wdc-split-open\"))" in js
    assert "setOpen(true)" not in js


def test_wdcalculator_embedded_pc_shell_assets_contract() -> None:
    """Embedded WDC assets prevent mobile takeover and expose saved-estimate overlay controls."""
    root = Path(__file__).resolve().parents[2]
    css = (root / "static/css/orders/erp-wdc-split.css").read_text(encoding="utf-8")
    js = (root / "static/js/wdcalculator/embedded-shell.js").read_text(encoding="utf-8")

    assert ".wdcalculator-embedded-layout > .container-fluid" in css
    assert ".wdcalculator-container--embedded .wdcalculator-shell" in css
    assert ".wdcalculator-container--embedded .saved-estimates-sidebar" in css
    assert ".wdcalculator-container--embedded.is-saved-estimates-open .saved-estimates-sidebar" in css
    assert "window.__wdCalculatorEmbeddedShellBound" in js
    assert 'document.getElementById("wdEmbeddedSavedToggle")' in js
    assert 'root.classList.toggle("is-saved-estimates-open", open)' in js
    assert "window.loadSidebarEstimates" in js


def test_get_add_open_erp_beta_redirects_to_canonical_erp_order(erp_editor_client) -> None:
    """Legacy ?open=erp-beta must 302 to the same path with open=erp-order (other query preserved)."""
    r = erp_editor_client.get("/add?open=erp-beta&x=1", follow_redirects=False)
    assert r.status_code == 302
    loc = (r.headers.get("Location") or "").replace("\\", "/")
    assert "open=erp-order" in loc
    assert "erp-beta" not in loc.lower()
    assert "x=1" in loc


def test_get_edit_open_erp_beta_redirects_to_canonical_erp_order(erp_editor_client) -> None:
    """Legacy ?open=erp-beta on edit must 302 to open=erp-order."""
    order = _create_erp_order()
    r = erp_editor_client.get(f"/edit/{order.id}?open=erp-beta", follow_redirects=False)
    assert r.status_code == 302
    loc = (r.headers.get("Location") or "").replace("\\", "/")
    assert f"/edit/{order.id}" in loc
    assert "open=erp-order" in loc
    assert "erp-beta" not in loc.lower()


def test_estimate_table_columns_contract() -> None:
    """Estimate contract table uses colgroup schema + localStorage persistence."""
    root = Path(__file__).resolve().parents[2]
    pane = (root / "templates/orders/partials/estimate_pane.html").read_text(encoding="utf-8")
    js = (root / "static/js/orders/estimate-table-columns.js").read_text(encoding="utf-8")

    assert 'id="erp-estimate-items-table"' in pane
    assert 'data-col-key="qty"' in pane
    assert 'data-col-key="amount"' in pane
    assert 'table-layout: fixed' in pane
    assert 'btn-est-reset-column-widths' in pane
    assert 'erp-est-col-resizer-grip' in pane

    assert "TABLE_ID = 'erp-estimate-items-table'" in js
    assert "STORAGE_KEY = 'foms.estimatePane.columnWidths.v1'" in js
    assert "resizeMode: 'fit'" in js
    assert "ColumnResizer" in js
    assert "localStorage.setItem" in js
    assert "initEstimateTableColumns" in js
    assert "refreshEstimateTableColumns" in js
    assert "scheduleEstimateColumnRefresh" in js
    assert "setEstimateTableExportMode" in js
    assert 'erp-est-tbl-wrap' in pane
    assert 'id="est-viewport"' in pane
    assert 'id="est-free-input-rows"' in pane
    assert 'erp-est-viewport' in pane
    assert 'erp-est-export-clone' in pane
    assert 'id="est-mobile-preview"' in pane
    assert 'id="est-mobile-preview-fallback"' in pane
    assert 'id="erpEstimatePreviewModal"' in pane
    assert 'id="erp-estimate-preview-body"' in pane
    assert 'data-factory2-src' in pane
    assert 'lahom-logo-en.png' in pane
    assert 'lahom-company-stamp.png' in pane
    assert 'erp-est-stamp--factory2' in pane
    assert 'erp-est-manual-row' in pane
    assert 'erp-est-add-row-btn' in pane
    assert '.erp-est-exporting .erp-est-edit-control' in pane
    # 견적서 PUSH 버튼은 이미지 저장 버튼 왼쪽에 위치한다.
    assert 'id="btn-est-channel-push"' in pane
    assert pane.index('id="btn-est-channel-push"') < pane.index('id="btn-est-export"')
    assert 'fa-paper-plane' in pane
    contract_css = pane.split('.erp-est-contract {', 1)[1].split('.erp-est-contract-title', 1)[0]
    assert 'min-height' not in contract_css


def test_estimate_preview_js_is_canonical_only() -> None:
    """P2 removes ERP_BETA_* fallbacks from the estimate preview runtime."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/estimate-preview.js").read_text(encoding="utf-8")
    start = text.index("function _isErpEnabled()")
    end = text.index("function _fmtMoney", start)
    block = text[start:end]
    assert "ERP_ORDER_ENABLED" in block
    assert "ERP_BETA_ENABLED" not in block
    assert "_EST_EXPORT_WIDTH = 700" in text
    assert "_buildExportClone" in text
    assert "_MOBILE_CANVAS_MAX_SIDE = 4096" in text
    assert "_getEstimateCaptureMetrics" in text
    assert "_setMobileCaptureFallback" in text
    assert "_canvasToImageUrl" in text
    assert "_waitForPreviewImageReady" in text
    assert "Promise.race" in text
    assert "preferBlobUrl: true" in text
    assert "canvas.toBlob" in text
    assert "canvas toBlob timed out" in text
    # 견적서 채널톡 PUSH: 캡처 Blob을 멀티파트로 업로드 전송.
    assert "_runEstimateChannelPush" in text
    assert "_bindChannelPushBtn" in text
    assert "/api/channel/push-estimate" in text
    assert "erpHasPriorChannelPush('estimate')" in text
    # 미저장 draft 주문에서는 영발/발주 PUSH와 동일하게 전송을 차단한다(라이브 DOM ↔ 저장 데이터 괴리 방지).
    push_start = text.index("function _runEstimateChannelPush")
    push_block = text[push_start:push_start + 1600]
    assert "erpCanUsePersistedOrderAction('견적서 전송은')" in push_block
    assert "window.erpIsDraftBackedOrder" in push_block
    assert "dataUrl === 'data:,'" in text
    assert "_HTML2CANVAS_RENDER_TIMEOUT_MS" in text
    assert "html2canvas render timed out" in text
    assert "_withEagerLazyMedia" in text
    assert 'document.querySelectorAll(\'img[loading="lazy"]\')' in text
    assert "html2canvas(exportEl" in text
    # iOS Safari는 a[download]를 무시 → 캡처 이미지를 모달로 띄워 길게 눌러 저장 안내.
    assert "_isIosLike" in text
    assert "navigator.maxTouchPoints" in text
    assert "_showSection('est-viewport')" in text
    export_start = text.index("function _bindExportBtn()")
    export_block = text[export_start:]
    assert "html2canvas render timed out" in text
    assert "_setMobileCaptureFallback(" in export_block
    assert "btn.innerHTML = originalHTML" in export_block
    assert "btn.disabled = false" in export_block
    assert "사진에 저장" in text
    assert "_bindEstimateMobilePreview" in text
    assert "_openEstimatePreviewModal" in text
    assert "fomsBindAttachmentPreviewImageZoom" in text
    assert "_bindManualRows" in text
    assert "window.__erpLastStructuredData.estimate_preview" in text
    assert "preview.manual_rows" in text
    assert "data-est-add-after-index" in text
    assert "data-est-delete-manual-id" in text
    assert "scheduleEstimateColumnRefresh" in text
    assert "function _renderFreeInputRows" in text
    assert "d.free_input_lines" in text
    assert "est-free-input-rows" in text
    assert "isFreeInputField" in text
    assert "function _applyEstimateLogo" in text
    assert "function _applyEstimateStamp" in text
    assert "dataset.factory2Src" in text
    assert "erp-est-stamp--factory2" in text
    assert "window.erpApplyEstimateFactory2Variant" in text


def test_as_modal_exposes_regional_shipping_date_field_contract() -> None:
    """AS 모달(데스크톱+모바일)은 지방주문 상차일 필드를 기본 숨김으로 제공한다."""
    root = Path(__file__).resolve().parents[2]
    pc_tab = (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    mobile_tab = (
        root / "templates/orders/partials/erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")

    for tab in (pc_tab, mobile_tab):
        assert 'id="as-receive-shipping-wrap"' in tab
        # 기본 숨김(지방주문일 때만 JS가 d-none 해제).
        wrap_idx = tab.index('id="as-receive-shipping-wrap"')
        wrap_open = tab.rfind("<div", 0, wrap_idx)
        assert "d-none" in tab[wrap_open:wrap_idx]
        assert 'id="as-receive-shipping-date"' in tab
        assert 'type="date"' in tab[tab.index('id="as-receive-shipping-date"') - 40 : tab.index('id="as-receive-shipping-date"') + 10]
        assert "상차 예정 알림" in tab


def test_as_modal_shipping_date_js_wiring_contract() -> None:
    """erp-order-shared.js는 상차일을 로드·오픈·제출 3지점에서 지방주문 조건으로 배선한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    # (1) 로드: GET 응답의 flat 컬럼을 전역에 보관.
    assert "window.__erpShippingScheduledDate = data.shipping_scheduled_date || '';" in text

    # (2) 오픈: 지방주문일 때만 필드 노출 + prefill(오픈마다 재평가).
    assert "const shipWrapEl = document.getElementById('as-receive-shipping-wrap');" in text
    assert "const shipDateEl = document.getElementById('as-receive-shipping-date');" in text
    assert "document.getElementById('erp-regional-order')?.checked === true" in text
    assert "shipWrapEl.classList.toggle('d-none', !isRegionalNow);" in text
    assert "shipDateEl.value = isRegionalNow ? (window.__erpShippingScheduledDate || '') : '';" in text

    # (3) 제출: 지방주문 + 값이 있을 때만 payload 포함 + 성공 후 전역 갱신.
    assert "const regPayload = { as_content: content };" in text
    assert "regPayload.shipping_scheduled_date = shipDateVal;" in text
    assert "body: JSON.stringify(regPayload)" in text
    assert "window.__erpShippingScheduledDate = shipDateVal;" in text


def test_active_as_reregister_button_opens_prefilled_modal_without_stage_mutation() -> None:
    """진행 중 AS 수정은 본공정 단계 재선택 없이 같은 접수 모달을 연다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    helper_start = text.index("function erpOpenAsReceiveModal(")
    helper_end = text.index("async function erpSaveStructuredOnce", helper_start)
    helper = text[helper_start:helper_end]
    assert "window.__erpLastStructuredData?.shipment?.as_content" in helper
    assert "options.reregister === true" in helper
    assert "AS 접수 수정" in helper
    assert "수정 내용 저장" in helper
    assert "erp-workflow-stage" not in helper

    binding_start = text.index("document.querySelectorAll('[data-erp-as-reregister-open]')")
    binding_end = text.index("if (modalEl) {", binding_start)
    binding = text[binding_start:binding_end]
    assert "erpAsReregisterBound" in binding
    assert "erpOpenAsReceiveModal(targetId, previousStage, { reregister: true })" in binding
    assert "주문 정보를 불러온 뒤 다시 시도해주세요." in binding


def test_as_register_success_refreshes_mutation_version_before_followup_save() -> None:
    """접수 API가 version 을 올린 뒤 폼 저장이 stale If-Match 로 409 가 나면 안 된다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    start = text.index("const regRes = await fetch(`/api/orders/${targetId}/as/register`")
    end = text.index("const saveResult = await erpSaveStructured({", start)
    block = text[start:end]
    assert "typeof regData.mutation_version === 'number'" in block
    assert "window.__erpLastMutationVersion = regData.mutation_version" in block


def test_shared_erp_order_js_has_no_beta_runtime_mirror() -> None:
    """The shared ERP runtime no longer exports beta globals or beta data-* fallbacks."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "window.ERP_BETA_ENABLED" not in text
    assert "__ERP_BETA_DRAFT_MODE" not in text
    assert "data-erp-beta-enabled" not in text
    assert "data-erp-beta-draft-mode" not in text


def test_shared_erp_order_js_links_drawing_attachments_to_items() -> None:
    """Drawing attachments must expose the same product-item link controls as measurement attachments."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    support_start = text.index("function erpAttachmentSupportsItemLink")
    support_end = text.index("function erpAttachmentsSetStatus", support_start)
    support_block = text[support_start:support_end]
    assert "return normalized === 'measurement' || normalized === 'drawing';" in support_block

    preview_start = text.index("function erpSyncAttachmentPreviewActions")
    preview_end = text.index("async function erpReindexItemLinkedAttachmentsAfterItemRemoval", preview_start)
    preview_block = text[preview_start:preview_end]
    assert "const canLinkToItem = !!(a && erpAttachmentSupportsItemLink(a));" in preview_block
    assert "select.classList.toggle('d-none', !canLinkToItem);" in preview_block
    assert "select.disabled = !canLinkToItem;" in preview_block
    assert "select.innerHTML = erpBuildAttachmentItemOptions(a.item_index);" in preview_block
    assert "unlinkBtn.classList.toggle('d-none', !canLinkToItem || linkedIndex === null);" in preview_block

    reindex_start = text.index("async function erpReindexItemLinkedAttachmentsAfterItemRemoval")
    reindex_end = text.index("async function erpUploadItemAttachments", reindex_start)
    reindex_block = text[reindex_start:reindex_end]
    assert "(__erpAttachments || []).filter((a) => erpAttachmentSupportsItemLink(a))" in reindex_block
    assert "erpReindexMeasurementAttachmentsAfterItemRemoval" not in text

    render_start = text.index("function erpRenderAttachments()")
    render_end = text.index("async function erpLoadAttachments", render_start)
    render_block = text[render_start:render_end]
    assert "showItemBadge: erpAttachmentSupportsItemLink(a)" in render_block
    assert "${erpAttachmentSupportsItemLink(a) ? `" in render_block


def test_shared_erp_order_js_preserves_drawing_operational_state() -> None:
    """ERP Order full-form save must not drop drawing timeline/files/assignees from the last snapshot."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    collect_start = text.index("function erpCollectStructured()")
    collect_end = text.index("async function erpSaveStructured", collect_start)
    collect_block = text[collect_start:collect_end]

    for key in (
        "drawing_status",
        "drawing_transferred",
        "drawing_current_files",
        "drawing_transfer_history",
        "last_drawing_transfer",
        "drawing_assignees",
        "blueprint",
        "estimate_preview",
        "channeltalk_push",
        "channeltalk_push_drawing",
        "channeltalk_push_estimate",
        "channeltalk_push_as",
    ):
        assert f"'{key}'" in collect_block

    workflow_start = collect_block.index("workflow: (function ()")
    workflow_end = collect_block.index("flags:", workflow_start)
    workflow_block = collect_block[workflow_start:workflow_end]
    assert "prevSd.workflow" in workflow_block
    assert "JSON.parse(JSON.stringify(prevWorkflow))" in workflow_block
    assert "getVal('erp-workflow-stage')" in workflow_block
    assert "formRank >= 0 && prevRank >= 0" in workflow_block
    assert "formRank === prevRank + 1" in workflow_block
    assert "workflow.stage = prevStage;" in workflow_block


def test_structured_put_preserves_estimate_preview_state() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "foms/api/erp_orders_structured.py").read_text(encoding="utf-8")

    keys_start = text.index("_OPERATIONAL_TOP_LEVEL_KEYS = (")
    keys_end = text.index("def _merge_preserving_missing", keys_start)
    keys_block = text[keys_start:keys_end]
    assert "'estimate_preview'" in keys_block
    assert "'channeltalk_push'" in keys_block
    assert "'channeltalk_push_drawing'" in keys_block
    assert "'channeltalk_push_estimate'" in keys_block
    assert "'channeltalk_push_as'" in keys_block


def test_shared_erp_order_js_does_not_auto_save_before_user_save() -> None:
    """Add-order actions must not persist anything until the user presses the save button."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "erpRequireFinalizedOrderForAction" not in text
    assert "erpEnsureFinalizedOrderForAction" not in text
    assert "function erpCanUsePersistedOrderAction(actionText)" in text
    assert "function erpToggleLocalPaymentState(pType, targetConfirmed)" in text
    assert "window.erpIsDraftBackedOrder = erpIsDraftBackedOrder;" in text

    payment_start = text.index("window.erpTogglePayment = async function")
    payment_end = text.index("// ERP Order: 발주사 드롭다운", payment_start)
    payment_block = text[payment_start:payment_end]
    assert "erpSaveStructured(" not in payment_block
    assert "erpToggleLocalPaymentState(pType, targetConfirmed);" in payment_block

    item_upload_start = text.index("async function erpUploadItemAttachments")
    item_upload_end = text.index("function erpRenderItemAttachmentPanels", item_upload_start)
    item_upload_block = text[item_upload_start:item_upload_end]
    assert "erpSaveStructured(" not in item_upload_block
    assert "const targetId = await erpRequireOrderIdOrWarn('제품 첨부 업로드:');" in item_upload_block
    assert "erpCanUsePersistedOrderAction('제품 첨부 업로드는')" not in item_upload_block
    assert "erpCanUsePersistedOrderAction('제품 이미지 업로드는')" not in item_upload_block

    common_upload_start = text.index("async function erpUploadSelectedAttachments")
    common_upload_end = text.index("function erpGenerateConversionText", common_upload_start)
    common_upload_block = text[common_upload_start:common_upload_end]
    assert "erpSaveStructured(" not in common_upload_block
    assert "const targetId = await erpRequireOrderIdOrWarn('첨부 업로드:');" in common_upload_block
    assert "erpCanUsePersistedOrderAction('첨부 업로드는')" not in common_upload_block

    push_start = text.index("document.getElementById('erp-channeltalk-push-btn')")
    push_end = text.index("initErpMainDatePickers();", push_start)
    push_block = text[push_start:push_end]
    # PUSH는 사용자가 명시적으로 누른 전송 액션 — 미저장/draft면 되묻지 않고 먼저 저장(승격)한다.
    # 게이트 상세 계약: test_shared_erp_order_js_gates_channel_push_on_unsaved_changes.
    assert "_autosave.isDirty()" in push_block
    assert "erpIsDraftBackedOrder()" in push_block
    assert "erpCanUsePersistedOrderAction('푸쉬는')" in push_block
    assert "erpSliceConversionTextForChannelPush(" in push_block
    assert "erpHasPriorChannelPush" in push_block
    assert "erpIsChannelPushResendNoteRequired" in push_block
    assert "resendRecoveryUsed" in push_block
    assert "change_note" in push_block


def test_channel_push_confirm_js_resend_recovery_contract() -> None:
    """재전송 modal: PUSH 잠금, desync 복구 헬퍼, 중복 session 차단."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-channel-push-confirm.js").read_text(encoding="utf-8")
    assert "function erpIsChannelPushResendNoteRequired(message)" in text
    assert "function _setChannelPushButtonsLocked(locked)" in text
    assert "erp-channeltalk-push-btn" in text
    assert "erp-channeltalk-push-drawing-btn" in text
    assert "if (typeof _pendingResolve === 'function')" in text
    assert "재전송 시 변경 내용" in text
    assert "const MIN_NOTE_LEN = 1" in text
    assert "_resolvedBySend" in text
    assert "내부 변경" not in text


def test_channel_push_kind_picker_contract() -> None:
    """모바일 PUSH 선택 시트: 4종 제공 + 재전송 modal 중첩 회피(hidden 후 resolve)."""
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-channel-push-confirm.js").read_text(encoding="utf-8")
    picker = (
        root / "templates/orders/partials/erp_channel_push_picker_modal.html"
    ).read_text(encoding="utf-8")
    shared = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "as: 'channeltalk_push_as'" in js
    assert "as: 'AS PUSH'" in js
    assert "erp-channeltalk-push-picker-btn" in js
    assert "erp-channeltalk-push-as-btn" in js
    assert "function erpPromptChannelPushKind()" in js
    # 선택 결과는 시트가 완전히 닫힌 뒤 반환해야 재전송 modal 과 겹치지 않는다.
    picker_mount = js[js.index("function erpMountChannelPushPickerModal()"):]
    assert "hidden.bs.modal" in picker_mount

    for kind in ("measurement", "measure_room", "drawing", "as"):
        assert f'data-erp-push-kind="{kind}"' in picker
    # 시트 색 = PC 버튼 색(같은 행위를 두 표면에서 다른 색으로 보이지 않게).
    for cls in (
        "erp-push-btn--measurement",
        "erp-push-btn--measure-room",
        "erp-push-btn--drawing",
        "erp-push-btn--as",
    ):
        assert cls in picker

    assert "window.erpPromptChannelPushKind = erpPromptChannelPushKind;" in js
    assert "erpPromptChannelPushKind()" in shared

    # 선택 시트는 화면 중앙에 내용 높이만큼만 — 전체 페이지 bottom-sheet 아님.
    assert "modal-dialog-centered" in picker
    assert "modal-dialog-scrollable" not in picker
    css = (root / "static/css/orders/erp-channel-push.css").read_text(encoding="utf-8")
    sheet_block = css[css.index("@media (max-width: 767.98px)"):css.index("/* PUSH 종류 선택")]
    assert "erp-channel-push-picker-modal" not in sheet_block
    # erp-pro 모바일 전역이 모든 모달을 max-width:100vw !important 로 풀스크린 강제하므로
    # 선택 시트는 .erp-pro 를 포함한 같은 특이도 + !important 로 되돌려야 눌리지 않는다.
    assert ".erp-pro .erp-channel-push-picker-modal .modal-dialog" in css
    assert "max-width: 22rem !important" in css
    assert ".erp-pro .erp-channel-push-picker-modal .modal-content" in css

    # 액션바 PUSH 트리거는 회색(secondary)이 아니라 파스텔 색.
    mobile = (
        root / "templates/orders/partials/erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")
    trigger_line = next(
        line for line in mobile.splitlines() if "erp-channeltalk-push-picker-btn" in line
    )
    assert "erp-mobile-push-btn--pastel" in trigger_line
    assert "foms-btn--secondary" not in trigger_line
    assert ".erp-mobile-push-btn--pastel {" in css


def test_mobile_action_bar_buttons_do_not_wrap_labels() -> None:
    """모바일 액션바 4버튼(저장·PUSH·알림톡·공유): 390px 에서 라벨이 세로로 접히면 안 된다."""
    root = Path(__file__).resolve().parents[2]
    css = (root / "static/css/components/foms-form-field.css").read_text(encoding="utf-8")
    block_start = css.index(".erp-mobile-sticky-action-bar .foms-btn {")
    block = css[block_start:css.index("}", block_start)]
    assert "flex: 1 1 0" in block
    # flex 아이템 기본 min-width:auto 는 내용 폭 아래로 못 줄어 라벨이 접힌다.
    assert "min-width: 0" in block
    assert "white-space: nowrap" in block


def test_measure_room_push_is_wired_on_pc_and_sheet_with_own_history_key() -> None:
    """실측 PUSH: PC 버튼·모바일 시트·이력 키가 영발과 분리돼 배선된다."""
    root = Path(__file__).resolve().parents[2]
    pc = (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    shared = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    confirm = (root / "static/js/orders/erp-channel-push-confirm.js").read_text(encoding="utf-8")

    # PC: 영발 PUSH 옆 버튼 — 테두리만 있는 outline 은 옆 solid 버튼들 사이에서 흐려 보였다.
    assert 'id="erp-channeltalk-push-measure-btn"' in pc
    assert "실측 PUSH" in pc
    assert "erp-push-btn--measure-room" in pc
    # 알림톡=카카오 노랑, 발주 PUSH=진한 주황(노랑끼리 붙어 보이지 않게 분리).
    assert "erp-alimtalk-btn--kakao" in pc
    assert "erp-push-btn--drawing" in pc
    assert 'class="btn btn-sm erp-push-btn--drawing" type="button" id="erp-channeltalk-push-drawing-btn"' in pc
    assert "btn-outline-primary dropdown-toggle" not in pc
    css = (root / "static/css/orders/erp-channel-push.css").read_text(encoding="utf-8")
    assert ".erp-push-btn--measure-room" in css
    # PC 버튼과 모바일 시트 선택지는 같은 색 클래스를 쓴다.
    picker = (
        root / "templates/orders/partials/erp_channel_push_picker_modal.html"
    ).read_text(encoding="utf-8")
    assert "erp-push-btn--measure-room" in picker
    assert pc.index("erp-channeltalk-push-btn") < pc.index("erp-channeltalk-push-measure-btn")

    # 클릭 → 공용 핸들러에 measure_room 종류로 위임
    assert "erpRunChannelPush(this, 'measure_room')" in shared
    # 이력 키 분리 — 영발을 보냈다고 실측 PUSH 가 재전송으로 취급되면 안 된다.
    assert "measure_room: 'channeltalk_push_measure_room'" in confirm
    assert "measure_room: '실측 PUSH'" in confirm
    assert "'erp-channeltalk-push-measure-btn'" in confirm
    # 폼 PUT 이 서버 소유 이력을 지우지 않도록 보존 키 목록에도 등재
    assert "'channeltalk_push_measure_room'" in shared


def test_measure_room_push_sends_conversion_text_verbatim() -> None:
    """실측방(measure_room) PUSH 본문 = 변환 텍스트 그대로. 영발·발주는 실측 헤더를 자른다.

    실측방은 실측일·시   간이 그대로 있어야 일정이 전달된다. 반대로 영발방/발주방에는
    그 두 줄이 나가면 안 되므로(사용자 확정 규칙) 슬라이스를 유지한다.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    push_start = text.index(
        "async function erpRunChannelPush(btn, pushKind, resendRetryState)"
    )
    push_end = text.index("initErpMainDatePickers();", push_start)
    push_block = text[push_start:push_end]

    assert "pushKind === 'measure_room'" in push_block
    assert "String(rawConversionText).trim()" in push_block
    assert "erpSliceConversionTextForChannelPush(rawConversionText)" in push_block
    # 영발(measurement)은 슬라이스 경로 — 실측일/시간이 영발방으로 나가면 안 된다.
    assert "pushKind === 'measurement'" not in push_block

    # 태블릿 실측 폼은 measure_room 버튼이 없다 — 항상 슬라이스 경로.
    tablet_js = (root / "static/js/foms/tablet-measure-form.js").read_text(encoding="utf-8")
    tablet_start = tablet_js.index("function requestPush(pushKind)")
    tablet_block = tablet_js[tablet_start:tablet_start + 900]
    assert "sliceConversionTextForChannelPush(buildConversionText())" in tablet_block
    assert "measure_room" not in tablet_block


def test_as_push_text_is_server_built_not_client_built() -> None:
    """AS 본문은 서버 SSOT — 폼이 없는 AS 대시보드와 같은 문구를 보장한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    # 클라이언트 조립기는 제거됐다(두 벌이면 화면마다 문구가 갈린다).
    assert "erpBuildAsPushText" not in text

    push_start = text.index("document.getElementById('erp-channeltalk-push-btn')")
    push_end = text.index("initErpMainDatePickers();", push_start)
    push_block = text[push_start:push_end]
    assert "if (pushKind !== 'as')" in push_block
    # 변환 텍스트 경로는 AS 가 아닐 때만 탄다.
    assert "erpSliceConversionTextForChannelPush(" in push_block
    # AS-BIND-01: ERP AS PUSH도 대시보드와 같은 확인창 + attachment_ids.
    assert "fomsConfirmAndSendAsPush" in push_block


def test_erp_as_gallery_upload_binds_anchor_before_batch() -> None:
    """AS-BIND-01: 공통첨부 분류 AS는 업로드 전에 앵커를 잡고 as_log_id를 실어 보낸다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    start = text.index("async function erpUploadCommonAttachmentFiles")
    block = text[start:start + 9000]
    assert "fomsEnsureAsUploadAnchor" in block
    assert "asLogId: asLogId" in block
    assert "sortOrders: sortOrders" in block
    ensure_idx = block.index("fomsEnsureAsUploadAnchor")
    optimistic_idx = block.index("Optimistic UI Start")
    assert ensure_idx < optimistic_idx


def test_shared_erp_order_supports_scoped_clipboard_image_upload() -> None:
    """Clipboard screenshots should upload through the same attachment path, scoped to the attachment box."""
    root = Path(__file__).resolve().parents[2]
    js_text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    template_text = (
        root / "templates" / "orders" / "partials" / "erp_order_tab.html"
    ).read_text(encoding="utf-8")

    assert 'data-erp-attachment-paste-zone="common"' in template_text
    assert 'data-erp-attachment-paste-zone="as-receive"' in template_text
    assert "이미지를 붙여넣으면 바로 업로드됩니다." in template_text
    assert "Ctrl+V로 바로 업로드" in template_text
    assert "카메라로 촬영" in template_text
    assert 'data-foms-photo-capture' in template_text

    assert 'data-erp-attachment-paste-zone="item"' in js_text
    assert "이 항목에 바로 업로드됩니다." in js_text
    assert "캡처 이미지를 항목에 바로 업로드" in js_text
    assert "const itemAttachmentPasteHint = isMobileForm" in js_text
    assert "itemAttachmentPasteHint" in js_text
    assert "function erpAppendAsReceiveFiles(files)" in js_text
    assert "function erpSetFileInputFiles(input, files)" in js_text
    assert "function erpRenderAsReceiveFilePreview(files)" in js_text
    assert "erpAppendAsReceiveFiles(files);" in js_text
    assert "window.__erpAsReceiveClipboardFiles" in js_text
    assert "async function erpUploadCommonAttachmentFiles(files, options = {})" in js_text
    assert "await erpUploadCommonAttachmentFiles(files);" in js_text
    assert "function erpGetClipboardImageFiles(event)" in js_text
    assert "item.kind !== 'file'" in js_text
    assert "startsWith('image/')" in js_text
    assert "item.getAsFile()" in js_text
    assert "new File([rawFile], name" in js_text
    assert "root.addEventListener('paste', erpHandleAttachmentPaste);" in js_text
    assert "function erpSetAttachmentPasteZoneActive(zone, isActive)" in js_text
    assert "root.addEventListener('focusin'" in js_text
    assert "root.addEventListener('focusout'" in js_text
    assert "rgba(13,110,253,0.18)" in js_text
    assert "await erpUploadItemAttachments(itemIndex, files);" in js_text
    assert "document.addEventListener('paste'" not in js_text


def test_shared_erp_order_js_guards_duplicate_save_clicks_and_tokens_draft_create() -> None:
    """Save clicks must be single-flight, and draft creation must carry a page token."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    save_start = text.index("async function erpSaveStructured(opts = {})")
    save_end = text.index("async function erpSaveStructuredOnce(opts = {})", save_start)
    save_block = text[save_start:save_end]
    assert "typeof opts.preventDefault === 'function'" in save_block
    assert "opts.preventDefault();" in save_block
    assert "opts.stopPropagation" in save_block
    assert "opts = {};" in save_block
    assert "_erpSaveStructuredInFlight" in save_block
    assert "return _erpSaveStructuredInFlight;" in save_block
    assert "erpSetSaveButtonBusy(true);" in save_block
    assert "erpSetSaveButtonBusy(false);" in save_block
    assert "function erpFocusWithoutScroll(el)" in text
    assert "el.focus({ preventScroll: true });" in text
    assert "erpFocusWithoutScroll(document.getElementById('erp-customer-name'))" in text
    assert "erpFocusWithoutScroll(firstItem);" in text
    assert "document.getElementById('erp-save-btn')?.addEventListener('click', erpSaveStructured);" in text
    assert "function erpNavigateAfterStructuredSave(targetUrl)" in text
    assert "window.history.back();" in text
    assert "erpNavigateAfterStructuredSave(erpAppendFocusOrderParam(targetUrl, targetId));" in text
    assert "fomsMountErpOrderSurface" in text
    dom_ready_start = text.index("document.addEventListener('DOMContentLoaded', function () {")
    dom_ready_end = text.index("// ============================================\n// ERP Order: Attachments", dom_ready_start)
    dom_ready_block = text[dom_ready_start:dom_ready_end]
    assert "erpLoadStructured();" not in dom_ready_block
    assert "function erpExpandMobileAttachmentSections()" in text
    assert "function erpItemAttachmentLinksForRow(" in text
    assert "foms:reload-order-list-after-erp-save" in text
    assert "sessionStorage.setItem('foms:reload-order-list-after-erp-save', target.href);" in text

    draft_start = text.index("var erpGetDraftRequestToken")
    draft_end = text.index("window.erpEnsureDraftOrderId = erpEnsureDraftOrderId;", draft_start)
    draft_block = text[draft_start:draft_end]
    assert "window.__ERP_DRAFT_REQUEST_TOKEN" in draft_block
    assert "crypto.randomUUID" in draft_block
    assert "body: JSON.stringify({ draft_token: erpGetDraftRequestToken() })" in draft_block


def test_shared_erp_order_js_sends_if_match_and_preserves_input_on_conflict() -> None:
    """저장은 If-Match(mutation_version)를 실어 보내고, 409 는 입력을 파괴하지 않는다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    # 로드가 토큰을 보관한다(숫자가 아니면 null → If-Match 생략, 구버전 서버 하위호환).
    load_start = text.index("async function erpLoadStructured(bootstrapData, options)")
    load_block = text[load_start : text.index("const sd = data.structured_data || {};", load_start)]
    assert "window.__erpLastMutationVersion =" in load_block
    assert "typeof data.mutation_version === 'number' ? data.mutation_version : null;" in load_block

    save_start = text.index("async function erpSaveStructuredOnce(opts = {})")
    save_end = text.index("document.addEventListener('DOMContentLoaded', function () {", save_start)
    save_block = text[save_start:save_end]

    # (1) If-Match 전송 + 토큰 가드 + force 재시도에서는 생략.
    assert "const saveHeaders = { 'Content-Type': 'application/json' };" in save_block
    assert (
        "if (opts.force !== true && typeof window.__erpLastMutationVersion === 'number') {"
        in save_block
    )
    assert "saveHeaders['If-Match'] = String(window.__erpLastMutationVersion);" in save_block
    assert "headers: saveHeaders," in save_block

    # (2) 409 분기 + 덮어쓰기 재시도는 1회(force 호출에서는 재진입하지 않는다).
    assert "if (res.status === 409 && opts.force !== true) {" in save_block
    assert "다른 사용자가 이 주문을 먼저 수정했습니다." in save_block
    assert "return await erpSaveStructuredOnce({ ...opts, force: true });" in save_block

    # (3) 409 분기 안에서는 폼을 절대 재조회하지 않는다(입력 보존 계약).
    conflict_start = save_block.index("if (res.status === 409 && opts.force !== true) {")
    conflict_end = save_block.index("if (!data.success) {", conflict_start)
    conflict_block = save_block[conflict_start:conflict_end]
    assert "erpLoadStructured" not in conflict_block
    assert "innerHTML" not in conflict_block

    # (4) 저장 성공 시 토큰 갱신 — 없으면 두 번째 저장이 stale 토큰으로 항상 409 가 된다.
    success_start = save_block.index("if (!data.success) {")
    success_block = save_block[success_start : save_block.index("erpSetStatus(doRedirect", success_start)]
    assert "window.__erpLastMutationVersion =" in success_block


def test_shared_erp_order_js_guards_quest_auto_transition_reload_on_dirty() -> None:
    """Quest 전팀 승인 자동전환은 dirty(미저장 입력)일 때 폼 재조회를 건너뛰고 알린다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    approve_start = text.index("async function erpApproveQuestTeam(team)")
    approve_end = text.index("async function erpUpdateQuestStatus()", approve_start)
    approve_block = text[approve_start:approve_end]

    assert "setTimeout(async () => {" in approve_block
    dirty_idx = approve_block.index(
        "var _erpDirty = _autosave && typeof _autosave.isDirty === 'function'"
    )
    reload_idx = approve_block.index("await erpLoadStructured();")
    assert dirty_idx < reload_idx
    assert "if (!_erpDirty) {" in approve_block
    assert "_autosave.recaptureBaseline();" in approve_block
    # dirty 스킵은 조용히 넘어가지 않는다.
    assert "미저장 입력이 있어 화면 새로고침을 건너뛰었습니다" in approve_block


def test_shared_erp_order_js_syncs_stage_from_measurement_date() -> None:
    """실측일 선택/해제는 단계 select를 실측/주문접수로 즉시 동기화한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    sync_start = text.index("var syncWorkflowStageByMeasurementDate")
    sync_end = text.index("var adjustTextareaHeight", sync_start)
    sync_block = text[sync_start:sync_end]

    assert 'document.getElementById("erp-measurement-date")' in sync_block
    assert 'document.getElementById("erp-workflow-stage")' in sync_block
    assert 'stageEl.value = "MEASURE";' in sync_block
    assert 'stageEl.value = "RECEIVED";' in sync_block
    assert 'current === "RECEIVED"' in sync_block
    assert 'current === "MEASURE"' in sync_block
    assert 'isLahomLike' in sync_block
    assert "window.FOMS_STAGE_OVERRIDE.noteCurrentStage" in sync_block
    assert "window.syncWorkflowStageByMeasurementDate = syncWorkflowStageByMeasurementDate;" in sync_block
    assert "onChange: function ()" in text
    assert "syncWorkflowStageByMeasurementDate();" in text
    assert "mEl.addEventListener('change', syncWorkflowStageByMeasurementDate);" in text
    assert "mEl.addEventListener('input', syncWorkflowStageByMeasurementDate);" in text


def test_shared_erp_order_js_persists_deposit_adjusted_final_totals() -> None:
    """ERP Order 저장은 잔금을 canonical final amount로 유지하고 변환 텍스트는 발주방 공유 포맷을 내보낸다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpBuildTotals(itemsTotal, depositAmount, discountAmount, freeInputAmount)" in text
    assert "free_input_amount: freeInput" in text
    assert "contract_total: total" in text
    assert "final_amount: balance" in text

    collect_start = text.index("function erpCollectStructured()")
    collect_end = text.index("async function erpSaveStructured", collect_start)
    collect_block = text[collect_start:collect_end]
    assert "const totals = erpBuildTotals(itemsTotal, depositAmount, discountAmount, freeInputAmount);" in collect_block
    assert "free_input: erpBuildFreeInputStoredValue()" in collect_block
    assert "function erpSumFreeInputAmountFromText" in text
    assert "function erpBuildFreeInputStoredValue" in text
    assert "erp-free-input-text" in text
    assert "function erpAppendConversionFreeInputBlock" in text
    assert "function erpFormatFreeInputForConversion" in text
    assert "erpFormatMoneyKRW(amount)" in text
    free_input_fn_start = text.index("function erpAppendConversionFreeInputBlock")
    free_input_fn_end = text.index("function erpReadItemFieldValue", free_input_fn_start)
    free_input_fn = text[free_input_fn_start:free_input_fn_end]
    assert "자유입력" not in free_input_fn
    assert "erpFormatFreeInputForConversion(value)" in free_input_fn
    assert "totals," in collect_block
    assert "deposit: totals.deposit_amount" in collect_block
    assert "discount: totals.discount_amount" in collect_block

    conversion_start = text.index("function erpGenerateConversionText()")
    conversion_end = text.index("function erpCopyToClipboard()", conversion_start)
    conversion_block = text[conversion_start:conversion_end]
    assert "function erpHasConversionTextValue(value)" in text
    assert "function erpAppendConversionTextLine(text, label, value)" in text
    assert "function erpAppendConversionMoneyLine(text, label, amount, suffix)" in text
    assert "erpAppendConversionTextLine(itemText, '추가 입력', extraInput)" not in conversion_block
    assert "erpAppendConversionExtraInputLine(itemText, extraInput)" in conversion_block
    assert "function erpReadItemFieldValue(row, key)" in text
    assert "function erpAppendConversionExtraInputLine(text, value)" in text
    assert conversion_block.index("erpAppendConversionTextLine(itemText, '기 타', misc)") < conversion_block.index(
        "erpAppendConversionMoneyLine(itemText, '항목 견적', itemPrice)"
    )
    assert conversion_block.index("erpAppendConversionMoneyLine(itemText, '항목 견적', itemPrice)") < conversion_block.index(
        "erpAppendConversionExtraInputLine(itemText, extraInput)"
    )
    assert "const itemPrice = getRowVal('price');" in conversion_block
    assert "allExtraInputs" not in conversion_block
    assert "getVal('erp-manager')" in conversion_block
    assert "factory2Checked" in conversion_block
    assert "erp-factory2" in conversion_block
    assert "★★\\n" in conversion_block
    assert conversion_block.index("if (factory2Checked) text += '★★\\n';") < conversion_block.index(
        "erpAppendConversionTextLine(text, '실측일', measurementDate)"
    )
    # 특이사항 4종: 부모 필드 바로 아래 (빈 값이면 helper가 스킵)
    assert "getVal('erp-measurement-note')" in conversion_block
    assert "getVal('erp-construction-note')" in conversion_block
    assert "getVal('erp-address-note')" in conversion_block
    assert "getVal('erp-phone-note')" in conversion_block
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '시   간', measurementTime)"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '실측 특이사항', getVal('erp-measurement-note'))"
    )
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '실측 특이사항', getVal('erp-measurement-note'))"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '고객명', customerName)"
    )
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '시공일', constructionDate)"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '시공 특이사항', getVal('erp-construction-note'))"
    )
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '시공 특이사항', getVal('erp-construction-note'))"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '시공시간', constructionTime)"
    )
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '주  소', address)"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '주소 특이사항', getVal('erp-address-note'))"
    )
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '주소 특이사항', getVal('erp-address-note'))"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '연락처', phone)"
    )
    assert conversion_block.index(
        "erpAppendConversionTextLine(text, '연락처', phone)"
    ) < conversion_block.index(
        "erpAppendConversionTextLine(text, '연락처 특이사항', getVal('erp-phone-note'))"
    )
    # 태블릿 실측 폼 변환 미러도 동일 배치 (PC SSOT 동기)
    tablet_js = (root / "static/js/foms/tablet-measure-form.js").read_text(encoding="utf-8")
    tablet_start = tablet_js.index("function buildConversionText()")
    tablet_end = tablet_js.index("function refreshConversionText()", tablet_start)
    tablet_block = tablet_js[tablet_start:tablet_end]
    assert tablet_block.index('convAppendLine(text, "시   간", measurementTime)') < tablet_block.index(
        'convAppendLine(text, "실측 특이사항", notesValue("measurement_note"))'
    )
    assert tablet_block.index(
        'convAppendLine(text, "실측 특이사항", notesValue("measurement_note"))'
    ) < tablet_block.index('convAppendLine(text, "고객명", customerName)')
    assert tablet_block.index('convAppendLine(text, "시공일", constructionDate)') < tablet_block.index(
        'convAppendLine(text, "시공 특이사항", notesValue("construction_note"))'
    )
    assert tablet_block.index(
        'convAppendLine(text, "시공 특이사항", notesValue("construction_note"))'
    ) < tablet_block.index('convAppendLine(text, "시공시간", constructionTime)')
    assert tablet_block.index('convAppendLine(text, "주  소", address)') < tablet_block.index(
        'convAppendLine(text, "주소 특이사항", notesValue("address_note"))'
    )
    assert tablet_block.index(
        'convAppendLine(text, "주소 특이사항", notesValue("address_note"))'
    ) < tablet_block.index('convAppendLine(text, "연락처", phone)')
    assert tablet_block.index('convAppendLine(text, "연락처", phone)') < tablet_block.index(
        'convAppendLine(text, "연락처 특이사항", notesValue("phone_note"))'
    )
    slice_start = text.index("function erpSliceConversionTextForChannelPush")
    slice_end = text.index("function erpGenerateConversionText()", slice_start)
    slice_block = text[slice_start:slice_end]
    assert "hasFactory2Stars" in slice_block
    assert "return `★★\\n${body}`;" in slice_block
    # 고객명 slice 폐기 — 실측일/시간만 제거해 실측 특이사항이 채널톡에 남는다
    assert "raw.search(/^고객명" not in slice_block
    assert "실측일\\s*:" in slice_block
    assert "시\\s*간\\s*:" in slice_block
    tablet_js = (root / "static/js/foms/tablet-measure-form.js").read_text(encoding="utf-8")
    tablet_slice_start = tablet_js.index("function sliceConversionTextForChannelPush")
    tablet_slice_end = tablet_js.index("function buildConversionText()", tablet_slice_start)
    tablet_slice = tablet_js[tablet_slice_start:tablet_slice_end]
    assert "raw.search(/^고객명" not in tablet_slice
    assert "실측일\\s*:" in tablet_slice
    assert "erpAppendConversionMoneyLine(text, '출고가', totals.shipping_price)" in conversion_block
    assert "erpAppendConversionMoneyLine(text, '예약금(선금)', totals.deposit_amount)" in conversion_block
    assert "_erpIsBalancePaymentConfirmed()" in conversion_block
    assert "const balanceSuffix = _erpIsBalancePaymentConfirmed() ? '(결제 완)' : '';" in conversion_block
    assert "erpAppendConversionMoneyLine(text, '잔금', totals.final_amount, balanceSuffix)" in conversion_block
    assert "erpAppendConversionFreeInputBlock(text, freeInputVal)" in conversion_block
    assert "erpAppendConversionTextLine(text, '잔금메모', balanceNoteVal)" in conversion_block
    assert "erpAppendConversionTextLine(text, '현금영수증', cashReceiptVal)" in conversion_block
    assert "function erpResolveFreeInputText" in text
    assert "legacyPayments.free_input" in text
    assert "erpHasConversionTextValue(cashReceiptVal) && totals.final_amount > 0" in conversion_block
    assert "function erpResolveCashReceipt" in text
    assert "function erpResolveBalanceNote" in text
    assert "Object.prototype.hasOwnProperty.call(modernPayment, 'cash_receipt')" in text
    assert "cash_receipt: String(getVal('erp-cash-receipt') || '')" in collect_block
    assert "balance_note: String(getVal('erp-balance-note') || '').trim()" in collect_block
    assert "cash_receipt: erpResolveCashReceipt(sd)" in text
    assert "balance_note: erpResolveBalanceNote(sd)" in text
    assert "erp-cash-receipt-section" in text
    assert "erp-balance-note-section" in text
    assert "erp-balance-note-toggle" in text
    assert "window.__ERP_BALANCE_NOTE_BOUND" in text
    assert "section.hidden = !open" in text
    assert "clearValue: true" in text
    assert 'id="erp-balance-note-section"' in (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    assert "hidden" in (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    assert 'data-payment-type="balance"' in text
    assert "erp-custom-payment-confirmed" in text
    assert "ERP_LAHOM_STANDARD_DEPOSIT_AMOUNTS" in text
    assert "Object.freeze([50000, 100000, 200000, 300000, 400000])" in text
    assert "function _erpShouldShowLahomDepositGold(amount)" in text
    assert 'orderer !== "라홈"' in text
    assert "function _erpRefreshDepositCoinVisual()" in text
    assert "라홈 비표준 예약금" in text
    assert "erp-custom-payment-lahom-hint" in text
    assert "_erpRefreshDepositCoinVisual()" in text
    # deposit binder onRecalc must refresh coin; orderer sync too
    deposit_bind = text.index(
        "erpBindAmountInput(\n        document.getElementById('erp-deposit-amount')"
    )
    assert "_erpRefreshDepositCoinVisual()" in text[deposit_bind : deposit_bind + 350]
    sync_start = text.index("function syncWorkflowStageByOrderer()")
    sync_end = text.index("window.syncWorkflowStageByOrderer", sync_start)
    assert "_erpRefreshDepositCoinVisual()" in text[sync_start:sync_end]
    assert "visibleItemIndex += 1" in conversion_block
    assert "function erpReadScheduleTimeValue(selectId, inputId)" in text
    assert "erpReadScheduleTimeValue('erp-construction-time-select', 'erp-construction-time')" in conversion_block
    assert "실측일\\s*:" in text
    assert "text += `예약금(선금) : ${erpFormatMoneyKRW(totals.deposit_amount)}\\n`;" not in conversion_block
    assert "선결제금액" not in conversion_block


def test_sum_free_input_amount_from_multiline_text() -> None:
    """자유입력 멀티라인에서 라벨:금액 패턴 금액을 합산한다."""
    from foms.services.estimate_service import _parse_free_input_lines, _sum_free_input_amount_from_text

    assert _sum_free_input_amount_from_text("") == 0
    assert _sum_free_input_amount_from_text("운반비 : 30,000\n세금 : 10,000") == 40000
    assert _sum_free_input_amount_from_text("메모만") == 0
    assert _parse_free_input_lines("운반비 : 30,000") == [{"label": "운반비", "amount": 30000}]
    assert _parse_free_input_lines("50,000") == [{"label": "추가", "amount": 50000}]


def test_shared_erp_amount_input_allows_empty_value_while_deleting() -> None:
    """금액 input은 원 suffix 뒤 backspace를 숫자 삭제로 처리하고, 삭제 중 빈 값을 허용한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    bind_start = text.index("function erpBindAmountInput(inputEl, parseFn, onRecalc)")
    bind_end = text.index("document.getElementById('erp-deposit-amount')", bind_start)
    bind_block = text[bind_start:bind_end]

    assert "function deleteErpAmountDigitBeforeSuffix(el)" in bind_block
    assert "start !== end || start !== value.length" in bind_block
    assert "const nextRaw = raw.slice(0, -1);" in bind_block
    assert "el.value = nextRaw ? erpFormatDepositDisplay(parseInt(nextRaw, 10)) : '';" in bind_block
    assert "event.key !== 'Backspace'" in bind_block
    assert "event.inputType !== 'deleteContentBackward'" in bind_block
    assert "if (deleteErpAmountDigitBeforeSuffix(this)) event.preventDefault();" in bind_block
    assert "const raw = prevValue.replace(/[^0-9]/g, '');" in bind_block
    assert "if (!raw) {" in bind_block
    assert "if (this.value !== '') this.value = '';" in bind_block
    assert "return;" in bind_block
    assert "restoreAmountCaret(this, prevValue, prevCaret, formatted);" in bind_block
    assert "setAmountCaretBeforeSuffix(el);" in bind_block
    assert "this.value = erpFormatDepositDisplay(num);" in bind_block


def test_shared_erp_price_input_uses_amount_binder() -> None:
    """항목 금액 `[data-erp=\"price\"]`도 예약금과 동일한 천단위 쉼표 포맷을 적용한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpBindPriceInput(inputEl)" in text
    assert "function erpBindAllPriceInputs(scope)" in text
    assert "erpBindPriceInput(row.querySelector('[data-erp=\"price\"]'))" in text
    assert "erpBindAllPriceInputs(document.getElementById('erp-items'))" in text
    assert "const priceAmount = erpCoerceAmount(item.price)" in text
    assert "const price = priceAmount > 0 ? erpFormatDepositDisplay(priceAmount) : ''" in text

    product_item_js = (root / "static/js/foms/product-item.js").read_text(encoding="utf-8")
    assert "formatPriceSummaryDisplay" in product_item_js
    assert 'endsWith("원")' in product_item_js


def test_mobile_erp_item_form_preserves_complex_spec_text() -> None:
    """모바일 현장 입력은 복합 규격 원문을 spec으로 보존하고 보조 W/D/H는 유지한다."""
    root = Path(__file__).resolve().parents[2]
    shared_js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    product_item_js = (root / "static/js/foms/product-item.js").read_text(encoding="utf-8")

    # spec(원문)은 저장 시 W/D/H 행에서 파생 보존 — collect/conversion이 참조한다.
    assert 'data-erp="spec"' in shared_js
    # 구조화 W 입력 + 복합 폭 콤마 안내 + W*D*H 붙여넣기 자동 분해.
    assert 'data-erp="spec_width"' in shared_js
    assert "5700,4512,2300" in shared_js
    assert "bindSpecWidthPasteSplit" in shared_js

    collect_start = shared_js.index("function erpCollectStructured()")
    collect_end = shared_js.index("async function erpSaveStructured", collect_start)
    collect_block = shared_js[collect_start:collect_end]
    assert "const rawSpec = String(obj.spec || '').trim();" in collect_block
    assert "const rawSpecWasDerived = rawSpecEl?.dataset?.erpSpecDerived === '1';" in collect_block
    assert "obj.spec = rawSpec && !rawSpecWasDerived ? rawSpec : (specLines.join(', ') || rawSpec);" in collect_block
    assert "obj.spec = rawSpec;" in collect_block

    conversion_start = shared_js.index("function erpGenerateConversionText()")
    conversion_end = shared_js.index("function erpCopyToClipboard()", conversion_start)
    conversion_block = shared_js[conversion_start:conversion_end]
    assert "const rawSpec = getRowVal('spec');" in conversion_block
    assert "const spec = rawSpec || (specParts.length ? specParts.join(', ') : '');" in conversion_block

    assert "var rawSpecEl = row.querySelector('[data-erp=\"spec\"]');" in product_item_js
    assert 'target.dataset.erp === "spec"' in product_item_js


def test_common_mobile_attachments_select_upload_immediately() -> None:
    """공통 사진/동영상은 모바일에서 선택 즉시 업로드되도록 input change에 바인딩한다."""
    root = Path(__file__).resolve().parents[2]
    shared_js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    mobile_partial = (
        root / "templates" / "orders" / "partials" / "erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")

    assert 'class="visually-hidden"' in mobile_partial
    assert 'id="erp-attachments-gallery-input"' in mobile_partial
    assert "data-erp-common-attachment-gallery-trigger" in mobile_partial
    assert "사진/동영상 추가" in mobile_partial
    assert "erpOpenCommonAttachmentPicker(input)" in shared_js
    assert "input.setAttribute('multiple', '');" in shared_js
    assert "document.getElementById('erp-attachments-input')?.addEventListener('change'" in shared_js
    assert "document.getElementById('erp-attachments-gallery-input')?.addEventListener('change'" in shared_js
    assert "erpUploadSelectedAttachments(this);" in shared_js


def test_erp_amount_surfaces_read_modern_payment_deposit_and_stored_final() -> None:
    """대시보드/실측 상세 금액 표시도 ERP Order payment.deposit와 final totals를 우선 사용한다."""
    root = Path(__file__).resolve().parents[2]
    dashboard_js = (root / "static/js/orders/dashboard/erp-dashboard-detail-dom.js").read_text(encoding="utf-8")
    measurement_desktop = (
        root / "templates/measurement/partials/dashboard_main.html"
    ).read_text(encoding="utf-8")

    for source in (dashboard_js,):
        assert "coerceAmount((sd.payment || {}).deposit)" in source
        assert "coerceAmount((sd.payments || {}).deposit)" in source
        assert "coerceAmount(totals.deposit_amount)" in source
        assert "coerceAmount((sd.payment || {}).discount)" in source
        assert "coerceAmount((sd.totals || {}).discount_amount)" in source
        assert "coerceAmount(totals.items_total)" in source
        assert "s + coerceAmount(it.price)" in source
        assert "coerceAmount(totals.shipping_price)" in source
        assert "sumFreeInputFromText" in source
        assert "coerceAmount(totals.final_amount)" in source
        assert "itemsTotal + freeInputAmt - depositAmt - discountAmt" in source

    # 실측 데스크톱 상세는 ERP payment.deposit + final totals 우선 사용.
    # (모바일 v2 큐는 홈과 동일한 깔끔한 queue-card-v2로, 금액 표시는 상세 페이지의
    #  mobile_amount_summary로 이동했다 — 큐 카드에 인라인 금액을 두지 않는다.)
    for source in (measurement_desktop,):
        assert "rsd_payment.get('deposit') or rsd_payments.get('deposit', 0)" in source
        assert "rsd_payment.get('discount')" in source
        assert "rsd_items_total + rsd_free_input - rsd_deposit - rsd_discount" in source


def test_erp_dashboard_selected_orders_can_copy_to_new_order_number() -> None:
    """ERP 대시보드 선택 바는 선택 주문을 새 주문번호로 복사하는 API를 호출한다."""
    root = Path(__file__).resolve().parents[2]
    dashboard_grid = (
        root / "templates/orders/partials/dashboard_grid.html"
    ).read_text(encoding="utf-8")
    dashboard_js = (root / "static/js/orders/dashboard/erp-dashboard-detail-dom.js").read_text(encoding="utf-8")

    assert 'id="erp-grid-copy-selected"' in dashboard_grid
    assert "주문 건 복사" in dashboard_grid
    for source in (dashboard_js,):
        assert "function selectedOrderIds()" in source
        assert "fetch('/api/orders/copy'" in source
        assert "JSON.stringify({ order_ids: orderIds })" in source
        assert "?open=erp-order" in source


def test_edit_order_matched_estimate_card_uses_order_payment_payload() -> None:
    """편집 화면의 매칭된 견적 카드는 ERP 예약금 payload를 사용해 표시/차감한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "templates/orders/edit_order.html").read_text(encoding="utf-8")

    assert "const orderPayment = data.order_payment ||" in text
    assert "displayMatchedEstimates(data.estimates || [], orderPayment)" in text
    assert "function resolveMatchedEstimatePayment(orderPayment)" in text
    assert "label = '예약금(선금)';" in text
    assert "${escapeHtml(paymentLabel)}" in text
    assert "(최종 금액 - ${escapeHtml(paymentLabel)})" in text
    assert "unmatch-estimate-from-order-btn" in text
    assert "/api/wdcalculator/unmatch-order" in text


def test_attachment_preview_zoom_scoped_to_modal_not_mobile_form() -> None:
    """Preview zoom CSS must target the modal; the dialog sits outside .erp-order-mobile-form."""
    root = Path(__file__).resolve().parents[2]
    css_text = (root / "static/css/components/foms-form-field.css").read_text(encoding="utf-8")
    mobile_partial = (
        root / "templates" / "orders" / "partials" / "erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")
    edit_body = (
        root / "templates" / "orders" / "partials" / "edit_order_body.html"
    ).read_text(encoding="utf-8")
    detail_partial = (
        root / "templates" / "partials" / "shared" / "foms_attachment_preview_modal.html"
    ).read_text(encoding="utf-8")

    form_idx = mobile_partial.index("erp-order-mobile-form")
    include_idx = edit_body.index("foms_attachment_preview_modal.html")
    assert form_idx < len(mobile_partial)
    assert "foms_attachment_preview_modal.html" not in mobile_partial
    assert "foms_attachment_preview_modal.html" in edit_body

    assert "#erpAttachmentPreviewModal #erp-attachment-preview-body" in css_text
    assert "#erpAttachmentPreviewModal .erp-attachment-preview-zoom-stage" in css_text
    assert ".erp-order-mobile-form #erp-attachment-preview-body .erp-attachment-preview-img" not in css_text
    assert 'id="erpAttachmentPreviewModal"' in detail_partial
    assert 'id="erp-attachment-preview-body"' in detail_partial


def test_mobile_attachment_preview_uses_viewport_sized_modal() -> None:
    """Mobile attachment previews use the global-viewer visual model while keeping actions."""
    root = Path(__file__).resolve().parents[2]
    css_text = (root / "static/css/components/foms-form-field.css").read_text(encoding="utf-8")
    mobile_bundle = (root / "static/css/foundation/foms-mobile-surfaces.css").read_text(
        encoding="utf-8"
    )
    layout_head = (root / "templates/partials/shared/layout_head.html").read_text(
        encoding="utf-8"
    )

    assert "Mobile attachment preview: global-viewer style stage" in css_text
    assert "foms-global-preview-modal" in css_text
    assert "#erpAttachmentPreviewModal .modal-dialog" in css_text
    assert "#erpEstimatePreviewModal .modal-dialog" in css_text
    assert "width: 100vw;" in css_text
    assert "height: 100dvh;" in css_text
    assert "backdrop-filter: blur(14px) saturate(120%)" in css_text
    assert "#erpAttachmentPreviewModal .modal-header" in css_text
    assert "display: none;" in css_text
    assert "overflow: hidden;" in css_text
    assert "max-height: calc(100dvh - 5rem - env(safe-area-inset-bottom));" in css_text
    assert "position: absolute;" in css_text
    assert "background: rgba(15, 23, 42, 0.86);" in css_text
    assert "flex-wrap: nowrap;" in css_text
    assert "background-color: #fff;" in css_text
    assert (
        "#erpAttachmentPreviewModal "
        ".erp-attachment-preview-actions .btn"
    ) in css_text
    assert ".erp-order-mobile-form .erp-attachment-preview-actions .btn" not in css_text
    assert "max-width: min(92vw, 36rem)" not in css_text
    assert "../components/foms-form-field.css?v=20260821a" in mobile_bundle
    assert "foms-mobile-surfaces.css') }}?v=20260826a" in layout_head


def test_mobile_erp_autosize_textarea_overrides_80px_floor() -> None:
    """Main-form autosize textareas must not inherit .foms-textarea { min-height: 80px } on mobile."""
    root = Path(__file__).resolve().parents[2]
    css_text = (root / "static/css/components/foms-form-field.css").read_text(encoding="utf-8")
    assert ".foms-textarea {" in css_text
    assert "min-height: 80px" in css_text
    assert (
        "body.erp-mobile-v2-layout .erp-order-mobile-form .foms-textarea.erp-flex-textarea"
        in css_text
    )
    compact_idx = css_text.index(
        "body.erp-mobile-v2-layout .erp-order-mobile-form .foms-textarea.erp-flex-textarea"
    )
    compact_block = css_text[compact_idx : compact_idx + 1200]
    assert "--erp-mobile-input-h: 40px" in css_text
    assert "min-height: var(--erp-mobile-input-h)" in compact_block
    assert "resize: none" in compact_block


def test_pc_erp_order_tab_uses_input_not_textarea_for_single_line_fields() -> None:
    """PC erp_order_tab은 production과 동일하게 단일행 필드를 input으로 유지한다."""
    root = Path(__file__).resolve().parents[2]
    pc_tab = (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    assert 'input type="text" class="form-control form-control-sm" id="erp-customer-name"' in pc_tab
    assert 'input type="tel" class="form-control form-control-sm" id="erp-customer-phone"' in pc_tab
    assert 'data-erp="product_name" value=' in (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")


def test_mobile_autosize_skips_placeholder_scroll_height() -> None:
    """Empty textarea height must not inflate from long placeholder wrap."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "function erpResolveAutosizeMinHeight" in text
    assert "erpIsMobileFormContext()" in text
    assert "5700(2402+…)" in text
    mobile = (root / "templates/orders/partials/erp_order_tab_mobile.html").read_text(
        encoding="utf-8"
    )
    assert 'id="erp-construction-workers" rows="1"' in mobile
    assert 'data-erp-min-height="40"' in mobile


def test_attachment_preview_image_zoom_supports_in_modal_gestures() -> None:
    """Attachment preview binds transform zoom + pan (tap, wheel, pinch, drag) inside the modal."""
    root = Path(__file__).resolve().parents[2]
    shared_js = (root / "static/js/foms/attachment-preview-zoom.js").read_text(encoding="utf-8")
    erp_js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    mobile_js = (root / "static/js/foms/mobile-detail-attachments.js").read_text(encoding="utf-8")
    css_text = (root / "static/css/components/foms-form-field.css").read_text(encoding="utf-8")

    assert "function bindImageZoom(bodyEl, options)" in shared_js or "bindImageZoom" in shared_js
    assert "fomsResetAttachmentPreviewZoom" in shared_js
    assert "fomsBindAttachmentPreviewImageZoom" in shared_js
    assert "erp-attachment-preview-zoom-stage" in shared_js
    assert "translate(" in shared_js
    assert "translate3d(" not in shared_js
    assert '"wheel"' in shared_js
    assert "ev.touches.length === 2" in shared_js
    assert '"pointerdown"' in shared_js
    assert "clampPan" in shared_js
    assert "cursor: grab" in css_text
    assert "erp-attachment-preview-img--dragging" in css_text

    assert "function erpBindAttachmentPreviewImageZoom(bodyEl)" in erp_js
    assert "function erpApplyAttachmentPreviewZoom(img)" in erp_js
    assert "function erpResetAttachmentPreviewZoom(img)" in erp_js
    assert "fomsBindAttachmentPreviewImageZoom" in erp_js
    assert "fomsOpenLightboxUrl" not in erp_js
    assert "function erpReleaseAttachmentPreviewModalFocus(modalEl)" in erp_js
    assert "fomsBindAttachmentPreviewModalZoomReset" in erp_js
    assert "erpOpenAttachmentPreview(attachmentId)" in erp_js

    assert "data-foms-attachment-preview-gallery" in mobile_js
    assert "erpAttachmentPreviewModal" in mobile_js
    assert "fomsBindAttachmentPreviewImageZoom" in mobile_js


def test_mobile_detail_attach_grid_uses_modal_preview_not_lightbox() -> None:
    """Mobile order detail attach section opens the shared modal preview, not legacy lightbox."""
    root = Path(__file__).resolve().parents[2]
    partial = (
        root / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    page = (root / "templates/orders/mobile_order_detail.html").read_text(encoding="utf-8")

    assert "data-foms-attachment-preview-gallery" in partial
    assert "data-foms-attachment-preview" in partial
    assert "data-foms-attachment-view-url" in partial
    assert 'src="{{ att.view_url or att.thumb_url }}"' in partial
    assert "data-foms-lightbox-gallery" not in partial
    assert "foms_attachment_preview_modal.html" in partial
    assert "attachment-preview-zoom.js" in page
    assert "mobile-detail-attachments.js" in page
    assert "lightbox.js" not in page


def test_attachment_preview_modal_global_shared_partial_dedup() -> None:
    """Attachment preview modal markup lives only in foms_attachment_preview_modal.html."""
    root = Path(__file__).resolve().parents[2]
    shared = root / "templates/partials/shared/foms_attachment_preview_modal.html"
    consumers = [
        root / "templates/orders/add_order.html",
        root / "templates/orders/partials/edit_order_body.html",
        root / "templates/orders/partials/order_detail_mobile_v2.html",
        root / "templates/orders/partials/dashboard_modals.html",
        root / "templates/production/partials/modals.html",
        root / "templates/orders/object.html",
        root / "templates/construction/partials/modals.html",
        root / "templates/orders/wizard/wizard_shell.html",
    ]
    non_consumers = [
        root / "templates/orders/partials/erp_order_tab.html",
        root / "templates/orders/partials/erp_order_tab_mobile.html",
    ]
    shared_text = shared.read_text(encoding="utf-8")
    assert shared_text.count('id="erpAttachmentPreviewModal"') == 1
    for path in consumers:
        text = path.read_text(encoding="utf-8")
        assert "foms_attachment_preview_modal.html" in text
        assert 'id="erpAttachmentPreviewModal"' not in text
    for path in non_consumers:
        text = path.read_text(encoding="utf-8")
        assert "foms_attachment_preview_modal.html" not in text
        assert 'id="erpAttachmentPreviewModal"' not in text


def test_dashboard_attachment_preview_bridge_ssot() -> None:
    """Production/construction dashboards delegate legacy openAttachmentPreviewModal to shared SSOT."""
    root = Path(__file__).resolve().parents[2]
    bridge = (root / "static/js/foms/attachment-preview-modal-bridge.js").read_text(encoding="utf-8")
    open_js = (root / "static/js/foms/erp-attachment-preview-open.js").read_text(encoding="utf-8")
    prod_body = (root / "templates/production/partials/dashboard_body.html").read_text(encoding="utf-8")
    cons_body = (root / "templates/construction/partials/dashboard_body.html").read_text(encoding="utf-8")

    assert "window.fomsOpenErpAttachmentPreviewModal" in open_js
    assert "window.openAttachmentPreviewModal = openAttachmentPreviewModal" in bridge
    assert "fomsOpenAttachmentPreviewFromRecord" in bridge
    assert "attachment-preview-modal-bridge.js" in prod_body
    assert "attachment-preview-modal-bridge.js" in cons_body
    assert "function openAttachmentPreviewModal(" not in (
        root / "templates/production/partials/scripts.html"
    ).read_text(encoding="utf-8")
    assert "function openAttachmentPreviewModal(" not in (
        root / "templates/construction/partials/scripts.html"
    ).read_text(encoding="utf-8")


def test_wizard_uses_shared_attachment_preview_modal() -> None:
    root = Path(__file__).resolve().parents[2]
    shell = (root / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    wizard_js = (root / "static/js/foms/wizard-attachments.js").read_text(encoding="utf-8")

    assert "foms_attachment_preview_modal.html" in shell
    assert "wizardAttachmentPreviewModal" not in shell
    assert "fomsOpenErpAttachmentPreviewModal" in wizard_js
    assert "erp-attachment-preview-delete" in wizard_js


def test_edit_order_initial_mount_releases_surface_before_deferred_panels() -> None:
    """Initial edit-page paint should reveal the ERP pane before quest/attachment fetches finish."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    mount_start = text.index("function fomsMountErpOrderSurface()")
    ready_idx = text.index("_erpMarkSurfaceReady();", mount_start)
    yield_idx = text.index("await _erpYieldForFirstPaint();", ready_idx)
    structured_idx = text.index(
        "await erpLoadStructured(erpBootstrap || undefined, { deferAttachments: true });",
        yield_idx,
    )
    deferred_idx = text.index("_erpLoadDeferredSurfaceDecorations();", structured_idx)

    assert "function _erpYieldForFirstPaint()" in text
    assert "function _erpLoadDeferredSurfaceDecorations()" in text
    assert ready_idx < yield_idx < structured_idx < deferred_idx


def test_add_order_handler_accepts_only_canonical_erp_order_create_mode_contract() -> None:
    """The POST handler must no longer accept create_mode=ERP_BETA."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "foms/web/orders/listing.py").read_text(encoding="utf-8")
    assert "ERP_BETA" not in text
    assert "create_mode == 'ERP_ORDER'" in text


def test_add_order_handler_rejects_blank_erp_order_placeholders(erp_editor_client) -> None:
    """The legacy add-order POST path must not create placeholder ERP orders."""
    before_total = db_session.query(Order).count()
    before_placeholder = (
        db_session.query(Order)
        .filter(Order.customer_name == "ERP Order", Order.phone == "000-0000-0000")
        .count()
    )

    response = erp_editor_client.post(
        "/add",
        data={"create_mode": "ERP_ORDER"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "필수 항목을 입력해주세요" in response.get_data(as_text=True)
    assert db_session.query(Order).count() == before_total
    assert (
        db_session.query(Order)
        .filter(Order.customer_name == "ERP Order", Order.phone == "000-0000-0000")
        .count()
        == before_placeholder
    )


def test_erp_order_flag_helper_ignores_legacy_attr() -> None:
    """Canonical flag helpers should read only is_erp_order."""
    from types import SimpleNamespace

    from foms.services.erp_order_flags import is_erp_order_record

    assert is_erp_order_record(SimpleNamespace(is_erp_order=True)) is True
    assert is_erp_order_record(SimpleNamespace(is_erp_order=False, is_erp_beta=True)) is False


def test_erp_blueprint_exports_only_canonical_debug_flag() -> None:
    """The ERP blueprint module should not expose ERP_BETA_DEBUG anymore."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "foms/platform/erp_blueprint.py").read_text(encoding="utf-8")
    assert "ERP_BETA_DEBUG" not in text
    assert "ERP_ORDER_DEBUG" in text


def test_edit_order_page_renders_thin_erp_order_partial_contract(erp_editor_client) -> None:
    order = _create_erp_order()

    response = erp_editor_client.get(f"/edit/{order.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    erp_order_shared_tag_idx = body.index("js/orders/erp-order-shared.js")
    config_idx = body.index('id="erp-order-config"')
    draft_mode_idx = body.index("window.__ERP_ORDER_DRAFT_MODE = false;")

    assert config_idx < payment_urls_idx < erp_order_shared_tag_idx < draft_mode_idx
    _assert_shared_form_script_contract(body)
    assert f'data-order-id="{order.id}"' in body
    assert 'data-erp-order-enabled="true"' in body
    assert 'data-erp-surface="1" data-erp-ready="1"' in body


def test_shared_erp_order_js_gates_channel_push_on_unsaved_changes() -> None:
    """미저장/draft 상태로 채널톡 푸시 시 먼저 저장(승격)을 통과해야 한다.

    사고 재현(주문 4414): 푸시 본문이 미저장 라이브 DOM에서 조립되어 채널톡엔
    나갔지만 DB엔 저장되지 않았다. isDirty()거나 아직 승격 안 된 draft 주문이면
    erpSaveStructured를 먼저 호출하고, 변환 텍스트 조립(erpGenerateConversionText)
    보다 앞서야 한다. 저장 여부를 사용자에게 되묻는 confirm은 두지 않는다
    (저장 후 다시 들어와야 푸시되던 동선 제거).
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    push_start = text.index(
        "async function erpRunChannelPush(btn, pushKind, resendRetryState)"
    )
    push_end = text.index("initErpMainDatePickers();", push_start)
    push_block = text[push_start:push_end]

    gate_idx = push_block.index("fomsErpAutosave")
    assert "isDirty()" in push_block
    assert "erpSaveStructured({ redirect: false })" in push_block
    gen_text_idx = push_block.index("erpGenerateConversionText()")
    assert gate_idx < gen_text_idx

    # 재귀(resend note) 호출은 이미 저장을 마쳤으므로 다시 저장하지 않는다.
    assert "if (!resendRetryState) {" in push_block
    assert "저장되지 않은 변경이 있습니다" in push_block
    # 저장 여부 confirm 금지 — draft/미저장이면 자동 저장 후 그대로 푸시한다.
    assert "저장한 뒤 푸시할까요" not in push_block
    assert "erpIsDraftBackedOrder()" in push_block


def test_shared_erp_order_js_regional_type_gate_alerts_without_scroll_jump() -> None:
    """지방주문 구분 미선택 저장은 alert 검증에 걸리고, 스크롤 점프를 만들지 않는다.

    사고 재현: 지방주문 체크 + 구분 미선택 상태의 저장이 alert 없이 맨 .focus()로
    뷰포트를 폼 상단으로 튕겨 "저장 누르면 스크롤만 올라가고 저장이 안 된다"로
    보였다(안내 문구는 하단 erp-status-text에 남아 사용자가 못 봄). 구분 누락은
    필수값 alert 목록에 포함되고, 모든 포커스 이동은 erpFocusWithoutScroll이어야 한다.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    once_start = text.index("async function erpSaveStructuredOnce(opts = {})")
    once_end = text.index("document.addEventListener('DOMContentLoaded'", once_start)
    once_block = text[once_start:once_end]

    # 사용자 저장 검증(alert)에 지방주문 구분 포함
    validation_start = once_block.index("if (opts._skipValidation !== true) {")
    validation_end = once_block.index("if (_paymentTogglePending)", validation_start)
    validation_block = once_block[validation_start:validation_end]
    assert "missing.push('지방주문 구분 (하우드/협력사)')" in validation_block
    assert (
        "erpFocusWithoutScroll(document.getElementById('erp-regional-construction-type'))"
        in validation_block
    )

    # 잔여 방어선(_skipValidation 경로)도 스크롤 유발 맨 .focus() 금지
    assert (
        "document.getElementById('erp-regional-construction-type')?.focus()"
        not in text
    )


def test_shared_erp_order_js_save_redirect_focuses_saved_row() -> None:
    """저장 복귀는 focus_order 딥링크로 방금 저장한 행에 정렬된다.

    사고 재현: 저장 성공 후 대시보드 복귀가 fresh load/reload 라
    그리드(erp-grid-scroll-wrap) 스크롤이 0으로 초기화 — 사용자에겐
    "저장 누르면 스크롤 업"으로 보였다. px 복원 대신 focus_order 파라미터를
    붙여 기존 딥링크(스크롤+하이라이트)가 행 기준으로 복귀시킨다.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpAppendFocusOrderParam(targetUrl, orderId)" in text
    helper_start = text.index("function erpAppendFocusOrderParam(targetUrl, orderId)")
    helper_end = text.index("function erpNavigateAfterStructuredSave(targetUrl)", helper_start)
    helper_block = text[helper_start:helper_end]
    # 소비자 배선된 복귀처(주문·실측 대시보드)에만 부여 — 그 외는 원본 URL 유지
    assert "u.pathname !== '/erp/dashboard' && u.pathname !== '/erp/measurement'" in helper_block
    assert "u.searchParams.set('focus_order', String(orderId))" in helper_block

    # 성공 리다이렉트 양 분기 모두 helper 를 통과한다
    assert "window.location.href = erpAppendFocusOrderParam('/erp/dashboard', targetId);" in text
    assert "erpNavigateAfterStructuredSave(erpAppendFocusOrderParam(targetUrl, targetId));" in text

    # 소비자(대시보드 focus_order 딥링크) 계약 유지
    dash = (root / "static/js/orders/dashboard/erp-dashboard-detail-dom.js").read_text(encoding="utf-8")
    assert "urlParams.get('focus_order')" in dash
    assert "scrollIntoView" in dash


def test_measurement_dashboard_consumes_focus_order_deeplink() -> None:
    """실측 대시보드도 focus_order 딥링크를 소비한다(저장 복귀 행 정렬).

    사고 재현(운영 4655 장상진): 실측 대시보드에서 편집 진입 → 저장 → 복귀 시
    today 자동 스크롤이 작업 위치를 덮어 "저장 안 되고 위로 튕김"으로 보였다.
    소비자는 today 스크롤 뒤에 실행돼 우선하고, 숫자 id만 허용한다.
    """
    root = Path(__file__).resolve().parents[2]
    dash = (root / "static/js/measurement/dashboard.js").read_text(encoding="utf-8")

    idx_today = dash.index("todayEl.scrollIntoView")
    idx_focus = dash.index("focus_order")
    assert idx_today < idx_focus  # today 스크롤보다 뒤 = 우선권
    assert "/^\d+$/.test(focusOrder)" in dash
    assert "tr.scrollIntoView({ block: 'center' })" in dash

    # 헬퍼가 실측 복귀 URL에 focus_order 를 부여한다
    shared = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "u.pathname !== '/erp/dashboard' && u.pathname !== '/erp/measurement'" in shared


def test_save_button_does_not_steal_focus_on_mouse_pointerdown() -> None:
    """저장 버튼 mousedown 이 입력 포커스를 뺏지 않는다(첫 클릭 무산 사고 방지).

    사고 재현(운영 4660 양선민 외 다수): 텍스트 입력(한글 IME)에 포커스를 둔 채
    아래로 스크롤해 저장을 누르면 mousedown→blur→IME 커밋의 네이티브 캐럿
    스크롤(부트스트랩 :root smooth)로 버튼이 커서 밑에서 이동, click 이 무산돼
    "저장 누르면 스크롤만 올라가고 저장 안 됨(재클릭은 됨)"이 됐다. 마우스
    pointerdown 은 preventDefault 로 포커스 이동을 차단하고, 터치는 click 합성
    억제 부작용이 있어 제외한다.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    idx_pd = text.index("addEventListener('pointerdown'", text.index("document.getElementById('erp-save-btn')"))
    idx_click = text.index("addEventListener('click', erpSaveStructured)")
    assert idx_pd < idx_click  # pointerdown 가드가 click 배선보다 먼저
    guard_block = text[idx_pd:idx_pd + 200]
    assert "e.pointerType === 'mouse'" in guard_block
    assert "e.preventDefault()" in guard_block


def test_site_address_join_guards_against_duplicated_detail():
    """주소 합치기는 full 이 이미 상세주소로 끝나면 다시 붙이지 않는다 (ADDR-DUP-01).

    외부 수집분·옛 문서에는 ``address_full`` 이 상세주소를 품은 채 ``address_detail`` 도
    남아 있는 행이 있다. 편집 폼은 로드 시 둘을 한 칸에 합쳐 보여주고 저장 시 그 문자열을
    주소로 굳히므로, 무방비로 이어 붙이면 같은 동·호수가 두 번 들어간 주소가 저장된다
    (2026-08-14 운영 실측: ``… 103동 605호 103동 605호``). JS 테스트 러너가 없어 소스 계약으로 고정한다.
    """
    root = Path(__file__).resolve().parents[2]
    source = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpJoinSiteAddress(" in source
    assert "base.endsWith(extra) ? base" in source
    # 편집 폼 로드가 그 함수를 거치는지(무방비 결합이 남아 있지 않은지) 함께 고정한다.
    assert "erpJoinSiteAddress(addressFull, addressDetail)" in source
    assert "`${addressFull} ${addressDetail}`" not in source


def test_measurement_panel_polling_pauses_while_hidden_and_stops_when_gone() -> None:
    """실측 미러링 패널 30초 폴링은 **보일 때만** 돌고, 패널이 사라지면 타이머를 접는다.

    이 API 는 호출 1회가 서버 수백 ms 다(2026-09-01 실측 263ms). 숨겨진 탭에서 계속
    돌면 사용자는 아무것도 못 보면서 서버만 먹는다 — 열린 탭 수만큼 곱해진다.
    복귀 시 1회 갱신이 없으면 최대 30초 낡은 값을 보여주므로 그 짝도 함께 고정한다.
    """
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "window.__fomsErpMeasurementIntervalId = window.setInterval(function () {" in js, (
        "폴링이 무조건 loadMeasurementPanel 을 부르는 옛 형태로 돌아갔다"
    )
    assert "if (document.visibilityState === 'hidden') return;" in js, "숨김 상태 건너뛰기가 없다"
    assert "window.clearInterval(window.__fomsErpMeasurementIntervalId);" in js, (
        "패널이 사라져도 타이머가 남는다"
    )
    assert "window.__FOMS_ERP_MEASUREMENT_VISIBILITY_BOUND" in js, (
        "visibilitychange 리스너 단일 등록 가드가 없다(프래그먼트 스왑마다 누적)"
    )
    assert "document.addEventListener('visibilitychange', function () {" in js, (
        "복귀 시 갱신 경로가 없다"
    )
