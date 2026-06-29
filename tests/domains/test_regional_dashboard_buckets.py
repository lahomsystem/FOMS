"""Regional dashboard bucket rules — orders must not appear in multiple sections."""

import re
from datetime import timedelta
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, User


def _login_as_admin(client, username: str) -> User:
    """Create an admin user and attach it to the test client session."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Regional Dashboard Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_regional_order(**overrides) -> Order:
    """Create a minimal regional order for dashboard bucket tests."""
    payload = {
        "received_date": "2026-06-01",
        "customer_name": "Regional Bucket Tester",
        "phone": "010-2222-3333",
        "address": "Busan",
        "product": "Kitchen",
        "status": "MEASURE",
        "is_regional": True,
        "measurement_completed": True,
        "structured_data": {},
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def _order_ids_in_section(html: str, section_title: str) -> set[str]:
    """Return order ids rendered under a regional dashboard section header."""
    marker = f">{section_title}"
    start = html.find(marker)
    assert start != -1, f"missing section: {section_title}"
    next_card = html.find('<div class="row mb-4">', start + len(marker))
    chunk = html[start:next_card] if next_card != -1 else html[start:]
    return set(re.findall(r'data-order-id="(\d+)"', chunk))


def _order_ids_in_card_class(html: str, card_class: str) -> set[str]:
    """Return order ids inside a rendered dashboard card by CSS class."""
    match = re.search(rf'<div class="card shadow {re.escape(card_class)}".*?</div>\s*</div>\s*</div>', html, re.S)
    if not match:
        return set()
    return set(re.findall(r'data-order-id="(\d+)"', match.group(0)))


def test_scheduled_regional_order_excluded_from_shipping_completed(client) -> None:
    """SCHEDULED orders belong only in 설치 예정, not 상차완료."""
    _login_as_admin(client, "regional-bucket-scheduled-admin")
    past_shipping_date = (get_today_kst() - timedelta(days=3)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="SCHEDULED",
        shipping_scheduled_date=past_shipping_date,
        completion_date="2026-06-20",
    )

    response = client.get("/regional_dashboard", query_string={"search_query": str(order.id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    scheduled_ids = _order_ids_in_section(body, "설치 예정 (1건)")
    assert scheduled_ids == {str(order.id)}
    assert str(order.id) not in body or "상차완료 (" not in body


def test_scheduled_regional_order_excluded_from_shipping_alerts(client) -> None:
    """SCHEDULED orders must not appear in 상차 예정 알림."""
    _login_as_admin(client, "regional-bucket-alert-admin")
    future_shipping_date = (get_today_kst() + timedelta(days=2)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="SCHEDULED",
        shipping_scheduled_date=future_shipping_date,
    )

    response = client.get("/regional_dashboard", query_string={"search_query": str(order.id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert _order_ids_in_section(body, "설치 예정 (1건)") == {str(order.id)}
    assert _order_ids_in_card_class(body, "shipping-alert-card") == set()


def test_non_scheduled_regional_order_still_in_shipping_completed(client) -> None:
    """Non-SCHEDULED orders with past shipping date still belong in 상차완료."""
    _login_as_admin(client, "regional-bucket-shipped-admin")
    past_shipping_date = (get_today_kst() - timedelta(days=2)).strftime("%Y-%m-%d")

    order = _create_regional_order(
        status="PRODUCTION",
        shipping_scheduled_date=past_shipping_date,
    )

    response = client.get("/regional_dashboard", query_string={"search_query": str(order.id)})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert _order_ids_in_section(body, "상차완료 (1건)") == {str(order.id)}
    assert "설치 예정 (1건)" not in body
