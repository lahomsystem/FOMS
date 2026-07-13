"""Regional dashboard bucket rules — orders must not appear in multiple sections."""

import re
from datetime import timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, User


ROOT = Path(__file__).resolve().parents[2]


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
    return set(_order_row_ids_in_section(html, section_title))


def _section_chunk(html: str, section_title: str) -> str:
    """Return HTML chunk for a regional dashboard section header."""
    marker = f">{section_title}"
    start = html.find(marker)
    assert start != -1, f"missing section: {section_title}"
    next_card = html.find('<div class="row mb-4">', start + len(marker))
    return html[start:next_card] if next_card != -1 else html[start:]


def _order_row_ids_in_section(html: str, section_title: str) -> list[str]:
    """Return rendered order row ids under a regional dashboard section header."""
    chunk = _section_chunk(html, section_title)
    return re.findall(r'<tr[^>]+data-order-id="(\d+)"', chunk)


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


def test_as_received_rework_shipping_joins_alerts_sorted_and_badged(client) -> None:
    """AS_RECEIVED rework orders with a new shipping date join the regular alert sort."""
    _login_as_admin(client, "regional-bucket-as-rework-admin")
    today = get_today_kst()
    as_shipping_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    normal_shipping_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

    normal_order = _create_regional_order(
        customer_name="AS Shipping Sort Normal",
        status="PRODUCTION",
        shipping_scheduled_date=normal_shipping_date,
        measurement_completed=True,
    )
    as_order = _create_regional_order(
        customer_name="AS Shipping Sort Rework",
        status="AS_RECEIVED",
        shipping_scheduled_date=as_shipping_date,
        measurement_completed=False,
        as_received_date=today.strftime("%Y-%m-%d"),
    )

    response = client.get(
        "/regional_dashboard",
        query_string={"search_query": "AS Shipping Sort"},
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    alert_ids = _order_row_ids_in_section(body, "상차 예정 알림 (2건)")
    assert alert_ids == [str(as_order.id), str(normal_order.id)]

    as_row = re.search(rf'<tr[^>]+data-order-id="{as_order.id}".*?</tr>', body, re.S)
    assert as_row is not None
    as_row_html = as_row.group(0)
    assert 'data-as-shipping-schedule="true"' in as_row_html
    assert "regional-as-schedule-badge" in as_row_html
    assert "AS 재상차 일정" in as_row_html


def test_regional_shipping_export_preserves_as_schedule_badge_contract() -> None:
    """PNG export must carry the AS schedule marker from the rendered row."""
    js = (ROOT / "static/js/measurement/regional-shipping-export.js").read_text(
        encoding="utf-8"
    )

    assert "data-as-shipping-schedule" in js
    assert "is_as_schedule" in js
    assert "querySelector('.regional-as-schedule-badge')" in js
    assert "badge.textContent = 'AS'" in js
