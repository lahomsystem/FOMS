"""Static contracts for the ERP order detail two-phase rendering follow-up."""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_INCLUDE = _REPO_ROOT / "templates" / "orders" / "partials" / "dashboard_scripts.html"
_DETAIL_DOM = _REPO_ROOT / "templates" / "orders" / "partials" / "dashboard_scripts_detail_dom.html"
_FRAGMENT = _REPO_ROOT / "static" / "js" / "erp" / "order-detail-fragment.js"
_CONTRACT_DOC = _REPO_ROOT / "docs" / "harness" / "policy" / "order-detail-2phase-contract.md"
_PRODUCTION_BODY = _REPO_ROOT / "templates" / "production" / "partials" / "dashboard_body.html"
_CONSTRUCTION_BODY = _REPO_ROOT / "templates" / "construction" / "partials" / "dashboard_body.html"
_PRODUCTION_SCRIPTS = _REPO_ROOT / "templates" / "production" / "partials" / "scripts.html"
_CONSTRUCTION_SCRIPTS = _REPO_ROOT / "templates" / "construction" / "partials" / "scripts.html"


def test_dashboard_scripts_load_fragment_module_before_detail_dom() -> None:
    text = _SCRIPTS_INCLUDE.read_text(encoding="utf-8")

    fragment_idx = text.index("js/erp/order-detail-fragment.js")
    detail_dom_idx = text.index("dashboard_scripts_detail_dom.html")

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


def test_detail_dom_keeps_phase2_accessibility_and_perf_contracts() -> None:
    text = _DETAIL_DOM.read_text(encoding="utf-8")

    assert "performance.mark('erp-detail-load-start:' + orderId)" in text
    assert "performance.mark('erp-detail-shell:' + orderId)" in text
    assert "order-detail-attach-loading" in text
    assert "dw-attach-panel--loading" in text
    assert "visually-hidden" in text
    assert "mention users/list fetch 실패:" in text
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

    assert "js/erp/order-detail-fragment.js" in production_body
    assert "js/erp/order-detail-fragment.js" in construction_body


def test_production_and_construction_scripts_use_two_phase_attachment_patch() -> None:
    production_src = _PRODUCTION_SCRIPTS.read_text(encoding="utf-8")
    construction_src = _CONSTRUCTION_SCRIPTS.read_text(encoding="utf-8")

    assert "patchProductionDetailAttachments" in production_src
    assert "attachmentsPending = true" in production_src
    assert "order-detail-attachments-slot-" in production_src
    assert "container.dataset.shellLoaded = '1'" in production_src

    assert "patchConstructionDetailAttachments" in construction_src
    assert "attachmentsPending = true" in construction_src
    assert "order-detail-attachments-slot-" in construction_src
    assert "container.dataset.shellLoaded = '1'" in construction_src
