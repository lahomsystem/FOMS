"""출고 패킹 체크리스트 API 계약 (B6).

GET 파생(items[] → 제품별 3항, 저장 안 함) · POST 저장 · 재GET 지속 ·
권한(SHIPMENT 허용 / DRAWING 403) · 잘못된 payload 400 · OrderEvent 기록.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, OrderEvent, User


def _make_user(username: str, team: str, role: str = "STAFF") -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role=role,
        team=team,
        name=username,
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
    today = get_today_kst().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="패킹 고객",
        phone="010-2000-3000",
        address="서울시 패킹구 1",
        product="싱크대",
        status="IN_CONSTRUCTION",
        scheduled_date=today,
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "items": [
                {"product_name": "싱크대"},
                {"product_name": "붙박이장"},
            ],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _url(order_id: int) -> str:
    return f"/api/erp/shipment/packing/{order_id}"


def test_get_derives_items_without_persisting(client) -> None:
    user = _make_user("packing_shipment_get", "SHIPMENT")
    _login(client, user)
    order = _make_order()

    res = client.get(_url(order.id))
    assert res.status_code == 200
    data = res.get_json()["data"]
    # 제품 2개 × 3항 = 6행 파생, 저장 안 됨(persisted=False)
    assert data["total"] == 6
    assert data["checked_count"] == 0
    assert data["persisted"] is False
    labels = [row["label"] for row in data["items"]]
    assert "싱크대 본체 패널" in labels
    assert "싱크대 도어" in labels
    assert "붙박이장 철물" in labels

    # 파생은 DB에 기록되지 않아야 한다.
    db_session.expire_all()
    fresh = db_session.query(Order).filter(Order.id == order.id).first()
    assert "packing" not in (fresh.structured_data.get("shipment") or {})


def test_post_saves_and_get_persists(client) -> None:
    user = _make_user("packing_shipment_save", "SHIPMENT")
    _login(client, user)
    order = _make_order()

    derived = client.get(_url(order.id)).get_json()["data"]["items"]
    target_key = derived[0]["key"]

    res = client.post(_url(order.id), json={"updates": [{"key": target_key, "checked": True}]})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["checked_count"] == 1
    assert data["persisted"] is True

    # 재GET 지속: 저장된 체크 상태가 유지되고 at/by_name 기록.
    again = client.get(_url(order.id)).get_json()["data"]
    assert again["persisted"] is True
    assert again["checked_count"] == 1
    checked_row = next(r for r in again["items"] if r["key"] == target_key)
    assert checked_row["checked"] is True
    assert checked_row["by_name"] == user.name
    assert checked_row["at"]


def test_post_add_item(client) -> None:
    user = _make_user("packing_add", "CS")
    _login(client, user)
    order = _make_order()

    res = client.post(_url(order.id), json={"add": {"label": "상판 유리", "qty": 2}})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["total"] == 7
    added = [r for r in data["items"] if r["label"] == "상판 유리"]
    assert len(added) == 1
    assert added[0]["qty"] == 2


def test_drawing_team_forbidden(client) -> None:
    user = _make_user("packing_drawing", "DRAWING")
    _login(client, user)
    order = _make_order()

    assert client.get(_url(order.id)).status_code == 403
    assert client.post(_url(order.id), json={"updates": []}).status_code == 403


def test_bad_payload_returns_400(client) -> None:
    user = _make_user("packing_bad", "SHIPMENT")
    _login(client, user)
    order = _make_order()

    # updates/add 둘 다 없음
    assert client.post(_url(order.id), json={}).status_code == 400
    # updates 타입 오류
    assert client.post(_url(order.id), json={"updates": "nope"}).status_code == 400
    # add label 누락
    assert client.post(_url(order.id), json={"add": {"qty": 1}}).status_code == 400


def test_post_sets_and_persists_issue(client) -> None:
    """누락 사유(issue) 표기 → 저장·재GET 지속, checked 보존, 이벤트 issues_count, 해제."""
    user = _make_user("packing_issue", "SHIPMENT")
    _login(client, user)
    order = _make_order()
    derived = client.get(_url(order.id)).get_json()["data"]["items"]
    target_key = derived[0]["key"]

    # 먼저 체크 → 이후 issue-only 업데이트가 checked 를 덮어쓰지 않아야 한다(부분 업데이트 계약).
    client.post(_url(order.id), json={"updates": [{"key": target_key, "checked": True}]})

    res = client.post(_url(order.id), json={"updates": [{"key": target_key, "issue": "damaged"}]})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["issues_count"] == 1
    row = next(r for r in data["items"] if r["key"] == target_key)
    assert row["issue"] == "damaged"
    assert row["issue_at"]
    assert row["issue_by_name"] == user.name
    assert row["checked"] is True  # issue-only 업데이트가 checked 보존

    # 재GET 지속.
    again = client.get(_url(order.id)).get_json()["data"]
    again_row = next(r for r in again["items"] if r["key"] == target_key)
    assert again_row["issue"] == "damaged"
    assert again_row["checked"] is True

    # OrderEvent payload 에 issues 카운트 포함.
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id, OrderEvent.event_type == "PACKING_UPDATED")
        .all()
    )
    assert events[-1].payload["issues_count"] == 1

    # 해제(null) → issue 제거, issues_count 0.
    clr = client.post(_url(order.id), json={"updates": [{"key": target_key, "issue": None}]})
    assert clr.status_code == 200
    cleared_data = clr.get_json()["data"]
    cleared = next(r for r in cleared_data["items"] if r["key"] == target_key)
    assert cleared["issue"] is None
    assert cleared_data["issues_count"] == 0


def test_post_rejects_invalid_issue(client) -> None:
    """화이트리스트 밖 issue 값 → 400, 저장 없음."""
    user = _make_user("packing_bad_issue", "SHIPMENT")
    _login(client, user)
    order = _make_order()
    derived = client.get(_url(order.id)).get_json()["data"]["items"]
    target_key = derived[0]["key"]

    res = client.post(_url(order.id), json={"updates": [{"key": target_key, "issue": "explode"}]})
    assert res.status_code == 400
    assert res.get_json()["success"] is False

    # 잘못된 요청은 커밋 전에 400 → packing 이 저장되지 않아야 한다.
    db_session.expire_all()
    fresh = db_session.query(Order).filter(Order.id == order.id).first()
    assert "packing" not in (fresh.structured_data.get("shipment") or {})


def test_post_records_order_event(client) -> None:
    user = _make_user("packing_event", "SHIPMENT")
    _login(client, user)
    order = _make_order()
    derived = client.get(_url(order.id)).get_json()["data"]["items"]

    client.post(_url(order.id), json={"updates": [{"key": derived[0]["key"], "checked": True}]})

    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id, OrderEvent.event_type == "PACKING_UPDATED")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["checked_count"] == 1
    assert events[0].payload["total"] == 6
    assert events[0].created_by_user_id == user.id
