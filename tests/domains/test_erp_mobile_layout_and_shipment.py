from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderScheduleDate, User


def _login_erp_admin(client):
    user = User(
        username="erp_mobile_layout_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Mobile Layout Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_erp_pages_mark_body_for_mobile_layout_shell(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_erp_admin(client)

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in body
    assert 'class="layout-global-nav navbar' in body


def test_shipment_mobile_markup_includes_colgroup_reset_override(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_erp_admin(client)

    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="모바일 출고",
        phone="010-5555-6666",
        address="Seoul",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="Alice",
        is_erp_beta=True,
        structured_data={
            "items": [
                {
                    "product_name": "상부장",
                    "spec_width": "1200",
                    "spec_depth": "600",
                    "spec_height": "2300",
                    "quantity": 1,
                }
            ],
            "shipment": {
                "construction_time": "10:00",
                "drawing_managers": ["도면1"],
                "construction_workers": ["시공1"],
            },
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get("/erp/shipment")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="shipment-dashboard-table"' in body
    assert "#shipment-dashboard-table colgroup" in body
    assert "#shipment-dashboard-table tbody tr" in body
    assert "Shipment Queue" in body


def test_shipment_dashboard_allows_past_date_search(client):
    _login_erp_admin(client)

    today = date.today()
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    order = Order(
        received_date=today.strftime("%Y-%m-%d"),
        customer_name="과거 출고 검색",
        phone="010-7777-8888",
        address="Busan",
        product="수납장",
        status="IN_CONSTRUCTION",
        manager_name="Bob",
        is_erp_beta=True,
        scheduled_date=yesterday,
        structured_data={
            "items": [
                {
                    "product_name": "하부장",
                    "spec_width": "900",
                    "spec_depth": "600",
                    "spec_height": "2300",
                    "quantity": 1,
                }
            ],
            "shipment": {},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=yesterday,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get(f"/erp/shipment?date={yesterday}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="shipment-dashboard-table"' in body
    assert "과거 출고 검색" in body
