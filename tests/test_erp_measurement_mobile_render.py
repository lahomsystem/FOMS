from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, OrderScheduleDate, User


def _login_erp_admin(client):
    user = User(
        username="measurement_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Measurement Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_measurement_mobile_page_renders_item_attachment_group_keys(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_erp_admin(client)

    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="모바일 실측",
        phone="010-2222-3333",
        address="Seoul",
        product="붙박이장",
        status="MEASURE",
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
            ]
        },
    )
    db_session.add(order)
    db_session.flush()

    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="measurement-1.jpg",
            file_type="image/jpeg",
            storage_key="tests/measurement-1.jpg",
            category="measurement",
            item_index=0,
        )
    )
    db_session.commit()

    response = client.get("/erp/measurement")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f'data-group-key="measurement_mobile_{order.id}_item_0"' in body
    assert "erp-measurement-mobile-attachment" in body
