"""주문 이벤트 스트림 API 계약 — 종류 필터·사람 이름·한글 라벨 (T15.3).

알림톡 발송 흔적 칩의 이력 패널이 이 엔드포인트를 쓴다. 패널은 알림톡 이벤트만 필요한데,
필터가 없으면 200건을 받아 클라이언트에서 걸러야 하고 보낸 사람은 숫자 id 로만 보인다.
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User

_EVENTS = "/api/orders/{order_id}/events"


def _mk_order() -> Order:
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name="임다슬",
        phone="010-2473-6730",
        address="Seoul",
        product="가구",
        status="RECEIVED",
        is_erp_order=True,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _mk_event(order_id: int, event_type: str, *, user_id: int | None = None,
              payload: dict | None = None) -> OrderEvent:
    event = OrderEvent(
        order_id=order_id,
        event_type=event_type,
        payload=payload or {},
        created_by_user_id=user_id,
        created_at=datetime.datetime(2026, 8, 24, 7, 58, 0),
    )
    db_session.add(event)
    db_session.commit()
    return event


def _login(client, username: str, role: str = "STAFF") -> int:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name="홍길동",
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


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


def test_events_require_login(client, db):
    order_id = _mk_order().id
    response = client.get(_EVENTS.format(order_id=order_id))
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_event_type_filter_narrows_stream(client, db):
    """필터를 주면 그 종류만 돌아온다 — 패널이 남의 이벤트를 걸러낼 필요가 없다."""
    uid = _login(client, "events-filter")
    order_id = _mk_order().id
    _mk_event(order_id, "ALIMTALK_SENT", user_id=uid)
    _mk_event(order_id, "ORDER_STATUS_CHANGED", user_id=uid)
    _mk_event(order_id, "ALIMTALK_FAILED", payload={"error": "invalid_phone"})

    response = client.get(
        _EVENTS.format(order_id=order_id) + "?event_type=ALIMTALK_SENT,ALIMTALK_FAILED")

    assert response.status_code == 200
    types = {e["event_type"] for e in response.get_json()["events"]}
    assert types == {"ALIMTALK_SENT", "ALIMTALK_FAILED"}


def test_events_carry_name_and_korean_label(client, db):
    """보낸 사람은 이름으로, 종류는 한글로 온다(화면이 코드를 그대로 쓰지 않게)."""
    uid = _login(client, "events-name")
    order_id = _mk_order().id
    _mk_event(order_id, "ALIMTALK_SENT", user_id=uid)

    response = client.get(_EVENTS.format(order_id=order_id) + "?event_type=ALIMTALK_SENT")

    event = response.get_json()["events"][0]
    assert event["created_by_name"] == "홍길동"
    assert event["event_label"] == "알림톡 발송"
    assert event["created_at"]


def test_automatic_event_has_no_sender_name(client, db):
    """자동 발송은 보낸 사람이 없다 — 화면이 '자동 발송'으로 표기할 근거."""
    _login(client, "events-auto")
    order_id = _mk_order().id
    _mk_event(order_id, "ALIMTALK_SENT")

    event = client.get(_EVENTS.format(order_id=order_id)).get_json()["events"][0]

    assert event["created_by_user_id"] is None
    assert event["created_by_name"] is None


def test_unknown_event_type_filter_returns_empty(client, db):
    """없는 종류를 물으면 빈 목록이다(전체 반환으로 조용히 넓어지지 않는다)."""
    _login(client, "events-empty")
    order_id = _mk_order().id
    _mk_event(order_id, "ALIMTALK_SENT")

    response = client.get(_EVENTS.format(order_id=order_id) + "?event_type=NOPE")

    assert response.get_json()["events"] == []
