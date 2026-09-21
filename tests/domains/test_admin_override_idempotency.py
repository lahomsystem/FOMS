"""ADMIN-OVERRIDE-01 — 강제 진행 재시도와 멱등 키의 관계(화면 재시도 계약 C8).

화면은 거부를 받은 뒤 **본문을 바꿔서**(admin_override·사유 추가) 같은 요청을 다시 보낸다.
그래서 멱등 키를 그대로 쓰면 안 된다. 여기서 두 가지를 못박는다.

1. 게이트에 막힌 요청은 영수증을 남기지 않는다 — 같은 키로 강제 진행을 보내면 **조용히
   예전 응답을 재생하지 않고** 실제로 처리된다(무음 replay 금지).
2. 한 번 성공한 키를 **다른 본문**으로 재사용하면 409 다(정합 축은 뚫리지 않는다).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User

_REASON = "관리자가 고객 일정 때문에 직접 완료"


def _make_user(username: str, *, role: str = "ADMIN") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team="CS", name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_cs_order_with_active_as() -> Order:
    sd = {"workflow": {"stage": "CS"},
          "as_lifecycle": {"current_cycle_id": "c1",
                           "cycles": [{"cycle_id": "c1", "transitions": []}]}}
    order = Order(received_date=date.today().isoformat(), customer_name="멱등 고객",
                  phone="010-0000-0000", address="Seoul", product="붙박이장", status="CS",
                  manager_name="Bob", is_erp_order=True, structured_data=sd,
                  erp_stage_code="CS")
    db_session.add(order)
    db_session.commit()
    return order


def _stage(order_id: int) -> str:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data["workflow"]["stage"]


def _override_event_count(order_id: int) -> int:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id,
                OrderEvent.event_type == "ADMIN_OVERRIDE_USED")
        .count()
    )


def test_게이트에_막힌_키는_강제_진행_재시도를_막지_않는다(client):
    """거부된 요청은 영수증을 안 남기므로, 같은 키의 강제 진행이 무음 replay 로 삼켜지지 않는다."""
    _login(client, _make_user("idem_admin"))
    oid = _make_cs_order_with_active_as().id
    headers = {"Idempotency-Key": "11111111-1111-1111-1111-111111111111"}

    blocked = client.post(f"/api/orders/{oid}/cs/complete", json={}, headers=headers)
    assert blocked.status_code == 409, blocked.get_data(as_text=True)
    assert blocked.get_json()["code"] == "AS_ACTIVE"
    assert _stage(oid) == "CS"

    punched = client.post(
        f"/api/orders/{oid}/cs/complete",
        json={"admin_override": True, "override_reason": _REASON},
        headers=headers,
    )

    assert punched.status_code == 200, punched.get_data(as_text=True)
    assert _stage(oid) == "COMPLETED"
    assert _override_event_count(oid) == 1


def test_성공한_키를_다른_본문으로_재사용하면_409_다(client):
    """정합 축(멱등 영수증)은 관리자도 못 뚫는다 — 화면은 재시도 때 키를 새로 만든다."""
    _login(client, _make_user("idem_admin2"))
    oid = _make_cs_order_with_active_as().id
    key = {"Idempotency-Key": "22222222-2222-2222-2222-222222222222"}

    first = client.post(
        f"/api/orders/{oid}/cs/complete",
        json={"admin_override": True, "override_reason": _REASON},
        headers=key,
    )
    assert first.status_code == 200, first.get_data(as_text=True)

    second = client.post(
        f"/api/orders/{oid}/cs/complete",
        json={"admin_override": True, "override_reason": "다른 사유"},
        headers=key,
    )

    assert second.status_code == 409, second.get_data(as_text=True)
    assert _override_event_count(oid) == 1
