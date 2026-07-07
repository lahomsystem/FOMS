"""도면 마법사 페이지 라우트 계약 테스트 (200 + config JSON 파싱 + 미로그인 redirect)."""

import json
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_admin(client, username="wizard-page-admin"):
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name="도면관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _erp_order():
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="서으뜸",
        phone="010-1111-2222",
        address="대구",
        product="붙박이장",
        status="DRAWING",
        manager_name="하우드 김성일",
        is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "서으뜸"}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_wizard_page_renders_with_parseable_config(client):
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}/wizard")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="dws-root"' in body
    assert f"도면 마법사 — 주문 #{order_id}" in body

    marker = '<script id="drawing-wizard-config" type="application/json">'
    start = body.index(marker) + len(marker)
    end = body.index("</script>", start)
    config = json.loads(body[start:end])
    assert config["order_id"] == order_id
    assert config["can_save"] is True


def test_wizard_page_missing_order_redirects_to_dashboard(client):
    _login_admin(client)

    resp = client.get("/erp/drawing-workbench/99999/wizard")

    assert resp.status_code == 302
    assert "/erp/drawing-workbench" in resp.headers["Location"]


def test_wizard_page_requires_login(client):
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}/wizard")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_workbench_detail_shows_wizard_entry_button(client):
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/erp/drawing-workbench/{order_id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f"/drawing-workbench/{order_id}/wizard" in body
