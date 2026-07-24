"""생산 보류 플래그 API 계약 (POST /api/orders/<id>/production/hold).

- 토글 ON: hold.active=True, reason/at/by_name 기록, 워크플로/상태 불변(표시 전용).
- 토글 OFF: hold.active=False, reason=""/at=None/by_name=None 로 초기화.
- 멱등: ON 재호출은 200 이며 active 유지.
- 권한: ADMIN·PRODUCTION 팀 허용, DRAWING 팀 403.
- 잘못된 payload(active 비-bool) 400.
- OrderEvent PRODUCTION_HOLD_TOGGLED 기록.
- deepcopy+flag_modified 저장 반영.
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
        customer_name="보류 고객",
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


def test_hold_activate_records_and_keeps_workflow(client):
    user = _make_user("hold_admin", role="ADMIN")
    user_name = user.name
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(
        f"/api/orders/{order_id}/production/hold",
        json={"active": True, "reason": "자재 입고 지연"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    hold = data["data"]["hold"]
    assert hold["active"] is True
    assert hold["reason"] == "자재 입고 지연"
    assert hold["at"]
    assert hold["by_name"] == user_name

    # 표시 전용 — 워크플로 단계/상태 불변.
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "PRODUCTION"
    assert saved.structured_data["workflow"]["stage"] == "생산"
    assert saved.structured_data["production"]["hold"]["active"] is True


def test_hold_release_clears_fields(client):
    user = _make_user("hold_admin2", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "x"})
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": False})
    assert resp.status_code == 200
    hold = resp.get_json()["data"]["hold"]
    assert hold["active"] is False
    assert hold["reason"] == ""
    assert hold["at"] is None
    assert hold["by_name"] is None


def test_hold_activate_is_idempotent(client):
    user = _make_user("hold_admin3", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    r1 = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "a"})
    r2 = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "b"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.get_json()["data"]["hold"]["active"] is True
    assert r2.get_json()["data"]["hold"]["reason"] == "b"


def test_production_team_allowed(client):
    user = _make_user("hold_prod", role="STAFF", team="PRODUCTION")
    _login(client, user)
    order_id = _make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_drawing_team_forbidden(client):
    user = _make_user("hold_draw", role="STAFF", team="DRAWING")
    _login(client, user)
    order_id = _make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_invalid_active_returns_400(client):
    user = _make_user("hold_admin4", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id
    # active 누락
    r1 = client.post(f"/api/orders/{order_id}/production/hold", json={"reason": "x"})
    assert r1.status_code == 400
    # active 비-bool
    r2 = client.post(f"/api/orders/{order_id}/production/hold", json={"active": "yes"})
    assert r2.status_code == 400


def test_missing_order_returns_404(client):
    user = _make_user("hold_admin5", role="ADMIN")
    _login(client, user)
    resp = client.post("/api/orders/999999/production/hold", json={"active": True})
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_order_event_recorded(client):
    user = _make_user("hold_admin6", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "z"})
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["active"] is True
    assert events[0].payload["reason"] == "z"
    assert events[0].created_by_user_id == user_id


def test_hold_release_appends_history(client):
    """해제(active=False) 시 직전 active hold 를 hold_history 에 보존한다(완료 후 소실 방지, E-a).

    {reason, at(보류 시작), released_at(now), released_by} 1건 append. 해제 응답의 hold 는
    초기화되지만 hold_history 는 별도로 남는다.
    """
    user = _make_user("hold_hist", role="ADMIN")
    user_name = user.name
    _login(client, user)
    order_id = _make_order().id

    client.post(
        f"/api/orders/{order_id}/production/hold",
        json={"active": True, "reason": "자재 입고 지연"},
    )
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": False})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    history = saved.structured_data["production"]["hold_history"]
    assert len(history) == 1
    assert history[0]["reason"] == "자재 입고 지연"
    assert history[0]["at"]  # 보류 시작 시각 보존
    assert history[0]["released_at"]  # 해제 시각 기록
    assert history[0]["released_by"] == user_name


def test_hold_release_without_active_does_not_append_history(client):
    """active hold 가 없는 상태의 해제(빈 해제)는 hold_history 를 만들지 않는다(중복·빈 append 방지)."""
    user = _make_user("hold_hist2", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    # 활성화 없이 곧바로 해제 → 이력 append 없음.
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": False})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    production = saved.structured_data.get("production") or {}
    assert production.get("hold_history", []) == []
