import re
from datetime import date

from foms.web.measurement import dashboard as erp_measurement_dashboard
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
    fake_today = date(2026, 4, 8)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    today = fake_today.strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="모바일 실측",
        phone="010-2222-3333",
        address="Seoul",
        product="붙박이장",
        status="MEASURE",
        manager_name="Alice",
        is_erp_order=True,
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
    order_id = order.id

    db_session.add(
        OrderScheduleDate(
            order_id=order_id,
            kind="measurement",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.add(
        OrderAttachment(
            order_id=order_id,
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
    assert f'data-group-key="measurement_mobile_{order_id}_item_0"' in body
    assert "erp-measurement-mobile-attachment" in body


def test_measurement_mobile_page_uses_normalized_manager_name(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 4, 8)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    manager_user = User(
        username="measurement_mobile_manager",
        password=generate_password_hash("manager"),
        role="STAFF",
        team="CS",
        name="Resolved Manager",
        is_active=True,
    )
    db_session.add(manager_user)
    db_session.commit()
    manager_user_id = manager_user.id

    today = fake_today.strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="Mobile Manager Restore",
        phone="010-1234-5678",
        address="Seoul",
        product="Cabinet",
        status="MEASURE",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={
            "parties": {
                "manager": {
                    "name": manager_user.id,
                }
            },
            "items": [
                {
                    "product_name": "Upper Cabinet",
                }
            ],
        },
    )
    db_session.add(order)
    db_session.flush()
    order_id = order.id
    db_session.add(
        OrderScheduleDate(
            order_id=order_id,
            kind="measurement",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    response = client.get("/erp/measurement")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    customer_idx = body.find("Mobile Manager Restore")
    assert customer_idx != -1
    snippet = body[customer_idx:customer_idx + 500]
    match = re.search(r'data-measurement-mobile-manager>([^<]+)<', snippet)
    assert match is not None
    assert match.group(1).strip()
    assert match.group(1).strip() != str(manager_user_id)


def test_measurement_dashboard_excludes_stale_legacy_schedule_date(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 5, 4)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    user = _login_erp_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = Order(
        received_date="2026-05-01",
        customer_name="Stale Legacy Measurement",
        phone="010-9999-0000",
        address="Seoul",
        product="Cabinet",
        status="MEASURE",
        measurement_date="2026-05-04",
        is_erp_order=True,
        erp_measurement_date="2026-05-06",
        structured_data={
            "schedule": {"measurement": {"date": "2026-05-06"}},
            "items": [{"product_name": "Cabinet"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            OrderScheduleDate(
                order_id=order.id,
                kind="measurement",
                date="2026-05-04",
                source="legacy_column",
            ),
            OrderScheduleDate(
                order_id=order.id,
                kind="measurement",
                date="2026-05-06",
                source="beta_schedule",
            ),
        ]
    )
    db_session.commit()

    stale_response = client.get("/erp/measurement?date=2026-05-04")
    fresh_response = client.get("/erp/measurement?date=2026-05-06")

    assert stale_response.status_code == 200
    assert fresh_response.status_code == 200
    assert "Stale Legacy Measurement" not in stale_response.get_data(as_text=True)
    assert "Stale Legacy Measurement" in fresh_response.get_data(as_text=True)
