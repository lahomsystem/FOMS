"""P0-05: Photo capture (C12) template and script contracts."""

from pathlib import Path

import pytest

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def erp_editor_client(client):
    """Login a user that can open ERP Order edit pages."""
    user = User(
        username="photo_cap_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Photo Cap Admin",
    )
    db_session.add(user)
    db_session.commit()
    client.post(
        "/login",
        data={"username": "photo_cap_admin", "password": "admin"},
        follow_redirects=True,
    )
    return client


def test_photo_capture_js_exports_helpers() -> None:
    text = (ROOT / "static/js/foms/photo-capture.js").read_text(encoding="utf-8")
    assert 'capture="environment"' in text
    # opt-out 계약: data-foms-no-capture input은 카메라 강제에서 제외(iOS 갤러리 허용).
    assert "data-foms-no-capture" in text
    assert "data-foms-photo-capture" in text
    assert "global.erpAppendAsReceiveFiles" in text
    # FileList를 그대로 concat하면 [FileList]가 되어 DataTransfer.items.add가 TypeError를 낸다.
    assert "const selectedFiles = Array.from(galleryInput.files);" in text
    assert "global.erpAppendAsReceiveFiles(selectedFiles);" in text
    assert "initAsReceiveModalFocus" in text


def test_erp_order_shared_exports_as_receive_append() -> None:
    text = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "window.erpAppendAsReceiveFiles = erpAppendAsReceiveFiles;" in text
    # 항목 첨부 input은 iOS 갤러리 선택을 위해 카메라 강제(capture)를 제거하고 opt-out 표식을 단다.
    assert "data-foms-no-capture" in text
    assert 'erp-item-attachments-input" accept="${itemAttachmentAccept}" capture' not in text


def test_layout_includes_photo_capture_assets() -> None:
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )
    assert "css/foms/photo-capture.css" in head
    assert "js/foms/photo-capture.js') }}?v=20260810a" in scripts


def test_erp_order_tab_as_modal_camera_first_markup(erp_editor_client) -> None:
    order = Order(
        received_date="2026-05-29",
        customer_name="Photo Capture Contract",
        phone="010-9999-8888",
        address="Seoul",
        product="Kitchen",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()

    response = erp_editor_client.get(f"/edit/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert 'data-foms-photo-capture' in body
    assert 'data-target-input="as-receive-files"' in body
    assert 'data-action="camera"' in body
    assert 'id="as-receive-files"' in body
    assert 'capture="environment"' in body
    assert 'data-erp-attachment-paste-zone="as-receive"' in body
    assert "카메라로 촬영" in body
    # 공통 첨부(일반 업로드) input은 iOS 갤러리 선택을 위해 카메라 강제에서 제외.
    common_input_start = body.index('id="erp-attachments-input"')
    common_input_end = body.index(">", common_input_start)
    common_input = body[common_input_start:common_input_end]
    assert "data-foms-no-capture" in common_input
    assert "capture=" not in common_input


def test_edit_order_blueprint_input_has_capture(erp_editor_client) -> None:
    """Non-ERP edit page renders the blueprint tab (ERP orders hide it via is_erp_order)."""
    order = Order(
        received_date="2026-05-29",
        customer_name="Blueprint Capture",
        phone="010-7777-6666",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        is_erp_order=False,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()

    response = erp_editor_client.get(f"/edit/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="blueprint-file-input"' in body
    assert body.index('id="blueprint-file-input"') < body.index(
        'capture="environment"', body.index('id="blueprint-file-input"')
    )
