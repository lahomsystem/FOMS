"""Regional dashboard ERP display sync contracts."""

import re

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Regional ERP Sync Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_regional_dashboard_dates_render_from_erp_order_schedule(client) -> None:
    """Regional dashboard date inputs must display ERP Order schedule dates."""
    _login_as_admin(client, "regional-dashboard-erp-date-admin")
    order = Order(
        received_date="2026-07-01",
        customer_name="Legacy Name",
        phone="010-5555-5555",
        address="Daegu",
        product="Legacy Product",
        status="MEASURE",
        is_erp_order=True,
        is_regional=True,
        construction_type="협력사 시공",
        measurement_completed=False,
        measurement_date="2026-07-01",
        scheduled_date="",
        structured_data={
            "parties": {"customer": {"name": "ERP Regional Customer"}},
            "schedule": {
                "measurement": {"date": "2026-07-13"},
                "construction": {"date": "2026-07-21"},
            },
        },
    )
    db_session.add(order)
    db_session.commit()

    response = client.get("/regional_dashboard", query_string={"search_query": str(order.id)})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    row = re.search(rf'<tr[^>]+data-order-id="{order.id}".*?</tr>', body, re.S)
    assert row is not None
    row_html = row.group(0)
    assert 'data-field="measurement_date"' in row_html
    assert 'value="2026-07-13"' in row_html
    assert 'data-field="scheduled_date"' in row_html
    assert 'value="2026-07-21"' in row_html
