from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client):
    user = User(
        username="erp_as_tabs_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP AS Tabs Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_as_order(*, notes=None, as_content_2="<div>2번 내용</div>"):
    today = date.today().strftime("%Y-%m-%d")
    shipment = {
        "as_content": "<div>1번 내용</div>",
    }
    if as_content_2 is not None:
        shipment["as_content_2"] = as_content_2
    order = Order(
        received_date=today,
        customer_name="AS 탭 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        is_erp_beta=True,
        notes=notes,
        structured_data={"shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_dashboard_renders_primary_and_secondary_tabs(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_as_admin(client)
    _create_as_order()

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-as-tab-target="1"' in body
    assert 'data-as-tab-target="2"' in body
    assert 'data-field-name="as_content"' in body
    assert 'data-field-name="as_content_2"' in body
    assert "2번 내용" in body


def test_update_order_field_saves_secondary_as_content(client):
    _login_as_admin(client)
    order = _create_as_order()

    response = client.post(
        "/api/update_order_field",
        json={
            "order_id": order.id,
            "field_name": "as_content_2",
            "new_value": "<div>두번째<br>AS 내용</div>",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "두번째" in data["normalized_value"]
    assert "AS 내용" in data["normalized_value"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.structured_data["shipment"]["as_content_2"] == data["normalized_value"]


def test_as_dashboard_falls_back_to_order_notes_for_secondary_tab(client):
    _login_as_admin(client)
    _create_as_order(notes="아일랜드 서랍 마이다 불량\n조명 색상변경", as_content_2=None)

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "아일랜드 서랍 마이다 불량" in body
    assert "조명 색상변경" in body


def test_as_dashboard_does_not_restore_notes_after_secondary_tab_is_cleared(client):
    _login_as_admin(client)
    _create_as_order(notes="복구되면 안 되는 기존 메모", as_content_2="")

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "복구되면 안 되는 기존 메모" not in body
