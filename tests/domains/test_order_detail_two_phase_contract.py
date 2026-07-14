"""Static contracts for the ERP order detail two-phase rendering follow-up."""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORDERS_CORE = _REPO_ROOT / "static" / "js" / "orders" / "dashboard" / "erp-dashboard-core.js"
_ORDERS_ATTACHMENTS = _REPO_ROOT / "static" / "js" / "orders" / "dashboard" / "erp-dashboard-attachments.js"
_DETAIL_DOM = _REPO_ROOT / "static" / "js" / "orders" / "dashboard" / "erp-dashboard-detail-dom.js"
_FRAGMENT = _REPO_ROOT / "static" / "js" / "orders" / "order-detail-fragment.js"
_CONTRACT_DOC = _REPO_ROOT / "docs" / "harness" / "policy" / "order-detail-2phase-contract.md"
_PRODUCTION_BODY = _REPO_ROOT / "templates" / "production" / "partials" / "dashboard_body.html"
_CONSTRUCTION_BODY = _REPO_ROOT / "templates" / "construction" / "partials" / "dashboard_body.html"
_PRODUCTION_SCRIPTS = _REPO_ROOT / "templates" / "production" / "partials" / "scripts.html"
_CONSTRUCTION_SCRIPTS = _REPO_ROOT / "templates" / "construction" / "partials" / "scripts.html"


def test_dashboard_scripts_load_fragment_module_before_detail_dom() -> None:
    # 라이브 로드 순서는 인라인 partial 이 아니라 erp-dashboard-entry.js CHAIN 이 강제한다:
    # order-detail-fragment.js(헬퍼) 가 erp-dashboard-detail-dom.js(소비자) 보다 먼저.
    text = (_REPO_ROOT / "static" / "js" / "orders" / "erp-dashboard-entry.js").read_text(
        encoding="utf-8"
    )

    fragment_idx = text.index("js/orders/order-detail-fragment.js")
    detail_dom_idx = text.index("dashboard/erp-dashboard-detail-dom.js")

    assert fragment_idx < detail_dom_idx


def test_fragment_module_owns_attachment_patch_helpers() -> None:
    fragment_src = _FRAGMENT.read_text(encoding="utf-8")
    detail_src = _DETAIL_DOM.read_text(encoding="utf-8")

    for fn_name in (
        "parseAttachmentsPayload",
        "orderDetailIsImageFile",
        "sanitizeAttachmentUrl",
        "buildDwAttachPanelHtml",
        "buildMainAttachThumbsHtml",
        "registerOrderDetailDrawingViewerGroups",
    ):
        assert f"function {fn_name}" in fragment_src
        assert f"function {fn_name}" not in detail_src

    assert "async function patchOrderDetailAttachments" in fragment_src
    assert "async function patchOrderDetailAttachments" not in detail_src
    assert "function invalidateOrderDetailRuntimeState" in fragment_src


def test_orders_invalidate_helper_matches_documented_contract() -> None:
    orders_core = _ORDERS_CORE.read_text(encoding="utf-8")
    orders_attachments = _ORDERS_ATTACHMENTS.read_text(encoding="utf-8")

    assert "window.invalidateOrderDetailRuntimeState(orderId" in orders_core
    assert "loadGen: __orderDetailLoadGen" in orders_core
    assert "delete c.dataset.itemCount;" in orders_core
    assert "__attachmentsCacheAt[orderId] = Date.now();" in orders_attachments


def test_detail_dom_keeps_phase2_accessibility_and_perf_contracts() -> None:
    text = _DETAIL_DOM.read_text(encoding="utf-8")

    assert "performance.mark('erp-detail-load-start:' + orderId)" in text
    assert "performance.mark('erp-detail-shell:' + orderId)" in text
    assert "order-detail-attach-loading" in text
    assert "dw-attach-panel--loading" in text
    assert "visually-hidden" in text
    assert "mention urgent-targets fetch 실패:" in text
    assert "const isImageFile = (a) =>" not in text
    assert '<div class="text-warning small">상세 정보를 불러올 수 없습니다.' not in text
    assert "text-warning small\">첨부를 불러오지 못했습니다." not in text


def test_order_detail_two_phase_contract_doc_exists() -> None:
    text = _CONTRACT_DOC.read_text(encoding="utf-8")

    assert "# loadOrderDetail 계약" in text
    assert "await loadOrderDetail(orderId)" in text
    assert "window.invalidateOrderDetailAttachments(orderId)" in text


def test_production_and_construction_load_common_fragment_module() -> None:
    production_body = _PRODUCTION_BODY.read_text(encoding="utf-8")
    construction_body = _CONSTRUCTION_BODY.read_text(encoding="utf-8")

    assert "js/orders/order-detail-fragment.js" in production_body
    assert "js/orders/order-detail-fragment.js" in construction_body


def test_production_and_construction_scripts_use_two_phase_attachment_patch() -> None:
    production_src = _PRODUCTION_SCRIPTS.read_text(encoding="utf-8")
    construction_src = _CONSTRUCTION_SCRIPTS.read_text(encoding="utf-8")

    assert "patchProductionDetailAttachments" in production_src
    assert "invalidateProductionOrderDetailAttachments" in production_src
    assert "attachmentsPending = true" in production_src
    assert "order-detail-attachments-slot-" in production_src
    assert "container.dataset.shellLoaded = '1'" in production_src
    assert "__attachmentsCacheAt[orderId] = Date.now();" in production_src

    assert "patchConstructionDetailAttachments" in construction_src
    assert "invalidateConstructionOrderDetailAttachments" in construction_src
    assert "attachmentsPending = true" in construction_src
    assert "order-detail-attachments-slot-" in construction_src
    assert "container.dataset.shellLoaded = '1'" in construction_src
    assert "__attachmentsCacheAt[orderId] = Date.now();" in construction_src
