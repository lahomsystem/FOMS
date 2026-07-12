"""B3 생산 공정 스텝 API 계약 (POST /api/orders/<id>/production/steps).

- 기본 5단계(cut/edge/paint/assemble/inspect) 최초 접근 시 생성
- 토글(체크/해제) 시 at·by_name 기록/삭제
- 권한: ADMIN 및 PRODUCTION 팀 허용, DRAWING 팀 403
- 잘못된 payload 400
- OrderEvent PRODUCTION_STEP_CHECKED 기록
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _make_user(username: str, *, role: str = "STAFF", team: str | None = None) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order() -> Order:
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="공정 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="PRODUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "생산"}},
        erp_stage_code="생산",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_first_toggle_seeds_default_five_steps(client):
    user = _make_user("prod_admin", role="ADMIN")
    user_name = user.name
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(
        f"/api/orders/{order_id}/production/steps",
        json={"key": "cut", "done": True},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    steps = data["data"]["steps"]
    assert [s["key"] for s in steps] == ["cut", "edge", "paint", "assemble", "inspect"]
    assert data["data"]["total"] == 5
    assert data["data"]["done_count"] == 1

    cut = next(s for s in steps if s["key"] == "cut")
    assert cut["done"] is True
    assert cut["at"]  # UTC iso 기록
    assert cut["by_name"] == user_name

    # 저장 확인(deepcopy+flag_modified 반영)
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    saved_steps = saved.structured_data["production"]["steps"]
    assert len(saved_steps) == 5
    assert next(s for s in saved_steps if s["key"] == "cut")["done"] is True


def test_toggle_off_clears_at_and_by_name(client):
    user = _make_user("prod_admin2", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/production/steps", json={"key": "paint", "done": True})
    resp = client.post(
        f"/api/orders/{order_id}/production/steps",
        json={"key": "paint", "done": False},
    )
    assert resp.status_code == 200
    steps = resp.get_json()["data"]["steps"]
    paint = next(s for s in steps if s["key"] == "paint")
    assert paint["done"] is False
    assert paint["at"] is None
    assert paint["by_name"] is None
    assert resp.get_json()["data"]["done_count"] == 0


def test_production_team_allowed(client):
    user = _make_user("prod_worker", role="STAFF", team="PRODUCTION")
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(
        f"/api/orders/{order_id}/production/steps",
        json={"key": "edge", "done": True},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_drawing_team_forbidden(client):
    user = _make_user("draw_worker", role="STAFF", team="DRAWING")
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(
        f"/api/orders/{order_id}/production/steps",
        json={"key": "edge", "done": True},
    )
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_invalid_payload_returns_400(client):
    user = _make_user("prod_admin3", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    # 알 수 없는 key
    r1 = client.post(f"/api/orders/{order_id}/production/steps", json={"key": "bogus", "done": True})
    assert r1.status_code == 400
    # done 이 bool 아님
    r2 = client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": "yes"})
    assert r2.status_code == 400
    # key 누락
    r3 = client.post(f"/api/orders/{order_id}/production/steps", json={"done": True})
    assert r3.status_code == 400


def test_order_event_recorded(client):
    user = _make_user("prod_admin4", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/production/steps", json={"key": "inspect", "done": True})

    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "PRODUCTION_STEP_CHECKED")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["key"] == "inspect"
    assert events[0].payload["done"] is True
    assert events[0].created_by_user_id == user_id
