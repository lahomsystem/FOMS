"""route-eta 엔드포인트 계약 — '오늘 동선' 스트립 캡션의 카카오 실도로 ETA 소스.

카카오 호출은 monkeypatch로 스텁한다(외부 네트워크 무의존).
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common.address_converter import FOMSAddressConverter
from models import Order, User


def _login_admin(client):
    user = User(
        username="route_eta_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Route ETA Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order(**kw) -> Order:
    order = Order(
        received_date="2026-07-14",
        customer_name=kw.pop("customer_name", "ETA 고객"),
        phone="010-1111-2222",
        address="서울 송파구 올림픽로 300",
        product="붙박이장",
        status="MEASURE",
        is_erp_order=True,
        **kw,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_route_eta_missing_params_returns_400(client):
    _login_admin(client)
    resp = client.get("/api/erp/measurement/route-eta")
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_route_eta_out_of_range_returns_400(client):
    _login_admin(client)
    order = _make_order(lat=37.5, lng=127.0)
    resp = client.get(
        f"/api/erp/measurement/route-eta?order_id={order.id}&from_lat=999&from_lng=127.0"
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_route_eta_order_without_coords_returns_success_false(client):
    _login_admin(client)
    order = _make_order(lat=None, lng=None)
    resp = client.get(
        f"/api/erp/measurement/route-eta?order_id={order.id}&from_lat=37.5&from_lng=127.0"
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is False


def test_route_eta_success_maps_kakao_result(client, monkeypatch):
    _login_admin(client)
    order = _make_order(lat=37.48, lng=127.12)

    def _stub(self, s_lat, s_lng, e_lat, e_lng, timeout=None):
        return {"status": "success", "distance_km": 4.2, "duration_min": 14, "toll": 0}

    monkeypatch.setattr(FOMSAddressConverter, "calculate_route", _stub)
    resp = client.get(
        f"/api/erp/measurement/route-eta?order_id={order.id}&from_lat=37.50&from_lng=127.03"
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["distance_km"] == 4.2
    assert payload["data"]["duration_min"] == 14


def test_route_eta_kakao_error_returns_success_false(client, monkeypatch):
    _login_admin(client)
    order = _make_order(lat=37.48, lng=127.12)

    def _stub(self, *a, **k):
        return {"status": "error", "message": "boom"}

    monkeypatch.setattr(FOMSAddressConverter, "calculate_route", _stub)
    resp = client.get(
        f"/api/erp/measurement/route-eta?order_id={order.id}&from_lat=37.50&from_lng=127.03"
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is False
