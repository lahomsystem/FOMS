"""P1-04: inline patch service + PATCH API tests."""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_inline_patch import apply_field_patch, is_critical_field
from models import Order, User


def test_is_critical_field() -> None:
    assert is_critical_field("parties.customer.phone") is True
    assert is_critical_field("items.0.color") is False
    assert is_critical_field("items.1.price") is True


def test_apply_field_patch_items(app) -> None:
    base = {"items": [{"color": "old"}]}
    updated = apply_field_patch(base, "items.0.color", "new")
    assert updated["items"][0]["color"] == "new"
    assert base["items"][0]["color"] == "old"


@pytest.fixture
def inline_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true")


def _login(client, app, username: str = "inline_user") -> Order:
    with app.app_context():
        user = User(
            username=username,
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Inline",
        )
        db_session.add(user)
        order = Order(
            received_date="2026-05-30",
            customer_name="테스트",
            phone="010-1111-2222",
            address="Seoul",
            product="장",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "테스트", "phone": "010-1111-2222"}},
                "site": {"address_full": "Seoul"},
                "items": [{"product_name": "장", "color": "white"}],
            },
            structured_updated_at=__import__("datetime").datetime.now(),
        )
        db_session.add(order)
        db_session.commit()
        order_id = order.id
    client.post("/login", data={"username": username, "password": "admin"}, follow_redirects=True)
    return order_id


def test_patch_inline_field(client, app, inline_enabled) -> None:
    order_id = _login(client, app, "inline_patch_user")
    get_resp = client.get(f"/api/orders/{order_id}/structured")
    updated_at = get_resp.get_json()["structured_updated_at"]

    patch = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        data=json.dumps({"field": "items.0.color", "value": "크림"}),
        content_type="application/json",
        headers={"X-If-Match": updated_at or ""},
    )
    assert patch.status_code == 200
    body = patch.get_json()
    assert body["success"] is True
    assert body["critical"] is False

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.structured_data["items"][0]["color"] == "크림"


def test_patch_conflict_409(client, app, inline_enabled) -> None:
    order_id = _login(client, app, "inline_conflict_user")
    stale = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        data=json.dumps({"field": "items.0.color", "value": "blue"}),
        content_type="application/json",
        headers={"X-If-Match": "1999-01-01 00:00:00"},
    )
    assert stale.status_code == 409


def test_inline_assets_wired() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/foms/inline-edit.js").read_text(encoding="utf-8")
    product_js = (root / "static/js/foms/product-item.js").read_text(encoding="utf-8")
    erp_js = (root / "templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    body = (root / "templates/orders/partials/edit_order_body.html").read_text(encoding="utf-8")
    assert "structured/fields" in js
    assert "fomsProductItem" in product_js
    assert "product-item.js" in erp_js
    assert "data-foms-inline-enabled" in body
