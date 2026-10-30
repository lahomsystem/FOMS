"""협력사 휴대폰 한 줄 목록 · 정렬 단추 · "도면 확인" 작업대(사용자 2026-10-30 목업).

대조군: 정렬을 바꾸면 순서가 실제로 바뀐다(같은 순서면 정렬이 안 먹은 것) · 다른 회사 주문은 어느 줄에도 없다.
"""
from __future__ import annotations

import datetime
import re

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.partners.list_view import date_cell, pick_sort
from models import Order, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_stage,
    quiet_push,
    world,
)


def _order(app, partner, name, *, date=None, drawing_at=None, status=None, stage=None):
    order_id = _create(app, partner, {**_PAYLOAD, "customer_name": name}).get_json()["data"]["order_id"]
    if stage:
        _to_stage(order_id, stage)
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    if date:
        order.erp_construction_date = date
    if drawing_at:
        key = f"orders/{order_id}/drawing/{name}.png"
        sd["drawing_current_files"] = [{"key": key, "filename": f"{name}.png"}]
        sd["last_drawing_transfer"] = {"transferred_at": drawing_at}
        sd["drawing_transfer_history"] = [{"action": "TRANSFER", "transferred_at": drawing_at, "files": [{"key": key}]}]
    if status:
        sd["drawing_status"] = status
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return order_id


def _ids(html):
    mobile = html[html.index('class="foms-shell-body pp-mlist"'):html.index('class="erp-pro-card pp-queue"')]
    return [int(x) for x in re.findall(r'class="pp-row[^"]*" href="[^"]*" data-pp-order-id="(\d+)"', mobile)]


def test_rows_sort_by_construction_date_drawing_and_recent(app, world):
    late = _order(app, world["partner_a"], "늦은", date="2026-11-20", drawing_at="2026-10-30 09:00:00")
    early = _order(app, world["partner_a"], "이른", date="2026-11-02", drawing_at="2026-10-28 09:00:00")
    none = _order(app, world["partner_a"], "미정")
    _order(app, world["partner_b"], "남의회사", date="2026-11-01")
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _ids(client.get("/partner?view=orders").get_data(as_text=True)) == [early, late, none]  # 기본 = 시공일
    assert _ids(client.get("/partner?sort=drawing").get_data(as_text=True)) == [late, early, none]
    assert _ids(client.get("/partner?sort=recent").get_data(as_text=True)) == [none, early, late]
    html = client.get("/partner?sort=drawing").get_data(as_text=True)
    assert 'pp-sort__btn is-on" href="/partner?sort=drawing"' in html and "남의회사" not in html


def test_turn_board_cards_receive_and_approve_with_auto_push_note(app, world):
    receive = _order(app, world["partner_a"], "받을건", date="2026-11-03", drawing_at="2026-10-30 01:00:00",
                     status="TRANSFERRED")
    approve = _order(app, world["partner_a"], "제작건", date="2026-11-01", drawing_at="2026-10-29 01:00:00",
                     status="CONFIRMED", stage="CONFIRM")
    fixing = _order(app, world["partner_a"], "고치는건", drawing_at="2026-10-28 01:00:00", status="RETURNED")
    html = _client(app, db_session.get(User, world["partner_a"])).get("/partner?turn=1").get_data(as_text=True)
    cards = [int(x) for x in re.findall(r'<article class="pp-tcard" data-pp-order-id="(\d+)"', html)]
    assert cards == [receive, approve]  # 도면 확인 탭 기본 = 도면 나온 순
    assert f"/api/partner/orders/{receive}/drawing-receipt" in html and f"/api/partner/orders/{approve}/approve-drawing" in html
    assert "발주방에 발주 PUSH(글 + 최종 도면)가 자동으로 갑니다" in html  # 제작 요청 카드 안내(사용자 2026-10-30)
    assert "도면팀이 고치는 중" in html and f'data-pp-order-id="{fixing}"' in html
    by_date = _client(app, db_session.get(User, world["partner_a"])).get("/partner?turn=1&sort=date").get_data(as_text=True)
    assert [int(x) for x in re.findall(r'<article class="pp-tcard" data-pp-order-id="(\d+)"', by_date)] == [approve, receive]


def test_date_cell_and_sort_param():
    today = datetime.date(2026, 10, 30)
    assert date_cell(datetime.date(2026, 11, 4), False, today) == {
        "none": False, "md": "11/04", "dw": "수", "dd": "D-5", "req": False, "soon": True}
    assert date_cell(datetime.date(2026, 11, 8), True, today)["req"] is True
    assert date_cell(None, False, today) == {"none": True}
    assert pick_sort("drawing") == "drawing" and pick_sort("<script>") == "date"


def test_pc_queue_has_same_sort_buttons_and_keeps_filters(app, world):
    """PC 작업 큐 위에도 정렬 단추(사용자 2026-10-30). 걸러 본 단계는 단추 링크에 그대로 남는다."""
    _order(app, world["partner_a"], "가", date="2026-11-02")
    html = _client(app, db_session.get(User, world["partner_a"])).get("/partner?stage=도면 작업 중").get_data(as_text=True)
    pc = html[html.index('class="erp-pro-card pp-queue"'):]
    assert 'class="pp-sort pp-sort--pc"' in pc
    assert re.search(r'pp-sort__btn" href="/partner\?sort=drawing&amp;stage=[^"]+"', pc)


def test_home_is_calendar_dashboard_and_orders_tab_is_list(app, world):
    """사용자 2026-10-30: 휴대폰 홈 = 달력 대시보드(오늘 요약 · 바로 가기), 주문 목록은 '주문' 탭."""
    order_id = _order(app, world["partner_a"], "가", date="2026-11-02")
    client = _client(app, db_session.get(User, world["partner_a"]))
    home = client.get("/partner").get_data(as_text=True)
    assert 'class="foms-tower__cal pp-cal"' in home and "pp-quick" in home and "foms-tower__today pp-today" in home
    assert 'class="foms-shell-body pp-mlist"' not in home  # 휴대폰 목록은 홈에 없다
    orders = client.get("/partner?view=orders").get_data(as_text=True)
    assert 'class="foms-shell-body pp-mlist"' in orders and 'class="foms-tower__cal pp-cal"' not in orders
    assert f'data-pp-order-id="{order_id}"' in orders
