"""협력사 출고 탭(/partner/shipments, 사용자 2026-11-12) — 우리 출고 탭 하루치 출고표를 자기 회사 주문만, 읽기만.

* 그날 줄 = 우리 시공일 + 확정 전 희망 시공일(희망 표시). 다른 회사 주문 · 금액 · 우리 메모는 싣지 않는다.
* 시공자 묶음 = 우리 태블릿 출고표와 같은 함수(시공자 정하는 중이 맨 위).
* 날짜 띠 = 오늘부터 14일 · 날마다 내 회사 건수. 날짜가 없으면 일이 있는 가장 가까운 날을 연다.
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.partners.shipment_board import partner_shipment_board
from models import Order, OrderScheduleDate, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, world  # noqa: F401 — pytest fixture 재노출

_TODAY = datetime.date(2026, 11, 12)


def _order_on(app, partner_id, day, *, workers=(), time="", customer=None, memo="") -> int:
    payload = {**_PAYLOAD, "customer_name": customer} if customer else None
    order_id = _create(app, partner_id, payload).get_json()["data"]["order_id"]
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["shipment"] = {"construction_workers": list(workers), "construction_time": time, "as_content": memo}
    sd["shipping_price"] = 7_770_000
    order.structured_data = sd
    flag_modified(order, "structured_data")
    if day:
        db_session.add(OrderScheduleDate(order_id=order_id, kind="construction", date=day, source="test"))
    db_session.commit()
    return order_id


def _ids(board) -> list[int]:
    return [row["id"] for g in board["groups"] for row in g["rows"]]


def test_day_lists_own_orders_grouped_by_worker(app, world):
    no_worker = _order_on(app, world["partner_a"], "2026-11-13", customer="정하는중")
    kim = _order_on(app, world["partner_a"], "2026-11-13", workers=["김시공"], time="오전 8시", customer="김씨집")
    two = _order_on(app, world["partner_a"], "2026-11-13", workers=["김시공", "이시공"], time="오후 1시")
    other = _order_on(app, world["partner_b"], "2026-11-13", workers=["김시공"], customer="남의고객")
    board = partner_shipment_board(db_session, world["org_a"], "2026-11-13", _TODAY)
    assert board["selected"] == "2026-11-13" and board["total"] == 3 and board["unassigned"] == 1
    assert other not in _ids(board)
    first, second = board["groups"]
    assert first["unassigned"] and [r["id"] for r in first["rows"]] == [no_worker]  # 정하는 중이 맨 위
    assert second["lead"]["name"] == "김시공" and {r["id"] for r in second["rows"]} == {kim, two}
    row = next(r for r in second["rows"] if r["id"] == kim)
    assert row["time"] == "오전 8시" and not row["time_is_plan"] and row["customer"] == "김씨집"
    assert [w["name"] for w in next(r for r in second["rows"] if r["id"] == two)["workers"]] == ["김시공", "이시공"]
    assert "shipping_price" not in str(board) and "7770000" not in str(board)


def test_requested_date_row_is_flagged(app, world):
    resp = _create(app, world["partner_a"], {**_PAYLOAD, "requested_construction_date": "2026-11-14",
                                             "requested_construction_time": "오후"})
    order_id = resp.get_json()["data"]["order_id"]
    board = partner_shipment_board(db_session, world["org_a"], "2026-11-14", _TODAY)
    [row] = [r for g in board["groups"] for r in g["rows"]]
    assert (row["id"], row["requested"], row["time"], row["time_is_plan"]) == (order_id, True, "오후", True)


def test_strip_counts_and_default_day(app, world):
    _order_on(app, world["partner_a"], "2026-11-15")
    _order_on(app, world["partner_a"], "2026-11-15")
    _order_on(app, world["partner_a"], "2026-11-20")
    _order_on(app, world["partner_b"], "2026-11-13")  # 다른 회사 — 띠 숫자에 안 든다
    board = partner_shipment_board(db_session, world["org_a"], None, _TODAY)
    days = {d["iso"]: d for d in board["days"]}
    assert len(board["days"]) == 14 and board["days"][0]["is_today"]
    assert days["2026-11-15"]["count"] == 2 and days["2026-11-13"]["count"] == 0 and days["2026-11-20"]["count"] == 1
    assert board["selected"] == "2026-11-15"  # 오늘이 비면 일이 있는 가장 가까운 날
    empty = partner_shipment_board(db_session, world["org_a"], "2026-11-12", _TODAY)
    assert empty["selected"] == "2026-11-12" and empty["groups"] == []  # 고른 날은 비어도 그대로
    far = partner_shipment_board(db_session, world["org_a"], "2027-01-05", _TODAY)
    assert far["is_outside"] and far["selected"] == "2027-01-05"
    bad = partner_shipment_board(db_session, world["org_a"], "2026-13-40", _TODAY)
    assert bad["selected"] == "2026-11-15"


def test_page_shows_only_own_company_and_no_internal_memo(app, world):
    day = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    own = _order_on(app, world["partner_a"], day, workers=["김시공"], time="오전 8시", memo="우리끼리 메모")
    other = _order_on(app, world["partner_b"], day, customer="남의고객")
    html = _client(app, db_session.get(User, world["partner_a"])).get(f"/partner/shipments?date={day}").get_data(as_text=True)
    assert f"/partner/orders/{own}" in html and "김시공" in html and "오전 8시" in html
    assert f"/partner/orders/{other}" not in html and "남의고객" not in html
    assert "우리끼리 메모" not in html and "777만" not in html and "7,770,000" not in html
    assert 'data-pp-nav="ship"' in html and 'aria-current="page"' in html.split('data-pp-nav="ship"')[1][:40]
    assert "partner-shipment.css" in html


def test_staff_cannot_open_partner_shipments(app, world):
    resp = _client(app, db_session.get(User, world["staff"])).get("/partner/shipments")
    assert resp.status_code in (302, 403, 404)


def test_partner_nav_links_to_shipments(app, world):
    html = _client(app, db_session.get(User, world["partner_a"])).get("/partner").get_data(as_text=True)
    assert html.count('href="/partner/shipments"') == 2  # PC 메뉴 줄 · 휴대폰 아래 탭
