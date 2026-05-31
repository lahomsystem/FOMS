"""P2-01: HTMX vendor, layout partial, and split-view fragment endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


def test_htmx_vendor_and_layout_contract() -> None:
    vendor = ROOT / "static/js/vendor/htmx.min.js"
    assert vendor.exists()
    assert vendor.stat().st_size > 10_000
    layout = (ROOT / "templates/partials/shared/htmx_layout.html").read_text(encoding="utf-8")
    assert "js/vendor/htmx.min.js" in layout
    assert "unpkg.com" not in layout
    app_shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "templates/partials/shared/erp_mobile_shell.html").read_text(
        encoding="utf-8"
    )
    assert "foms_app_shell.html" in shell
    assert "htmx_layout.html" in app_shell
    assert "unpkg.com/htmx" not in app_shell


def test_split_master_cards_use_fragment_href() -> None:
    from foms.services.foms_split_view import build_split_master_cards

    cards = build_split_master_cards([{"id": 9, "customer_name": "T", "product": "P"}])
    assert cards[0]["detail_href"] == "/api/foms/fragment/order/9/edit?open=erp-order"


def test_order_edit_fragment_returns_body_not_document(client, app, monkeypatch) -> None:
    from db import db_session
    from models import Order, User

    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true")
    with app.app_context():
        user = User(
            username="p2_frag_admin",
            password=generate_password_hash("pass"),
            role="ADMIN",
            name="P2",
        )
        db_session.add(user)
        order = Order(
            received_date="2026-05-30",
            customer_name="Frag",
            phone="010-1111-2222",
            address="Seoul",
            product="Cabinet",
            is_erp_order=True,
            structured_data={"items": [{"product_name": "Cabinet"}]},
        )
        db_session.add(order)
        db_session.commit()
        oid = order.id
        uid = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid

    response = client.get(f"/api/foms/fragment/order/{oid}/edit?open=erp-order")
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-Fragment") == "1"
    body = response.get_data(as_text=True)
    assert "<!DOCTYPE" not in body[:120]
    assert "foms-order-detail-fragment" in body
    assert "erp-order-config" in body
    assert "foms:main-content-swapped" in body


def test_order_edit_fragment_requires_auth(client) -> None:
    response = client.get("/api/foms/fragment/order/1/edit")
    assert response.status_code in (302, 401, 403)
