"""주문 수정 화면 예약금 칸 아래 '마지막으로 고친 사람·때' 계약 (2026-11-11).

운영 #5978(정순현) 예약금 4,344,000 을 누가 바꿨는지 운영 DB 감사 기록을 뒤져야 알았다.
네이버 관계 표와 같은 한 줄(``이름 MM-DD HH:MM 고침``)을 주문 화면 예약금 칸 아래에도 낸다.
다른 금액 칸 변경은 세지 않고(음성 대조군), 기록이 없으면 줄 자체가 없다.
"""

from __future__ import annotations

import datetime
import itertools
import re

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User

_counter = itertools.count(1)


def _make_user(name: str) -> int:
    user = User(
        username=f"deposit-who-{next(_counter)}",
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="SALES",
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order() -> int:
    order = Order(
        received_date="2026-11-04",
        received_time="10:00",
        customer_name="예약금 고객",
        phone="010-1234-5678",
        address="서울 예약구 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="RECEIVED",
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "parties": {"customer": {"name": "예약금 고객", "phone": "010-1234-5678"}},
            "items": [{"product_name": "붙박이장", "price": 4_344_000}],
            "payment": {"deposit": 4_344_000},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _event(order_id: int, field: str, user_id: int | None, at: datetime.datetime) -> None:
    db_session.add(OrderEvent(
        order_id=order_id, event_type="PAYMENT_CHANGED",
        payload={"field": field, "from": 100_000, "to": 4_344_000},
        created_by_user_id=user_id, created_at=at,
    ))
    db_session.commit()


def _who_lines(html: str) -> list[str]:
    return re.findall(r'<div class="erp-deposit-who">([^<]*)</div>', html)


def test_edit_page_shows_last_deposit_editor(client):
    editor = _make_user("정다슬")
    viewer = _make_user("박열람")
    order_id = _make_order()
    # UTC-naive 규약 — 화면은 KST(+9h). 뒤의 할인 변경은 예약금 고침이 아니다.
    _event(order_id, "payment.deposit", editor, datetime.datetime(2026, 11, 11, 4, 41))
    _event(order_id, "payment.discount", viewer, datetime.datetime(2026, 11, 11, 6, 0))
    with client.session_transaction() as sess:
        sess["user_id"] = viewer

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    lines = _who_lines(html)
    assert lines, "예약금 고친 사람 줄이 렌더되지 않았다"
    assert set(lines) == {"정다슬 11-11 13:41 고침"}


def test_edit_page_without_deposit_change_has_no_line(client):
    viewer = _make_user("박열람")
    order_id = _make_order()
    _event(order_id, "payment.discount", viewer, datetime.datetime(2026, 11, 11, 6, 0))
    with client.session_transaction() as sess:
        sess["user_id"] = viewer

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert 'id="erp-deposit-amount"' in html
    assert _who_lines(html) == []
