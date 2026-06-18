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
    erp_order_shared_idx = body.index("js/orders/erp-order-shared.js")
    estimate_preview_idx = body.index("js/orders/estimate-preview.js")
    estimate_columns_idx = body.index("js/orders/estimate-table-columns.js")
    column_resizer_idx = body.index("js/runtime/column-resizer.js")

    assert payment_urls_idx < erp_order_shared_idx < column_resizer_idx < estimate_preview_idx < estimate_columns_idx
    assert "html2canvas.min.js" not in body

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
    """Edit surface keeps only the canonical ?open=erp-order branch."""
    order = _create_erp_order()
    response = erp_editor_client.get(f"/edit/{order.id}?open=erp-order")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "openTarget !== 'erp-order'" in body
    assert "bootstrap.Tab.getOrCreateInstance(btn).show()" in body
    assert "erp-beta" not in body


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
    assert 'erp-est-viewport' in pane
    assert 'erp-est-export-clone' in pane
    assert 'id="est-mobile-preview"' in pane
    assert 'id="erpEstimatePreviewModal"' in pane
    assert 'id="erp-estimate-preview-body"' in pane
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
    assert "_bindEstimateMobilePreview" in text
    assert "_openEstimatePreviewModal" in text
    assert "fomsBindAttachmentPreviewImageZoom" in text


def test_shared_erp_order_js_has_no_beta_runtime_mirror() -> None:
    """The shared ERP runtime no longer exports beta globals or beta data-* fallbacks."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "window.ERP_BETA_ENABLED" not in text
    assert "__ERP_BETA_DRAFT_MODE" not in text
    assert "data-erp-beta-enabled" not in text
    assert "data-erp-beta-draft-mode" not in text


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
    assert "erpSaveStructured(" not in push_block
    assert "erpCanUsePersistedOrderAction('푸쉬는')" in push_block


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
    assert "erpNavigateAfterStructuredSave(targetUrl);" in text
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
    assert "window.syncWorkflowStageByMeasurementDate = syncWorkflowStageByMeasurementDate;" in sync_block
    assert "onChange: function ()" in text
    assert "syncWorkflowStageByMeasurementDate();" in text
    assert "mEl.addEventListener('change', syncWorkflowStageByMeasurementDate);" in text
    assert "mEl.addEventListener('input', syncWorkflowStageByMeasurementDate);" in text


def test_shared_erp_order_js_persists_deposit_adjusted_final_totals() -> None:
    """ERP Order 저장은 잔금을 canonical final amount로 유지하되 변환 텍스트에는 잔금 라인을 내보내지 않는다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpBuildTotals(itemsTotal, depositAmount, discountAmount)" in text
    assert "discount_amount: discount" in text
    assert "final_amount: balance" in text

    collect_start = text.index("function erpCollectStructured()")
    collect_end = text.index("async function erpSaveStructured", collect_start)
    collect_block = text[collect_start:collect_end]
    assert "const totals = erpBuildTotals(itemsTotal, depositAmount, discountAmount);" in collect_block
    assert "totals," in collect_block
    assert "deposit: totals.deposit_amount" in collect_block
    assert "discount: totals.discount_amount" in collect_block

    conversion_start = text.index("function erpGenerateConversionText()")
    conversion_end = text.index("function erpCopyToClipboard()", conversion_start)
    conversion_block = text[conversion_start:conversion_end]
    assert "text += `예약금 : ${erpFormatMoneyKRW(depositAmount)}`;" in conversion_block
    assert "text += `잔금 :" not in conversion_block


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
    assert "사진/동영상 추가" in mobile_partial
    assert "input.click();" in shared_js
    assert "document.getElementById('erp-attachments-input')?.addEventListener('change'" in shared_js


def test_erp_amount_surfaces_read_modern_payment_deposit_and_stored_final() -> None:
    """대시보드/실측 상세 금액 표시도 ERP Order payment.deposit와 final totals를 우선 사용한다."""
    root = Path(__file__).resolve().parents[2]
    dashboard_js = (root / "static/js/orders/dashboard/erp-dashboard-detail-dom.js").read_text(encoding="utf-8")
    dashboard_template = (
        root / "templates/orders/partials/dashboard_scripts_detail_dom.html"
    ).read_text(encoding="utf-8")
    measurement_desktop = (
        root / "templates/measurement/partials/dashboard_main.html"
    ).read_text(encoding="utf-8")

    for source in (dashboard_js, dashboard_template):
        assert "coerceAmount((sd.payment || {}).deposit)" in source
        assert "coerceAmount((sd.payments || {}).deposit)" in source
        assert "coerceAmount((sd.payment || {}).discount)" in source
        assert "coerceAmount((sd.totals || {}).discount_amount)" in source
        assert "Math.max(0, itemsTotal - depositAmt - discountAmt)" in source

    # 실측 데스크톱 상세는 ERP payment.deposit + final totals 우선 사용.
    # (모바일 v2 큐는 홈과 동일한 깔끔한 queue-card-v2로, 금액 표시는 상세 페이지의
    #  mobile_amount_summary로 이동했다 — 큐 카드에 인라인 금액을 두지 않는다.)
    for source in (measurement_desktop,):
        assert "rsd_payment.get('deposit') or rsd_payments.get('deposit', 0)" in source
        assert "rsd_payment.get('discount')" in source
        assert "rsd_items_total - rsd_deposit - rsd_discount" in source


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
    """Mobile attachment previews need the full phone viewport, not a compact frame."""
    root = Path(__file__).resolve().parents[2]
    css_text = (root / "static/css/components/foms-form-field.css").read_text(encoding="utf-8")
    mobile_bundle = (root / "static/css/foundation/foms-mobile-surfaces.css").read_text(
        encoding="utf-8"
    )
    layout_head = (root / "templates/partials/shared/layout_head.html").read_text(
        encoding="utf-8"
    )

    assert "Mobile attachment preview: use the phone viewport" in css_text
    assert "#erpAttachmentPreviewModal .modal-dialog" in css_text
    assert "width: 100vw;" in css_text
    assert "height: 100dvh;" in css_text
    assert "overflow: hidden;" in css_text
    assert "max-height: calc(100dvh - 8.75rem);" in css_text
    assert (
        "body.erp-mobile-v2-layout #erpAttachmentPreviewModal "
        ".erp-attachment-preview-actions .btn"
    ) in css_text
    assert ".erp-order-mobile-form .erp-attachment-preview-actions .btn" not in css_text
    assert "max-width: min(92vw, 36rem)" not in css_text
    assert "../components/foms-form-field.css?v=20260617a" in mobile_bundle
    assert "foms-mobile-surfaces.css') }}?v=20260617b" in layout_head


def test_attachment_preview_image_zoom_supports_in_modal_gestures() -> None:
    """Attachment preview binds transform zoom (tap, wheel, pinch) inside the modal."""
    root = Path(__file__).resolve().parents[2]
    shared_js = (root / "static/js/foms/attachment-preview-zoom.js").read_text(encoding="utf-8")
    erp_js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    mobile_js = (root / "static/js/foms/mobile-detail-attachments.js").read_text(encoding="utf-8")

    assert "function bindImageZoom(bodyEl, options)" in shared_js or "bindImageZoom" in shared_js
    assert "fomsResetAttachmentPreviewZoom" in shared_js
    assert "fomsBindAttachmentPreviewImageZoom" in shared_js
    assert "erp-attachment-preview-zoom-stage" in shared_js
    assert "translate3d(" in shared_js
    assert '"wheel"' in shared_js
    assert "ev.touches.length === 2" in shared_js

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
