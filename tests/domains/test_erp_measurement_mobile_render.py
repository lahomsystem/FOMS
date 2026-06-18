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


def test_measurement_mobile_page_renders_queue_card_attachments(client, monkeypatch):
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
    assert "모바일 실측" in body
    assert "foms-queue-card-v2__attachments" in body
    assert "data-foms-erp-attachment-preview-gallery" in body
    assert "data-foms-erp-attachment-view-url" in body
    assert "erp-attachment-preview-open.js" in body


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
    assert "Mobile Manager Restore" in body
    # 담당은 user id가 아니라 표시명(Resolved Manager)으로 정규화되어 카드에 노출
    assert "Resolved Manager" in body
    assert f"담당 {manager_user_id}" not in body


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
