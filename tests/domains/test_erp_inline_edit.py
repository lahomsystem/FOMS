"""P1-04: inline patch service + PATCH API tests."""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash

from sqlalchemy.orm.attributes import flag_modified

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


def test_inline_price_save_refreshes_the_saved_totals(client, app, inline_enabled) -> None:
    """**품목금액 인라인 저장이 잔금을 세운다** (2026-08-26 CEO M-1).

    ``totals`` 는 ``items[].price`` 와 ``payment.*`` 에서 파생되는데 인라인 경로만
    재계산을 안 했다. 그래서 예약금이 들어와 있고 품목금액을 나중에 넣는 주문
    (네이버 승격분이 정확히 그 모양이다)에서, 금액을 넣어도 저장 ``totals`` 가
    ``items_total 0`` 인 채로 남아 저장 totals 를 먼저 읽는 표면이 **잔금 0원**을
    계속 보여줬다. 화면에 버튼을 다는 순간 돈이 사라지는 트립와이어였다.
    """
    order_id = _login(client, app, "inline_price_user")
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = dict(order.structured_data)
        sd["payment"] = {"deposit": 1_000_000}
        sd["totals"] = {"items_total": 0, "balance_amount": 0, "deposit_amount": 1_000_000}
        order.structured_data = sd
        flag_modified(order, "structured_data")
        db_session.commit()

    response = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        data=json.dumps({"field": "items.0.price", "value": "1,500,000"}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    with app.app_context():
        totals = db_session.query(Order).filter_by(id=order_id).one().structured_data["totals"]
    assert totals["items_total"] == 1_500_000, "품목금액을 넣었는데 저장 합계가 옛 0 그대로다"
    assert totals["balance_amount"] == 500_000, "잔금이 서지 않았다(돈이 사라진다)"


def test_payment_paths_are_not_inline_editable_today(client, app, inline_enabled) -> None:
    """``payment.*`` 는 아직 인라인 경로가 아니다 — 재계산 조건이 **미리** 덮어 둔 자리다.

    ``_field_affects_totals`` 는 ``payment.`` 도 재계산 대상으로 본다. 지금은
    ``apply_field_patch`` 가 그 경로를 거절하므로 도달하지 않지만, 나중에 예약금을
    인라인으로 열 때 같은 트립와이어를 다시 밟지 않도록 조건을 먼저 넓혀 뒀다.
    이 단언은 "지금은 못 간다"는 사실 쪽을 잠근다 — 열리면 여기가 빨개진다.
    """
    order_id = _login(client, app, "inline_deposit_user")

    response = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        data=json.dumps({"field": "payment.deposit", "value": 400_000}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "unsupported field path" in response.get_json()["error"]


def test_field_affects_totals_covers_both_money_sources() -> None:
    """재계산 조건이 금액 소스 둘(``items[].price``·``payment.*``)만 고른다."""
    from foms.api.erp_orders_structured import _field_affects_totals

    assert _field_affects_totals("items.0.price") is True
    assert _field_affects_totals("items.12.price") is True
    assert _field_affects_totals("payment.deposit") is True
    assert _field_affects_totals("items.0.color") is False
    assert _field_affects_totals("items.0.spec_rows") is False
    assert _field_affects_totals("notes") is False
    assert _field_affects_totals("schedule.construction.date") is False


def test_non_money_inline_field_leaves_totals_alone(client, app, inline_enabled) -> None:
    """금액과 무관한 필드는 ``totals`` 를 건드리지 않는다 — 옛 주문 값이 조용히 바뀌면 안 된다."""
    order_id = _login(client, app, "inline_nonmoney_user")
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = dict(order.structured_data)
        sd["totals"] = {"items_total": 777, "balance_amount": 777}
        order.structured_data = sd
        flag_modified(order, "structured_data")
        db_session.commit()

    response = client.patch(
        f"/api/orders/{order_id}/structured/fields",
        data=json.dumps({"field": "items.0.color", "value": "네이비"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    with app.app_context():
        totals = db_session.query(Order).filter_by(id=order_id).one().structured_data["totals"]
    assert totals == {"items_total": 777, "balance_amount": 777}, "무관한 편집이 금액을 다시 썼다"


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
