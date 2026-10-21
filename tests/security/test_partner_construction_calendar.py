"""PARTNER-FOMS 18-2: 협력사 시공 달력 — 건수는 우리 회사 전체, 금액은 그 협력사 주문 출고가만.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18.4.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.services.orders.dashboard_control_tower as tower
from db import db_session
from foms.services.partners.construction_calendar import partner_construction_calendar
from models import Order, OrderScheduleDate, User
from tests.security.partner_fixtures import _client, _create, world  # noqa: F401 — pytest fixture 재노출

_TODAY = datetime.date(2026, 11, 1)


@pytest.fixture
def priced(monkeypatch):
    """출고가 = sd['_price'](시험용) — 실제 식은 우리 달력 시험이 고정한다."""
    monkeypatch.setattr(tower, "erp_shipping_price_from_structured", lambda sd: int(sd.get("_price") or 0) or None)


def _order_on(app, partner_id, dates, price) -> int:
    order_id = _create(app, partner_id).get_json()["data"]["order_id"]
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["_price"] = price
    order.structured_data = sd
    flag_modified(order, "structured_data")
    for date in dates:
        db_session.add(OrderScheduleDate(order_id=order_id, kind="construction", date=date, source="test"))
    db_session.commit()
    return order_id


def _cell(cal, iso):
    return next(c for w in cal["weeks"] for c in w if c["iso"] == iso)


def test_counts_all_companies_but_amount_only_own(app, world, priced):
    _order_on(app, world["partner_a"], ["2026-11-05"], 3_000_000)
    _order_on(app, world["partner_b"], ["2026-11-05"], 9_990_000)  # 다른 회사 — 건수만
    _order_on(app, world["partner_a"], ["2026-11-10", "2026-11-11"], 2_000_000)  # 이틀 시공은 반씩
    cal = partner_construction_calendar(db_session, world["org_a"], "2026-11", today=_TODAY)
    assert _cell(cal, "2026-11-05")["count"] == 2
    assert _cell(cal, "2026-11-05")["amount_label"] == "300만"
    assert _cell(cal, "2026-11-10")["amount_label"] == "100만" and _cell(cal, "2026-11-11")["count"] == 1
    assert cal["construction_total"] == 4 and cal["own_amount_label"] == "500만"
    other = partner_construction_calendar(db_session, world["org_b"], "2026-11", today=_TODAY)
    assert other["own_amount_label"] == "999만" and _cell(other, "2026-11-05")["count"] == 2


def test_month_range_and_api_carry_no_customer_data(app, world, priced):
    order_id = _order_on(app, world["partner_b"], ["2026-11-05"], 9_990_000)
    far = partner_construction_calendar(db_session, world["org_a"], "2028-01", today=_TODAY)
    assert far["month"] == "2026-11"  # 6개월 밖은 이번 달
    client = _client(app, db_session.get(User, world["partner_a"]))
    body = client.get("/api/partner/construction-calendar?month=2026-11").get_json()
    assert body["success"] is True
    text = str(body)
    customer = db_session.get(Order, order_id).customer_name
    assert customer not in text and "999만" not in text and "다라가구" not in text  # 남의 고객 · 금액 · 회사 이름 없음
    staff = _client(app, db_session.get(User, world["staff"])).get("/api/partner/construction-calendar")
    assert staff.status_code == 403


def test_home_shows_calendar(app, world, priced):
    html = _client(app, db_session.get(User, world["partner_a"])).get("/partner").get_data(as_text=True)
    assert 'class="foms-tower__cal pp-cal"' in html and "내 회사 출고가 합계" in html
    new = _client(app, db_session.get(User, world["partner_a"])).get("/partner/orders/new").get_data(as_text=True)
    assert 'data-pp-date-counts="/api/partner/construction-calendar"' in new
