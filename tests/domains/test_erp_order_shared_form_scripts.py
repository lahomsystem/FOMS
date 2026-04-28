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
    html2canvas_idx = body.index("html2canvas.min.js")
    estimate_preview_idx = body.index("js/orders/estimate-preview.js")

    assert payment_urls_idx < erp_order_shared_idx < html2canvas_idx < estimate_preview_idx

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
    assert "openTarget === 'erp-order'" in body
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


def test_estimate_preview_js_is_canonical_only() -> None:
    """P2 removes ERP_BETA_* fallbacks from the estimate preview runtime."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/estimate-preview.js").read_text(encoding="utf-8")
    start = text.index("function _isErpEnabled()")
    end = text.index("function _fmtMoney", start)
    block = text[start:end]
    assert "ERP_ORDER_ENABLED" in block
    assert "ERP_BETA_ENABLED" not in block


def test_shared_erp_order_js_has_no_beta_runtime_mirror() -> None:
    """The shared ERP runtime no longer exports beta globals or beta data-* fallbacks."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "window.ERP_BETA_ENABLED" not in text
    assert "__ERP_BETA_DRAFT_MODE" not in text
    assert "data-erp-beta-enabled" not in text
    assert "data-erp-beta-draft-mode" not in text


def test_shared_erp_order_js_blocks_non_save_actions_from_creating_drafts() -> None:
    """Only explicit save may create/finalize an ERP draft row."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpRequireFinalizedOrderForAction(actionText)" in text
    assert "window.erpIsDraftBackedOrder = erpIsDraftBackedOrder;" in text

    payment_start = text.index("window.erpTogglePayment = async function")
    payment_end = text.index("// ERP Order: 발주사 드롭다운", payment_start)
    payment_block = text[payment_start:payment_end]
    assert "erpRequireOrderIdOrWarn('결제:')" not in payment_block
    assert "erpRequireFinalizedOrderForAction('결제 확인은')" in payment_block

    item_upload_start = text.index("async function erpUploadItemAttachments")
    item_upload_end = text.index("function erpRenderItemAttachmentPanels", item_upload_start)
    item_upload_block = text[item_upload_start:item_upload_end]
    assert "erpRequireOrderIdOrWarn('제품 이미지 업로드:')" not in item_upload_block
    assert "erpRequireFinalizedOrderForAction('제품 이미지 업로드는')" in item_upload_block

    common_upload_start = text.index("async function erpUploadSelectedAttachments")
    common_upload_end = text.index("function erpGenerateConversionText", common_upload_start)
    common_upload_block = text[common_upload_start:common_upload_end]
    assert "erpRequireOrderIdOrWarn('첨부 업로드:')" not in common_upload_block
    assert "erpRequireFinalizedOrderForAction('첨부 업로드는')" in common_upload_block


def test_shared_erp_order_js_persists_deposit_adjusted_final_totals() -> None:
    """ERP Order 저장/변환은 예약금 차감 후 잔금을 canonical final amount로 유지한다."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert "function erpBuildTotals(itemsTotal, depositAmount)" in text
    assert "final_amount: balance" in text

    collect_start = text.index("function erpCollectStructured()")
    collect_end = text.index("async function erpSaveStructured", collect_start)
    collect_block = text[collect_start:collect_end]
    assert "const totals = erpBuildTotals(itemsTotal, depositAmount);" in collect_block
    assert "totals," in collect_block
    assert "deposit: totals.deposit_amount" in collect_block

    conversion_start = text.index("function erpGenerateConversionText()")
    conversion_end = text.index("function erpCopyToClipboard()", conversion_start)
    conversion_block = text[conversion_start:conversion_end]
    assert "const balanceText = erpFormatMoneyKRW(Math.max(0, erpCoerceAmount(totalText) - depositAmount));" in conversion_block
    assert "text += `잔금 : ${balanceText}`;" in conversion_block


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
    measurement_mobile = (
        root / "templates/measurement/partials/mobile_list.html"
    ).read_text(encoding="utf-8")

    for source in (dashboard_js, dashboard_template):
        assert "coerceAmount((sd.payment || {}).deposit)" in source
        assert "coerceAmount((sd.payments || {}).deposit)" in source
        assert "totals.final_amount == null ? totals.balance_amount : totals.final_amount" in source

    for source in (measurement_desktop, measurement_mobile):
        assert "rsd_payment.get('deposit') or rsd_payments.get('deposit', 0)" in source
        assert "rsd_totals.get('final_amount')" in source
        assert "rsd_totals.get('balance_amount')" in source


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
