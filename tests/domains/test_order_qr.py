"""B4 QR 라벨·스캔 계약 테스트.

- GET /api/orders/<id>/qr.svg → 200 + SVG 시그니처(로그인), 비로그인 302, 없는 주문 404
- GET /erp/orders/<id>/label → 200 + 라벨 마커(로그인), 없는 주문 404

call_log 테스트와 동일하게 요청 전 정수 id만 확보하고, 요청 후 db_session.remove()로
세션을 리셋한다.
"""

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login(client, *, username="qr-user", role="STAFF", team="CS"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _create_order():
    order = Order(
        received_date="2026-04-07",
        customer_name="QR 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="PRODUCTION",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "PRODUCTION"},
            "parties": {"customer": {"name": "QR 고객"}},
            "items": [{"product_name": "붙박이장"}, {"product_name": "신발장"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    oid = order.id
    return oid


def test_qr_svg_returns_svg(client, app):
    """로그인 상태 → 200, image/svg+xml, SVG 시그니처, private 캐시 헤더."""
    _login(client)
    oid = _create_order()

    resp = client.get(f"/api/orders/{oid}/qr.svg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/svg+xml"
    assert b"<svg" in resp.data
    assert "private" in resp.headers.get("Cache-Control", "")


def test_qr_svg_requires_login(client, app):
    """비로그인 → 로그인 리다이렉트 302."""
    oid = _create_order()

    resp = client.get(f"/api/orders/{oid}/qr.svg")
    assert resp.status_code == 302


def test_qr_svg_missing_order_404(client, app):
    """없는 주문 → 404."""
    _login(client)

    resp = client.get("/api/orders/99999999/qr.svg")
    assert resp.status_code == 404


def test_label_page_renders(client, app):
    """로그인 상태 → 200, 라벨 마커·주문번호·QR img·품목 요약 렌더."""
    _login(client)
    oid = _create_order()

    resp = client.get(f"/erp/orders/{oid}/label")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "data-foms-order-label" in body
    assert f"주문 #{oid}" in body
    assert f"/api/orders/{oid}/qr.svg" in body
    assert "외 1개" in body  # items 2건 → '붙박이장 외 1개'


def test_label_page_missing_order_404(client, app):
    """없는 주문 → 404."""
    _login(client)

    resp = client.get("/erp/orders/99999999/label")
    assert resp.status_code == 404
